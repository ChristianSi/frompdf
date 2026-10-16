"""Format the front matter around a document title.

Subtitles, author names, and chapter labels near a title are often set large
or bold, so font-size heuristics turn them into headings of their own. They are
rendered as bold paragraphs instead, leaving heading levels to the title and
the document's sections.
"""

import re

from frompdf.models import Block, Heading, StrongParagraph

# A paragraph this long is body text, such as an abstract, ending the front
# matter. Bylines, affiliations, and dates are much shorter.
MAX_FRONT_MATTER_PARAGRAPH_CHARACTERS = 200

# Lowercase particles within personal names.
NAME_PARTICLES = frozenset(
    {'da', 'das', 'de', 'del', 'della', 'den', 'der', 'di', 'do', 'dos', 'du', 'la', 'le'}
    | {'ten', 'ter', 'van', 'von', 'zu'}
)
NAME_SEPARATOR_PATTERN = re.compile(r'\s*(?:[,;&]|\band\b)\s*')
NAME_INITIALS_PATTERN = re.compile(r'(?:[^\W\d_]\.-?)+')
NAME_WORD_PATTERN = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
# Affiliation marks and symbols, such as digits, asterisks, daggers, or ✉.
NAME_MARK_PATTERN = re.compile(r"[^\w\s.,;&'’-]|\d")
MIN_NAME_WORDS = 2
MAX_NAME_WORDS = 5

# A label such as "CHAPTER 10" or "Part II" above the actual title.
CHAPTER_LABEL_PATTERN = re.compile(r'[^\W\d_]{3,}\s+(?:\d+|[IVXLCDM]+)[.:]?')


def visible_text(block_obj: Block) -> str:
    """Return block text without superscripts and subscripts, with collapsed whitespace."""
    characters = list(block_obj.text)
    for run in block_obj.scripts:
        characters[run.start : run.end] = ' ' * (run.end - run.start)
    return ' '.join(''.join(characters).split())


def is_name_word(word: str) -> bool:
    """Return whether a word can be part of a personal name."""
    return (
        word in NAME_PARTICLES
        or bool(NAME_INITIALS_PATTERN.fullmatch(word))
        or (len(word) >= 2 and word[0].isupper() and bool(NAME_WORD_PATTERN.fullmatch(word)))
    )


def looks_like_names(block_obj: Block) -> bool:
    """Return whether a block consists of one or more personal names.

    Names are separated by commas, semicolons, ampersands, or "and". Each has a
    few capitalized words, initials, or particles, including at least one full
    word. Affiliation marks are ignored.
    """
    text = NAME_MARK_PATTERN.sub(' ', visible_text(block_obj))
    names = [name.split() for name in NAME_SEPARATOR_PATTERN.split(text)]
    names = [words for words in names if words]
    return bool(names) and all(
        MIN_NAME_WORDS <= len(words) <= MAX_NAME_WORDS
        and all(is_name_word(word) for word in words)
        and any(word[0].isupper() and not word.endswith('.') for word in words)
        for words in names
    )


def is_chapter_label(block_obj: Block) -> bool:
    """Return whether a block is a label such as "CHAPTER 10" rather than a title."""
    return bool(CHAPTER_LABEL_PATTERN.fullmatch(visible_text(block_obj)))


def has_alphanumeric(text: str) -> bool:
    """Return whether text contains letters or digits, unlike ornaments and rules."""
    return any(character.isalnum() for character in text)


def title_indices(block_list: list[Block]) -> list[int]:
    """Return the indices of likely document titles.

    These are the first heading and the first top-level heading, which can
    differ when a cover page precedes the article.
    """
    headings = [
        (index, block) for index, block in enumerate(block_list) if isinstance(block, Heading)
    ]
    if not headings:
        return []
    indices = [headings[0][0]]
    top_level = next((index for index, block in headings if block.level == 1), None)
    if top_level is not None and top_level != indices[0]:
        indices.append(top_level)
    return indices


def front_matter_region(block_list: list[Block], title_index: int) -> list[int]:
    """Return the indices of blocks following a title before its page's body text."""
    title = block_list[title_index]
    assert isinstance(title, Heading)
    region: list[int] = []
    for index in range(title_index + 1, len(block_list)):
        block = block_list[index]
        if block.start_page.raw != title.start_page.raw:
            break
        if isinstance(block, Heading):
            if block.level <= title.level:
                break
        elif len(block.text) > MAX_FRONT_MATTER_PARAGRAPH_CHARACTERS:
            break
        region.append(index)
    return region


def strong_paragraph(source: Block) -> StrongParagraph:
    """Return a bold paragraph retaining the source block's text and line breaks."""
    return StrongParagraph(
        text=source.text,
        scripts=source.scripts,
        start_page=source.start_page,
        end_page=source.end_page,
        font_size=source.font_size,
        avg_weight=source.avg_weight,
        fragments=source.fragments,
    )


def format_front_matter(block_list: list[Block], source_blocks: list[Block]) -> set[int]:
    """Render subtitles, author names, and chapter labels near titles in bold.

    source_blocks holds each block as it was before heading detection, which
    collapses line breaks. Blocks are replaced in place. Returns the indices of
    decorative blocks without letters or digits within the front matter, which
    should be dropped.

    A chapter label directly followed by a heading is demoted, and that heading
    becomes the title. Following the title on its page, until body text or
    another heading as high as the title, the first block is a subtitle if it is
    a heading of a level used nowhere else in the document. A heading level is
    demoted as a whole when all of its headings there look like personal names.
    """
    dropped: set[int] = set()
    for title_index in title_indices(block_list):
        title = block_list[title_index]
        following_index = title_index + 1
        if (
            isinstance(title, Heading)
            and is_chapter_label(title)
            and following_index < len(block_list)
            and isinstance(block_list[following_index], Heading)
            and block_list[following_index].start_page.raw == title.start_page.raw
        ):
            block_list[title_index] = strong_paragraph(source_blocks[title_index])
            title_index = following_index
            title = block_list[title_index]
        if not isinstance(title, Heading):
            continue

        region = front_matter_region(block_list, title_index)
        region_set = set(region)
        level_indices: dict[int, list[int]] = {}
        for index, block in enumerate(block_list):
            if isinstance(block, Heading):
                level_indices.setdefault(block.level, []).append(index)

        demoted: set[int] = set()
        first = block_list[region[0]] if region else None
        if (
            isinstance(first, Heading)
            and first.level > title.level
            and set(level_indices[first.level]) <= region_set
        ):
            demoted.add(region[0])
        for level, indices in level_indices.items():
            in_region = [index for index in indices if index in region_set]
            if (
                level > title.level
                and in_region
                and all(looks_like_names(block_list[index]) for index in in_region)
            ):
                demoted.update(in_region)
        for index in demoted:
            block_list[index] = strong_paragraph(source_blocks[index])
        dropped.update(
            index
            for index in region
            if not isinstance(block_list[index], Heading)
            and not has_alphanumeric(block_list[index].text)
        )
    return dropped
