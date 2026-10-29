"""Pull plain text out of an upload. Bounded on every axis: hostile files must not exhaust the server."""
from __future__ import annotations

import io
from pathlib import PurePath

MAX_BYTES = 10_000_000
MAX_PDF_PAGES = 300
MAX_CHARS = 2_000_000
TEXT_TYPES = {".txt", ".md", ".markdown"}
SUPPORTED = TEXT_TYPES | {".pdf", ".docx"}


class UnsupportedType(ValueError):
    pass


class ParseError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED:
        raise UnsupportedType(f"{ext or 'that file type'} is not supported; use .txt, .md, .pdf or .docx")
    try:
        if ext in TEXT_TYPES:
            text = data.decode("utf-8", errors="replace")
        elif ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ParseError("encrypted PDFs cannot be read")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ParseError(f"PDFs over {MAX_PDF_PAGES} pages are not supported")
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        else:
            from docx import Document as Docx

            doc = Docx(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            parts += [c.text for t in doc.tables for row in t.rows for c in row.cells]
            text = "\n".join(parts)
    except ParseError:
        raise
    except Exception as e:
        raise ParseError(f"could not read the file ({type(e).__name__})") from e
    text = text.replace("\x00", "")
    if not text.strip():
        raise ParseError("no text found in the file (a scanned image PDF needs OCR first)")
    if len(text) > MAX_CHARS:
        raise ParseError("the document has too much text")
    return text
