"""Pull plain text out of an upload. Bounded on every axis: hostile files must not exhaust the server."""
from __future__ import annotations

import csv
import io
from pathlib import PurePath

MAX_BYTES = 10_000_000
MAX_PDF_PAGES = 300
MAX_CHARS = 2_000_000
MAX_SHEET_ROWS = 5_000
MAX_SLIDES = 200
TEXT_TYPES = {".txt", ".md", ".markdown", ".csv"}
SUPPORTED = TEXT_TYPES | {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"}


class UnsupportedType(ValueError):
    pass


class ParseError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED:
        raise UnsupportedType(
            f"{ext or 'that file type'} is not supported; use .txt, .md, .csv, .pdf, "
            ".docx, .xlsx or .pptx"
        )
    if ext in {".doc", ".xls", ".ppt"}:
        raise UnsupportedType(
            f"{ext} (legacy Office) is not supported; export as "
            f"{'.docx' if ext == '.doc' else '.xlsx' if ext == '.xls' else '.pptx'} instead"
        )
    try:
        if ext in {".txt", ".md", ".markdown"}:
            text = data.decode("utf-8", errors="replace")
        elif ext == ".csv":
            text = _csv_text(data)
        elif ext == ".pdf":
            text = _pdf_text(data)
        elif ext == ".docx":
            text = _docx_text(data)
        elif ext == ".xlsx":
            text = _xlsx_text(data)
        else:
            text = _pptx_text(data)
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


def _csv_text(data: bytes) -> str:
    raw = data.decode("utf-8-sig", errors="replace")
    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(raw), dialect)
    rows: list[str] = []
    for i, row in enumerate(reader):
        if i >= MAX_SHEET_ROWS:
            rows.append(f"… truncated after {MAX_SHEET_ROWS} rows")
            break
        rows.append("\t".join(cell.replace("\t", " ").replace("\n", " ") for cell in row))
    return "\n".join(rows)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ParseError("encrypted PDFs cannot be read")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ParseError(f"PDFs over {MAX_PDF_PAGES} pages are not supported")
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _docx_text(data: bytes) -> str:
    from docx import Document as Docx

    doc = Docx(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    parts += [c.text for t in doc.tables for row in t.rows for c in row.cells]
    return "\n".join(parts)


def _xlsx_text(data: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts: list[str] = []
    try:
        for sheet in wb.worksheets:
            parts.append(f"## {sheet.title}")
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i >= MAX_SHEET_ROWS:
                    parts.append(f"… truncated after {MAX_SHEET_ROWS} rows")
                    break
                cells = [("" if c is None else str(c)).replace("\t", " ").replace("\n", " ") for c in row]
                if any(cells):
                    parts.append("\t".join(cells))
            parts.append("")
    finally:
        wb.close()
    return "\n".join(parts)


def _pptx_text(data: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    if len(prs.slides) > MAX_SLIDES:
        raise ParseError(f"decks over {MAX_SLIDES} slides are not supported")
    parts: list[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        parts.append(f"## Slide {i}")
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = (shape.text or "").strip()
                if text:
                    parts.append(text)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [cell.text.strip().replace("\t", " ").replace("\n", " ") for cell in row.cells]
                    if any(cells):
                        parts.append("\t".join(cells))
        parts.append("")
    return "\n".join(parts)
