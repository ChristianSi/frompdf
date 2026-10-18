"""Format the front matter around a document title.

Subtitles, author names, and chapter labels near a title are often set large
or bold, so font-size heuristics turn them into headings of their own. They are
rendered as bold paragraphs instead, leaving heading levels to the title and
the document's sections.
"""

import re

from frompdf.models import Block, Heading, StrongParagraph
from frompdf.segmentation import NUMBERED_OR_BULLETED_START_PATTERN

# A paragraph this long is body text, such as an abstract, ending the front
# matter. Bylines, affiliations, and dates are much shorter.
MAX_FRONT_MATTER_PARAGRAPH_CHARACTERS = 200

# A label such as "CHAPTER 10" or "Part II" above the actual title.
CHAPTER_LABEL_PATTERN = re.compile(r'[^\W\d_]{3,}\s+(?:\d+|[IVXLCDM]+)[.:]?')


def visible_text(block_obj: Block) -> str:
    """Return block text without superscripts and subscripts, with collapsed whitespace."""
    characters = list(block_obj.text)
    for run in block_obj.ranges:
        if not run.is_script:
            continue
        characters[run.start : run.end] = ' ' * (run.end - run.start)
    return ' '.join(''.join(characters).split())


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


def is_section_like(block_obj: Block) -> bool:
    """Return whether a heading reads like a section heading, such as "Abstract" or "1 Methods"."""
    text = visible_text(block_obj)
    return len(text.split()) < 2 or bool(NUMBERED_OR_BULLETED_START_PATTERN.match(text))


def front_matter_level(block_list: list[Block], region: list[int]) -> int | None:
    """Return the heading level of a title's front matter, if it has one.

    The front matter starts with a heading directly below the title, such as a
    subtitle or the first author name. A section heading can follow a title
    directly as well, so its level only counts when it is used nowhere else in
    the document, or when the heading does not read like a section heading.
    """
    first = block_list[region[0]] if region else None
    if not isinstance(first, Heading):
        return None
    region_set = set(region)
    level_only_here = all(
        index in region_set
        for index, block in enumerate(block_list)
        if isinstance(block, Heading) and block.level == first.level
    )
    return first.level if level_only_here or not is_section_like(first) else None


def strong_paragraph(source: Block) -> StrongParagraph:
    """Return a bold paragraph retaining the source block's text and line breaks."""
    return StrongParagraph(
        text=source.text,
        ranges=source.ranges,
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
    becomes the title. The front matter follows the title on its page, until
    body text or another heading as high as the title. All of its headings at
    the front-matter level, such as a subtitle or author names alternating with
    affiliations, are demoted.
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
        level = front_matter_level(block_list, region)
        for index in region:
            block = block_list[index]
            if isinstance(block, Heading) and block.level == level:
                block_list[index] = strong_paragraph(source_blocks[index])
        dropped.update(
            index
            for index in region
            if not isinstance(block_list[index], Heading)
            and not has_alphanumeric(block_list[index].text)
        )
    return dropped
