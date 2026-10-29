from __future__ import annotations

import re

DEFAULT_SIZE = 200  # words. Small enough that a whole passage fits in a tool result (about 1,400 characters)
DEFAULT_OVERLAP = 30
_HEADING = re.compile(r"(?m)^(?=#{1,4} )")


def _windows(text: str, size: int, overlap: int) -> list[str]:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    if not words or words == [""]:
        return []
    out, start = [], 0
    while start < len(words):
        out.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
        start += size - overlap
    return out


def chunk_text(text: str, size: int = DEFAULT_SIZE, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    """Split into passages of about `size` words.

    Markdown headings are boundaries: a section is never cut in half just because the previous one ended
    mid-window, and short sections are grouped until a passage is full. Text with no headings (or a section
    longer than `size`) is cut into windows that overlap by `overlap` words, so a sentence split at a
    boundary still appears whole in one passage.
    """
    if size <= overlap:
        raise ValueError("size must exceed overlap")
    chunks: list[str] = []
    buf: list[str] = []
    buf_words = 0

    def flush() -> None:
        nonlocal buf, buf_words
        if buf:
            chunks.append(re.sub(r"\s+", " ", " ".join(buf)).strip())
        buf, buf_words = [], 0

    for section in (s for s in _HEADING.split(text) if s.strip()):
        n = len(section.split())
        if n > size:
            flush()
            chunks.extend(_windows(section, size, overlap))
            continue
        if buf_words + n > size:
            flush()
        buf.append(section)
        buf_words += n
    flush()
    return chunks
