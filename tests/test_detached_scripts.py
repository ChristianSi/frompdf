import unittest
from typing import cast

from pdftext.schema import Page

from frompdf.lines import attach_stacked_scripts, attach_stray_scripts, iter_lines
from frompdf.scripts import render_scripts


def span(text: str, x: float, top: float, size: float, width: float = 5.0) -> dict:
    """Build a span of equally wide glyphs, starting at x with the given top edge."""
    chars = [
        {
            'char': char,
            'bbox': [x + index * width, top, x + (index + 1) * width, top + size * 0.9],
            'font': {'size': size},
            'rotation': 0,
        }
        for index, char in enumerate(text)
    ]
    return {
        'text': text,
        'bbox': [x, top, x + len(text) * width, top + size * 0.9],
        'font': {'size': size},
        'chars': chars,
    }


def line(*spans: dict) -> dict:
    """Build a pdftext line from spans, ending in a line break."""
    boxes = [s['bbox'] for s in spans]
    end = boxes[-1][2]
    return {
        'bbox': [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ],
        'spans': [
            *spans,
            {'text': '\n', 'bbox': [end, 0, end, 0], 'font': {'size': 1}, 'chars': []},
        ],
    }


def page(*blocks: list[dict]) -> Page:
    return cast(Page, {'blocks': [{'lines': lines} for lines in blocks]})


def texts(page_obj: Page) -> list[str]:
    """Return the rendered text of each line record."""
    return [render_scripts(line.text, line.scripts) for line in iter_lines([page_obj])]


class StrayScriptTests(unittest.TestCase):
    def test_script_in_a_block_of_its_own_joins_its_line(self) -> None:
        text = line(span('For any set F', 0, 100, 10))
        following = line(span(') is open', 68, 100, 10))
        script = line(span('i', 65, 98, 7, width=3))
        page_obj = page([text], [following], [script])

        attach_stray_scripts([page_obj])

        self.assertEqual(texts(page_obj), ['For any set F<sup>i</sup>', ') is open'])

    def test_unshifted_or_same_size_label_stays_apart(self) -> None:
        for label in (span('3', 65, 100, 7), span('3', 65, 95, 10)):
            with self.subTest(label=label['bbox']):
                page_obj = page(
                    [line(span('Recovery time', 0, 100, 10))],
                    [line(span('Other text', 0, 200, 10))],
                    [line(label)],
                )

                attach_stray_scripts([page_obj])

                self.assertEqual(len(texts(page_obj)), 3)


class StackedScriptTests(unittest.TestCase):
    def test_subscript_below_superscript_joins_the_line(self) -> None:
        base = line(span('and R', 0, 100, 10), span('i', 25, 98, 7, width=3))
        subscript = line(span('∗', 25, 104, 7, width=4))
        page_obj = page([base, subscript, line(span(') holds', 29.5, 100, 10))])

        attach_stacked_scripts([page_obj])

        self.assertEqual(texts(page_obj), ['and R<sup>i</sup><sub>∗</sub>', ') holds'])

    def test_subscript_starting_the_next_record_moves_to_the_line(self) -> None:
        base = line(span('and R', 0, 100, 10), span('j', 25, 98, 7, width=3))
        following = line(span('∗', 25, 104, 7, width=4), span(') holds', 29.5, 100, 10))
        page_obj = page([base, following])

        attach_stacked_scripts([page_obj])

        self.assertEqual(texts(page_obj), ['and R<sup>j</sup><sub>∗</sub>', ') holds'])
        self.assertEqual(iter_lines([page_obj])[1].x1, 29.5)

    def test_superscript_record_takes_its_base_from_the_record_before(self) -> None:
        # TeX shifts the superscript right of the subscript by the italic correction.
        records = [
            line(span('bound 2C', 0, 100, 10)),
            line(span('(s)', 40.7, 98, 7, width=3)),
            line(span('0', 40, 104, 7, width=4), span(' holds', 50, 100, 10)),
        ]
        page_obj = page(records)

        attach_stacked_scripts([page_obj])

        self.assertEqual(texts(page_obj), ['bound 2C', '<sup>(s)</sup><sub>0</sub>', 'holds'])

    def test_misaligned_or_same_direction_scripts_stay_apart(self) -> None:
        for second in (span('∗', 28, 104, 7, width=4), span('∗', 25, 98, 7, width=4)):
            with self.subTest(second=second['bbox']):
                base = line(span('and R', 0, 100, 10), span('i', 25, 98, 7, width=3))
                page_obj = page([base, line(second)])

                attach_stacked_scripts([page_obj])

                self.assertEqual(len(texts(page_obj)), 2)


if __name__ == '__main__':
    unittest.main()
