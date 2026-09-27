import unittest
from dataclasses import replace

from frompdf.heading_candidates import find_typographic_heading_lines
from frompdf.models import Line
from frompdf.segmentation import segment_lines


def line(text: str, top: float, *, size: float = 10.0, font: str = 'Body-Roman') -> Line:
    return Line(
        text=text,
        page_no=1,
        block_no=1,
        line_no_on_page=1,
        font_size=size,
        x1=50.0,
        y1=top,
        x2=350.0,
        y2=top + size,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        font_name=font,
    )


def title(text: str, top: float = 140.0, *, size: float = 9.0, font: str = 'Body-Roman'):
    return replace(line(text, top, size=size, font=font), x1=100.0, x2=300.0)


def page(titles: list[Line], following_size: float = 10.0) -> list[Line]:
    """Surround candidates with enough prose to establish real column geometry."""
    prose = 'Ordinary prose has enough letters to establish the surrounding body column'
    before = [line(prose, 20.0 + 14 * index) for index in range(6)]
    after_top = (titles[-1].y2 or 200.0) + 24.0
    after = [line(prose, after_top + 14 * index, size=following_size) for index in range(6)]
    return before + titles + after


class TypographicHeadingTests(unittest.TestCase):
    def test_smallcaps_use_body_rhythm_and_keep_source_lines_exactly_once(self):
        titles = [
            title(text, 140.0 + 14 * index, size=5.6, font='BodySmallcaps')
            for index, text in enumerate(
                ['chapter two', 'how the heavens turn', 'around themselves']
            )
        ]
        # A full capital can increase the measured glyph height on one line.
        titles[1].font_size = 7.3
        titles[1].y2 = titles[1].y1 + 7.3
        lines = page(titles)
        headings = find_typographic_heading_lines(lines)
        self.assertEqual(headings, {id(item): id(titles[0]) for item in titles})
        groups = segment_lines(lines, headings)
        self.assertIn(titles, groups)
        self.assertEqual(
            [id(item) for group in groups for item in group], [id(item) for item in lines]
        )

    def test_caps_join_across_parser_blocks_and_accent_height_variations(self):
        titles = [title('CONTENT APPROVAL'), title('GRANTED BY SOMEONE', 157.0, size=11.2)]
        titles[1].block_no = 2
        titles[0].font_name = 'ABCDEF+Body-Roman'
        lines = page(titles)
        headings = find_typographic_heading_lines(lines)
        self.assertEqual(len(headings), 2)
        self.assertIn(titles, segment_lines(lines, headings))

    def test_short_italic_label_is_split_from_smaller_following_text(self):
        label = title('References', size=10.0, font='Body-Italic')
        lines = page([label], following_size=7.5)
        headings = find_typographic_heading_lines(lines)
        self.assertEqual(headings, {id(label): id(label)})
        self.assertIn([label], segment_lines(lines, headings))

    def test_adjacent_different_sized_titles_are_not_joined(self):
        titles = [title('FIRST TITLE', size=9.0), title('LARGER TITLE', 157.0, size=12.0)]
        self.assertFalse(find_typographic_heading_lines(page(titles)))

    def test_italic_label_requires_smaller_following_text(self):
        self.assertFalse(
            find_typographic_heading_lines(page([title('An aside', font='Body-Italic')]))
        )

    def test_multiline_italic_salutation_does_not_qualify_via_last_line(self):
        titles = [
            title(text, 140.0 + index * 14, font='Body-Italic')
            for index, text in enumerate(['To Her Highness', 'the Infanta', 'My lady'])
        ]
        self.assertFalse(find_typographic_heading_lines(page(titles, following_size=7.5)))

    def test_four_line_caps_passage_does_not_qualify_via_last_three_lines(self):
        titles = [title('A LONGER CAPITALIZED PASSAGE', 140.0 + index * 14) for index in range(4)]
        self.assertFalse(find_typographic_heading_lines(page(titles)))

    def test_length_limit_rejects_long_candidate(self):
        self.assertFalse(find_typographic_heading_lines(page([title('LONG WORDS ' * 26)])))

    def test_inset_left_aligned_quote_is_not_centered(self):
        candidate = replace(title('A CAPITALIZED QUOTATION'), x1=80.0, x2=260.0)
        self.assertFalse(find_typographic_heading_lines(page([candidate])))

    def test_smallcap_paragraph_opening_is_not_a_heading(self):
        candidate = line(
            'an opening in small caps followed by ordinary prose', 140, font='Smallcaps'
        )
        self.assertFalse(find_typographic_heading_lines(page([candidate])))

    def test_tight_body_spacing_does_not_make_a_heading(self):
        candidate = title('EMPHASIZED TEXT', 104.0)
        self.assertFalse(find_typographic_heading_lines(page([candidate])))

    def test_missing_geometry_does_not_make_a_heading(self):
        for field in ['x1', 'y1', 'x2', 'y2']:
            with self.subTest(field=field):
                candidate = replace(title('SECTION TITLE'), **{field: None})
                self.assertFalse(find_typographic_heading_lines(page([candidate])))

    def test_sparse_labels_do_not_establish_a_body_column(self):
        labels = [title('MAP LOCATION', 20.0 + 14 * index) for index in range(6)]
        self.assertFalse(find_typographic_heading_lines(labels))

    def test_caption_below_body_without_following_passage_is_not_a_heading(self):
        candidate = title('FIGURE CAPTION')
        lines = page([candidate])[:7]
        self.assertFalse(find_typographic_heading_lines(lines))

    def test_candidates_never_use_following_page_as_body_evidence(self):
        candidate = title('SECTION TITLE')
        lines = page([candidate])
        for item in lines[7:]:
            item.page_no = 2
        self.assertFalse(find_typographic_heading_lines(lines))

    def test_widely_separated_caps_title_leaves_salutation_in_body(self):
        candidate = title('DEDICATION')
        lines = page([candidate])
        salutation = title('To Her Highness', 190.0, size=10.0, font='Body-Italic')
        lines.insert(7, salutation)
        for item in lines[8:]:
            item.y1 += 80
            item.y2 += 80
        headings = find_typographic_heading_lines(lines)
        self.assertEqual(headings, {id(candidate): id(candidate)})


if __name__ == '__main__':
    unittest.main()
