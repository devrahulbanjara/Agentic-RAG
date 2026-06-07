import re


def is_noise(text: str, min_chars: int) -> bool:
    """Decide if a text string is junk that should not become a chunk.

    Checks for: too short (below min_chars), starts with "DRAFT",
    starts with "Keywords:", or is a bare email address.

    Args:
        text: The raw text to check.
        min_chars: Minimum character count. Anything shorter is noise.

    Returns:
        True if the text should be skipped, False if it's real content.
    """
    stripped = text.strip()
    if len(stripped) < min_chars:
        return True
    if re.match(r"^DRAFT\b", stripped):
        return True
    if re.match(r"^Keywords?:", stripped):
        return True
    if re.match(r"^[\w.\-]+@[\w.\-]+\.\w+$", stripped):
        return True
    return False


def table_to_markdown(rows: list[list[str]]) -> str:
    """Turn a list of rows into a markdown table string.

    First row is treated as the header. A separator row (| --- | --- |)
    is added after the header. Each cell is converted to str.

    Args:
        rows: List of rows, where each row is a list of cell values.
              Example: [["Model", "BLEU"], ["Transformer", "28.4"]]

    Returns:
        A markdown table string. Empty string if rows is empty.
    """
    if not rows:
        return ""
    header = rows[0]
    markdown = "| " + " | ".join(str(cell) for cell in header) + " |\n"
    markdown += "| " + " | ".join("---" for _ in header) + " |\n"
    for row in rows[1:]:
        markdown += "| " + " | ".join(str(cell) for cell in row) + " |\n"
    return markdown.strip()


def should_merge(current: str, next_text: str, max_chars: int) -> bool:
    """Decide if two consecutive paragraph texts should be merged into one chunk.

    Joins them with a blank line ("\\n\\n") and checks if the total length
    fits within max_chars.

    Args:
        current: The text accumulated so far (may already be multiple merged paragraphs).
        next_text: The next paragraph's text.
        max_chars: Maximum allowed character count for the combined result.

    Returns:
        True if combined length <= max_chars, False otherwise.
    """
    return len(current + "\n\n" + next_text) <= max_chars


def merge_short_paragraphs(texts: list[str], max_chars: int) -> list[str]:
    """Take a list of paragraph texts and merge consecutive short ones.

    Walks left-to-right through the list. Keeps a buffer starting with the
    first paragraph. For each next paragraph, calls should_merge to check
    if the buffer + next paragraph fits within max_chars. If yes, joins
    them with a blank line. If no, saves the buffer as a finished chunk
    and starts a new buffer with the next paragraph.

    The first paragraph has nothing before it — becomes the initial buffer.
    The last paragraph has nothing after it — gets saved at the end.
    Non-paragraph elements (tables, figures, equations) are not in this list —
    they are handled separately. When one appears, all collected paragraphs
    are merged and saved before the non-paragraph element is processed.

    Args:
        texts: List of paragraph text strings from one section, in reading order.
               Only contains paragraphs that passed the is_noise filter.
        max_chars: Maximum character count for a merged result.

    Returns:
        List of text strings, same or fewer than input. Each string is either
        a single paragraph or multiple short paragraphs joined with "\\n\\n".
    """
    if not texts:
        return []
    merged: list[str] = []
    buffer = texts[0]
    for text in texts[1:]:
        if should_merge(buffer, text, max_chars):
            buffer = buffer + "\n\n" + text
        else:
            merged.append(buffer)
            buffer = text
    merged.append(buffer)
    return merged
