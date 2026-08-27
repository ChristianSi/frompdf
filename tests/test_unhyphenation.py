import unittest
from collections import Counter

from frompdf.blocks import lines_to_markdown_blocks
from frompdf.models import Line, PageNumber
from frompdf.unhyphenation import (
    document_coordination_tokens,
    document_mixed_case_words,
    document_word_counts,
    unhyphenate_block_lines,
)


def resolve(lines: list[str], evidence: str = '') -> str:
    """Resolve a synthetic block using its lines and separate document evidence."""
    evidence_lines = [evidence]
    all_lines = [*lines, *evidence_lines]
    return unhyphenate_block_lines(
        lines,
        document_word_counts(all_lines),
        document_mixed_case_words(all_lines),
        document_coordination_tokens(all_lines),
    )


def text_line(text: str, block_no: int, line_no: int) -> Line:
    """Build a minimally positioned synthetic line."""
    return Line(
        text=text,
        page_no=1,
        block_no=block_no,
        line_no_on_page=line_no,
        font_size=10.0,
        x1=20.0,
        y1=float(line_no * 12),
        x2=200.0,
        y2=float(line_no * 12 + 10),
        rel_x=0.0,
        rel_y=12.0,
        avg_weight=400.0,
    )


class DocumentEvidenceTests(unittest.TestCase):
    def test_learns_coordination_tokens_only_from_same_line_patterns(self) -> None:
        tokens = document_coordination_tokens(
            [
                'Korrektur- und Abfragemöglichkeiten',
                'middle- and upper-income',
                'Aufgaben-',
                'oder Challenge-bezogen',
            ]
        )

        self.assertEqual(tokens, {'and', 'und'})

    def test_unhyphenated_document_form_wins_case_insensitively(self) -> None:
        result = resolve(
            ['This prevents dis-', 'crimination in licensing.'],
            evidence='DISCRIMINATION',
        )

        self.assertEqual(result, 'This prevents discrimination\nin licensing.')

    def test_hyphenated_document_form_wins(self) -> None:
        result = resolve(
            ['A 2-edge-', 'connected network is required.'],
            evidence='2-edge-connected',
        )

        self.assertEqual(result, 'A 2-edge-connected\nnetwork is required.')

    def test_more_frequent_form_wins(self) -> None:
        evidence = 'nonprofit nonprofit non-profit'

        self.assertEqual(
            resolve(['A non-', 'profit organization'], evidence), 'A nonprofit\norganization'
        )

    def test_frequency_tie_keeps_hyphen(self) -> None:
        evidence = 'nonprofit non-profit'

        self.assertEqual(
            resolve(['A non-', 'profit organization'], evidence),
            'A non-profit\norganization',
        )

    def test_exact_evidence_precedes_capitalization_fallback(self) -> None:
        result = resolve(['Visit the Online-', 'Shop today.'], evidence='OnlineShop')

        self.assertEqual(result, 'Visit the OnlineShop\ntoday.')

    def test_case_folded_evidence_does_not_override_capitalization_fallback(self) -> None:
        result = resolve(
            ['the Konsent-', 'Prinzip requires consent'],
            evidence='Konsentprinzip',
        )

        self.assertEqual(result, 'the Konsent-Prinzip\nrequires consent')

    def test_exact_mixed_case_evidence_removes_hyphen_before_capital(self) -> None:
        result = resolve(['the Java-', 'Script runtime'], evidence='JavaScript')

        self.assertEqual(result, 'the JavaScript\nruntime')

    def test_dictionary_keeps_internal_hyphens_and_ignores_surrounding_punctuation(self) -> None:
        counts = document_word_counts(['(E-Learning-Systeme), E‑Learning‑Systeme!'])

        self.assertEqual(counts, Counter({'e-learning-systeme': 2}))

    def test_dictionary_does_not_join_words_across_arbitrary_punctuation(self) -> None:
        counts = document_word_counts(['foo/bar'])

        self.assertNotIn('foobar', counts)
        self.assertEqual(counts, Counter({'foo': 1, 'bar': 1}))


class FallbackHeuristicTests(unittest.TestCase):
    def test_other_internal_hyphens_keep_boundary_hyphen(self) -> None:
        self.assertEqual(
            resolve(['Top-down-', 'Entscheidungen helfen.']),
            'Top-down-Entscheidungen\nhelfen.',
        )

    def test_initial_capital_keeps_boundary_hyphen(self) -> None:
        self.assertEqual(resolve(['anti-', 'American rhetoric']), 'anti-American\nrhetoric')

    def test_all_caps_word_does_not_trigger_capital_rule(self) -> None:
        self.assertEqual(resolve(['DIS-', 'CRIMINATION']), 'DISCRIMINATION')

    def test_digit_keeps_boundary_hyphen(self) -> None:
        self.assertEqual(resolve(['COVID-', '19 restrictions']), 'COVID-19\nrestrictions')

    def test_other_nonletter_keeps_boundary_hyphen(self) -> None:
        self.assertEqual(resolve(['C++-', 'api bindings']), 'C++-api\nbindings')

    def test_default_removes_boundary_hyphen(self) -> None:
        self.assertEqual(
            resolve(['code modifica-', 'tions are allowed']),
            'code modifications\nare allowed',
        )

    def test_soft_hyphen_is_removed_without_other_evidence(self) -> None:
        self.assertEqual(resolve(['modifica\u00ad', 'tions']), 'modifications')

    def test_nonbreaking_hyphen_is_kept_without_other_evidence(self) -> None:
        self.assertEqual(resolve(['word\u2011', 'part']), 'word\u2011part')


class BoundaryRewriteTests(unittest.TestCase):
    def test_moves_trailing_punctuation_with_continuation_word(self) -> None:
        result = resolve(['While, tradi-', 'tionally, licenses differed.'])

        self.assertEqual(result, 'While, traditionally,\nlicenses differed.')

    def test_ignores_quote_and_footnote_suffix_when_deciding(self) -> None:
        result = resolve(
            ['their individual protago-', 'nists”[1]. The genre continues.'],
            evidence='protagonists',
        )

        self.assertEqual(
            result,
            'their individual protagonists”[1].\nThe genre continues.',
        )

    def test_removes_consumed_empty_physical_line(self) -> None:
        result = resolve(['These modifica-', 'tions', 'remain useful.'])

        self.assertEqual(result, 'These modifications\nremain useful.')

    def test_does_not_merge_after_spaced_standalone_hyphen(self) -> None:
        result = resolve(['funded by the European Union -', 'NextGenerationEU through projects'])

        self.assertEqual(
            result,
            'funded by the European Union -\nNextGenerationEU through projects',
        )

    def test_does_not_merge_when_next_line_starts_with_punctuation(self) -> None:
        result = resolve(['unfinished-', '“quoted text”'])

        self.assertEqual(result, 'unfinished-\n“quoted text”')

    def test_keeps_coordination_hyphen_before_conjunction(self) -> None:
        result = resolve(
            ['Organisations-', 'und Zwangsmittel'],
            evidence='Korrektur- und Abfragemöglichkeiten',
        )

        self.assertEqual(result, 'Organisations-\nund Zwangsmittel')

    def test_keeps_coordination_hyphen_before_learned_english_token(self) -> None:
        result = resolve(
            ['middle-', 'and upper-income'],
            evidence='lower- and middle-income',
        )

        self.assertEqual(result, 'middle-\nand upper-income')

    def test_frequent_word_is_not_assumed_to_be_a_coordinator(self) -> None:
        result = resolve(
            ['bei-', 'den Bereichen'],
            evidence='den den den den den den den den den den',
        )

        self.assertEqual(result, 'beiden\nBereichen')

    def test_combined_word_evidence_precedes_learned_coordination(self) -> None:
        result = resolve(
            ['gr-', 'and total'],
            evidence='grand lower- and middle-income',
        )

        self.assertEqual(result, 'grand\ntotal')

    def test_internal_hyphen_excludes_learned_coordination(self) -> None:
        result = resolve(
            ['Open-Source-', 'Software remains'],
            evidence='Data- Software systems',
        )

        self.assertEqual(result, 'Open-Source-Software\nremains')

    def test_does_not_merge_across_markdown_blocks(self) -> None:
        lines = [
            text_line('first paragraph ends with unfinished-', block_no=1, line_no=1),
            text_line('continuation is a new paragraph', block_no=2, line_no=2),
        ]

        blocks = lines_to_markdown_blocks(lines, {1: PageNumber(raw=1, visible=None)})

        self.assertEqual(
            [block.text for block in blocks],
            ['first paragraph ends with unfinished-', 'continuation is a new paragraph'],
        )


class UnspacedDashTests(unittest.TestCase):
    def test_moves_token_after_line_final_en_dash(self) -> None:
        result = resolve(['Collaboration (pp. 25–', '28). https://example.test/'])

        self.assertEqual(result, 'Collaboration (pp. 25–28).\nhttps://example.test/')

    def test_moves_token_after_line_final_em_dash(self) -> None:
        result = resolve(['witty and relatable—', 'reflecting the broader community.'])

        self.assertEqual(result, 'witty and relatable—reflecting\nthe broader community.')

    def test_moves_line_initial_em_dash_and_its_token_upward(self) -> None:
        result = resolve(['witty and relatable', '—reflecting the broader community.'])

        self.assertEqual(result, 'witty and relatable—reflecting\nthe broader community.')

    def test_leaves_spaced_and_non_alphanumeric_dash_boundaries_unchanged(self) -> None:
        cases = [
            (['word –', 'next'], 'word –\nnext'),
            (['word—', '“next'], 'word—\n“next'),
            (['word', '— next'], 'word\n— next'),
            (['word', '–next'], 'word\n–next'),
            (['word!—', 'next'], 'word!—\nnext'),
            (['word', '—(next'], 'word\n—(next'),
        ]

        for lines, expected in cases:
            with self.subTest(lines=lines):
                self.assertEqual(resolve(lines), expected)

    def test_resolves_neighboring_hyphen_and_dash_boundaries_bottom_up(self) -> None:
        result = resolve(['foo-', 'bar—', 'baz remains.'])

        self.assertEqual(result, 'foobar—baz\nremains.')

    def test_does_not_move_dash_token_across_markdown_blocks(self) -> None:
        lines = [
            text_line('first block ends—', block_no=1, line_no=1),
            text_line('next block begins', block_no=2, line_no=2),
        ]

        blocks = lines_to_markdown_blocks(lines, {1: PageNumber(raw=1, visible=None)})

        self.assertEqual(
            [block.text for block in blocks],
            ['first block ends—', 'next block begins'],
        )


if __name__ == '__main__':
    unittest.main()
