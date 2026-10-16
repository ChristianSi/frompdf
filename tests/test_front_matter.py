import unittest

from frompdf.front_matter import format_front_matter, is_chapter_label, looks_like_names
from frompdf.models import Block, Heading, PageNumber, Paragraph, ScriptRange, StrongParagraph

PAGE_ONE = PageNumber(raw=1, visible=None)
PAGE_TWO = PageNumber(raw=2, visible=None)
BODY_TEXT = 'Ordinary body text that is long enough to end the front matter. ' * 4


def heading(text: str, level: int, page: PageNumber = PAGE_ONE) -> Heading:
    return Heading(text, page, page, level=level)


def paragraph(text: str, page: PageNumber = PAGE_ONE) -> Paragraph:
    return Paragraph(text, page, page)


def formatted(block_list: list[Block], source_blocks: list[Block] | None = None) -> list[Block]:
    """Format front matter and return the kept blocks."""
    dropped = format_front_matter(block_list, source_blocks or list(block_list))
    return [block for index, block in enumerate(block_list) if index not in dropped]


def describe(block_list: list[Block]) -> list[str]:
    return [
        f'H{block.level} {block.text}'
        if isinstance(block, Heading)
        else f'** {block.text}'
        if isinstance(block, StrongParagraph)
        else block.text
        for block in block_list
    ]


class NameRecognitionTests(unittest.TestCase):
    def test_recognizes_single_names_and_name_lists(self) -> None:
        for text in [
            'Jérémie Chalopin',
            'Giuseppe A. Di Luna',
            'Rolf B. Versteeg, Paul H. M. van Loosdrecht',
            'Yi-Jun Chang & Jean-Pierre O’Neill',
            'Sergey Artyukhin 4 and Fumiya Sekiguchi*†✉',
        ]:
            with self.subTest(text=text):
                self.assertTrue(looks_like_names(paragraph(text)))

    def test_ignores_affiliation_superscripts(self) -> None:
        block = Paragraph('Fumiya Sekiguchi12, Kestutis Budzinauskas3', PAGE_ONE, PAGE_ONE)
        block.scripts = (ScriptRange(16, 18, 'sup'), ScriptRange(41, 42, 'sup'))

        self.assertTrue(looks_like_names(block))

    def test_rejects_titles_labels_and_single_words(self) -> None:
        for text in [
            'Abstract',
            'Angaben zur Veröffentlichung / Publication details:',
            'Neue Folge Nr. 12',
            'Money for nothing',
            'A. B.',
            'The Ministry of Truth and Some Other Very Long Organization Name',
        ]:
            with self.subTest(text=text):
                self.assertFalse(looks_like_names(paragraph(text)))

    def test_recognizes_chapter_labels_but_not_numbered_titles(self) -> None:
        self.assertTrue(is_chapter_label(heading('CHAPTER 10', 1)))
        self.assertTrue(is_chapter_label(heading('Part II', 1)))
        self.assertFalse(is_chapter_label(heading('1 Introduction', 1)))
        self.assertFalse(is_chapter_label(heading('Chapter 10 Results', 1)))


class FrontMatterFormattingTests(unittest.TestCase):
    def test_subtitle_with_unique_level_becomes_bold(self) -> None:
        blocks: list[Block] = [
            heading('Espaçologia', 1),
            heading('Spaceology', 2),
            paragraph(BODY_TEXT),
            heading('1. Abertura', 3),
        ]

        self.assertEqual(
            describe(formatted(blocks)),
            ['H1 Espaçologia', '** Spaceology', BODY_TEXT, 'H3 1. Abertura'],
        )

    def test_keeps_subtitle_level_used_by_section_headings(self) -> None:
        blocks: list[Block] = [
            heading('Title', 1),
            heading('Abstract', 2),
            paragraph(BODY_TEXT),
            heading('Introduction', 2),
        ]

        self.assertEqual(describe(formatted(blocks))[1], 'H2 Abstract')

    def test_author_names_become_bold_with_line_breaks_from_source(self) -> None:
        source_name = paragraph('Fumiya Sekiguchi,\nPaul H. M. van Loosdrecht')
        blocks: list[Block] = [
            heading('Title', 1),
            heading('Fumiya Sekiguchi, Paul H. M. van Loosdrecht', 3),
            paragraph(BODY_TEXT),
            heading('Results', 3),
        ]
        source_blocks: list[Block] = [blocks[0], source_name, blocks[2], blocks[3]]

        result = formatted(blocks, source_blocks)

        self.assertIsInstance(result[1], StrongParagraph)
        self.assertEqual(result[1].text, 'Fumiya Sekiguchi,\nPaul H. M. van Loosdrecht')
        self.assertIsInstance(result[3], Heading)

    def test_name_headings_interleaved_with_affiliations_become_bold(self) -> None:
        blocks: list[Block] = [
            heading('Title', 1),
            heading('Jane Doe', 2),
            paragraph('University of Somewhere'),
            heading('John Roe', 2),
            paragraph('Institute of Elsewhere'),
            heading('Abstract', 3),
            paragraph(BODY_TEXT),
            heading('1 Introduction', 2),
        ]

        self.assertEqual(
            describe(formatted(blocks)),
            [
                'H1 Title',
                '** Jane Doe',
                'University of Somewhere',
                '** John Roe',
                'Institute of Elsewhere',
                'H3 Abstract',
                BODY_TEXT,
                'H2 1 Introduction',
            ],
        )

    def test_keeps_level_when_one_of_its_front_matter_headings_is_no_name(self) -> None:
        blocks: list[Block] = [
            heading('espero', 1),
            heading('Neue Folge Nr. 12', 4),
            heading('Libertad Verlag Potsdam', 4),
            paragraph(BODY_TEXT),
            heading('Prolog', 4),
        ]

        self.assertEqual(
            describe(formatted(blocks))[1:3], ['H4 Neue Folge Nr. 12', 'H4 Libertad Verlag Potsdam']
        )

    def test_front_matter_ends_with_page_and_body_text(self) -> None:
        blocks: list[Block] = [
            heading('Title', 1),
            paragraph(BODY_TEXT),
            heading('Jane Doe', 2),
            heading('John Roe', 2, PAGE_TWO),
        ]

        self.assertEqual(describe(formatted(blocks))[2:], ['H2 Jane Doe', 'H2 John Roe'])

    def test_chapter_label_becomes_bold_and_ornament_is_dropped(self) -> None:
        blocks: list[Block] = [
            heading('CHAPTER 10', 1),
            heading('Domestic Cooks’ Work', 2),
            paragraph('Katharina Graf'),
            paragraph('•••'),
            heading('Introduction', 3),
            paragraph(BODY_TEXT),
            paragraph('***'),
        ]

        self.assertEqual(
            describe(formatted(blocks)),
            [
                '** CHAPTER 10',
                'H2 Domestic Cooks’ Work',
                'Katharina Graf',
                'H3 Introduction',
                BODY_TEXT,
                '***',
            ],
        )

    def test_repeated_title_on_a_later_page_has_its_own_front_matter(self) -> None:
        blocks: list[Block] = [
            heading('Cover Title', 2),
            paragraph(BODY_TEXT),
            heading('ARTICLE', 3, PAGE_TWO),
            heading('Article Title', 1, PAGE_TWO),
            heading('Jane Doe, John Roe', 3, PAGE_TWO),
            paragraph(BODY_TEXT, PAGE_TWO),
        ]

        self.assertEqual(
            describe(formatted(blocks))[2:5],
            ['H3 ARTICLE', 'H1 Article Title', '** Jane Doe, John Roe'],
        )


if __name__ == '__main__':
    unittest.main()
