from collections import Counter
from collections.abc import Iterable
from unicodedata import category, normalize

# These characters can represent a hyphen within an extracted word. Other dash
# and minus characters are deliberately excluded because they generally express
# punctuation or mathematical operators instead of word joining.
VISIBLE_WORD_HYPHENS = {'-', '\u2010', '\u2011'}
SOFT_HYPHEN = '\u00ad'
WORD_HYPHENS = VISIBLE_WORD_HYPHENS | {SOFT_HYPHEN}


def is_word_base(char: str) -> bool:
    """Return whether a character can begin a dictionary word."""
    return char.isalnum()


def is_word_continuation(char: str) -> bool:
    """Return whether a character can continue a dictionary word."""
    return char.isalnum() or category(char).startswith('M')


def canonical_word(word: str) -> str:
    """Return the case-folded dictionary representation of one word."""
    return normalize('NFC', exact_word(word).casefold())


def exact_word(word: str) -> str:
    """Return the case-preserving normalized representation of one word."""
    normalized = normalize('NFC', word)
    return normalize(
        'NFC',
        ''.join(
            '' if char == SOFT_HYPHEN else '-' if char in VISIBLE_WORD_HYPHENS else char
            for char in normalized
        ),
    )


def exact_words_in_text(text: str) -> Iterable[str]:
    """Yield case-preserving words while retaining only word-internal hyphens."""
    char_index = 0

    while char_index < len(text):
        if not is_word_base(text[char_index]):
            char_index += 1
            continue

        word_chars = [text[char_index]]
        char_index += 1

        while char_index < len(text):
            char = text[char_index]
            if is_word_continuation(char):
                word_chars.append(char)
                char_index += 1
                continue
            if (
                char in WORD_HYPHENS
                and char_index + 1 < len(text)
                and is_word_base(text[char_index + 1])
            ):
                word_chars.append(char)
                char_index += 1
                continue
            break

        yield exact_word(''.join(word_chars))


def words_in_text(text: str) -> Iterable[str]:
    """Yield case-folded words while retaining only word-internal hyphens."""
    return (canonical_word(word) for word in exact_words_in_text(text))


def document_word_counts(line_texts: Iterable[str]) -> Counter[str]:
    """Count normalized words in the unmodified document text."""
    return Counter(word for text in line_texts for word in words_in_text(text))


def is_mixed_case_word(word: str) -> bool:
    """Return whether a word has lowercase letters and an uppercase inner letter."""
    return any(char.islower() for char in word) and any(
        char_index > 0 and char.isupper() for char_index, char in enumerate(word)
    )


def document_mixed_case_words(line_texts: Iterable[str]) -> set[str]:
    """Collect exact-case camelCase and PascalCase words from the document."""
    return {
        word
        for text in line_texts
        for word in exact_words_in_text(text)
        if is_mixed_case_word(word)
    }


def strip_leading_wrapping_punctuation(text: str) -> str:
    """Strip punctuation that wraps, rather than belongs to, a left fragment."""
    first_word_index = 0
    while (
        first_word_index < len(text)
        and category(text[first_word_index]).startswith('P')
        and text[first_word_index] not in WORD_HYPHENS
    ):
        first_word_index += 1
    return text[first_word_index:]


def initial_lexical_fragment(text: str) -> str | None:
    """Return a token's initial word fragment without attached annotations."""
    if not text or not is_word_base(text[0]):
        return None

    fragment_end = 1
    while fragment_end < len(text):
        char = text[fragment_end]
        if is_word_continuation(char) or category(char).startswith('S'):
            fragment_end += 1
            continue
        if (
            char in WORD_HYPHENS
            and fragment_end + 1 < len(text)
            and is_word_base(text[fragment_end + 1])
        ):
            fragment_end += 1
            continue
        break

    return text[:fragment_end]


def exact_dictionary_candidate(fragment: str) -> str | None:
    """Return an exact-case key when a candidate is exactly one lexical word."""
    word_list = list(exact_words_in_text(fragment))
    normalized_fragment = exact_word(fragment)
    if len(word_list) != 1 or word_list[0] != normalized_fragment:
        return None
    return word_list[0]


def dictionary_candidate(fragment: str) -> str | None:
    """Return a dictionary key when a candidate is exactly one lexical word."""
    exact_candidate = exact_dictionary_candidate(fragment)
    if exact_candidate is None:
        return None
    return canonical_word(exact_candidate)


def is_all_caps(text: str) -> bool:
    """Return whether all cased letters in text are uppercase."""
    cased_chars = [char for char in text if char.lower() != char.upper()]
    return bool(cased_chars) and all(char.isupper() for char in cased_chars)


def contains_nonletter(text: str) -> bool:
    """Return whether a word fragment contains digits, symbols, or punctuation."""
    return any(
        not category(char).startswith(('L', 'M')) and char not in WORD_HYPHENS for char in text
    )


def should_keep_boundary_hyphen(
    left_fragment: str,
    right_fragment: str,
    boundary_hyphen: str,
    word_counts: Counter[str],
    mixed_case_words: set[str],
) -> bool:
    """Decide whether a line-boundary hyphen belongs to the complete word."""
    combined_word = left_fragment + right_fragment
    if right_fragment[0].isupper() and not is_all_caps(combined_word):
        exact_candidate = exact_dictionary_candidate(combined_word)
        if exact_candidate is not None and exact_candidate in mixed_case_words:
            return False
        return boundary_hyphen != SOFT_HYPHEN

    unhyphenated_key = dictionary_candidate(left_fragment + right_fragment)
    hyphenated_key = dictionary_candidate(left_fragment + '-' + right_fragment)
    unhyphenated_count = word_counts[unhyphenated_key] if unhyphenated_key is not None else 0
    hyphenated_count = word_counts[hyphenated_key] if hyphenated_key is not None else 0

    if unhyphenated_count or hyphenated_count:
        # Exact evidence wins; ties retain the source hyphen.
        return hyphenated_count >= unhyphenated_count

    if boundary_hyphen == '\u2011':
        return True
    if boundary_hyphen == SOFT_HYPHEN:
        return False
    if any(char in VISIBLE_WORD_HYPHENS for char in left_fragment + right_fragment):
        return True

    return contains_nonletter(combined_word)


def split_boundary_fragments(left_line: str, right_line: str) -> tuple[str, str, str, str] | None:
    """Return the fragments and right token at an eligible line boundary."""
    if not left_line or left_line[-1] not in WORD_HYPHENS:
        return None

    left_without_hyphen = left_line[:-1]
    if not left_without_hyphen or left_without_hyphen[-1].isspace():
        return None

    left_token_start = len(left_without_hyphen)
    while left_token_start and not left_without_hyphen[left_token_start - 1].isspace():
        left_token_start -= 1
    raw_left_fragment = left_without_hyphen[left_token_start:]
    left_fragment = strip_leading_wrapping_punctuation(raw_left_fragment)
    if not left_fragment or not any(is_word_base(char) for char in left_fragment):
        return None

    stripped_right_line = right_line.lstrip()
    if not stripped_right_line:
        return None
    raw_right_token = stripped_right_line.split(maxsplit=1)[0]
    right_fragment = initial_lexical_fragment(raw_right_token)
    if right_fragment is None:
        return None

    return left_fragment, right_fragment, left_line[-1], raw_right_token


def unhyphenate_block_lines(
    line_texts: Iterable[str], word_counts: Counter[str], mixed_case_words: set[str]
) -> str:
    """Resolve wrapped words within one Markdown block and retain its line breaks."""
    rewritten_lines = list(line_texts)
    consumed_line_indexes: set[int] = set()

    for line_index in range(len(rewritten_lines) - 1):
        fragments = split_boundary_fragments(
            rewritten_lines[line_index], rewritten_lines[line_index + 1]
        )
        if fragments is None:
            continue

        left_fragment, right_fragment, boundary_hyphen, raw_right_token = fragments
        keep_hyphen = should_keep_boundary_hyphen(
            left_fragment,
            right_fragment,
            boundary_hyphen,
            word_counts,
            mixed_case_words,
        )
        if keep_hyphen:
            rewritten_lines[line_index] += raw_right_token
        else:
            rewritten_lines[line_index] = rewritten_lines[line_index][:-1] + raw_right_token

        right_remainder = rewritten_lines[line_index + 1].lstrip()[len(raw_right_token) :].lstrip()
        rewritten_lines[line_index + 1] = right_remainder
        if not right_remainder:
            consumed_line_indexes.add(line_index + 1)

    return '\n'.join(
        line_text
        for line_index, line_text in enumerate(rewritten_lines)
        if line_index not in consumed_line_indexes or line_text
    )
