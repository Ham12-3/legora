"""DOCX parsing with python-docx.

Word documents have no pages until they are rendered, so the whole document
is a single ``Page`` with zero-size word boxes. Paragraph index is preserved
as the block order; heading styles feed the section detector.
"""

import io
from typing import Any

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.types import BLOCK_SEPARATOR, Page, ParsedDocument, Word, assemble_text


def _iter_body(document: Any) -> list[tuple[str, bool]]:
    """(text, is_heading) for paragraphs and table cells, in document order."""
    out: list[tuple[str, bool]] = []
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name if para.style is not None else "") or ""
            out.append((text, style.lower().startswith(("heading", "title"))))
        elif tag == "tbl":
            table = Table(child, document)
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                line = " | ".join(c for c in cells if c)
                if line:
                    out.append((line, False))
    return out


def parse_docx(data: bytes) -> ParsedDocument:
    document = DocxDocument(io.BytesIO(data))
    items = _iter_body(document)

    text_parts: list[str] = []
    words: list[Word] = []
    pos = 0
    for i, (raw_text, _is_heading) in enumerate(items):
        # A paragraph must never contain the block separator, or the chunk
        # stage would re-derive a different block structure than we saw here.
        para_text = raw_text.replace(BLOCK_SEPARATOR, "\n")
        if i > 0:
            text_parts.append(BLOCK_SEPARATOR)
            pos += len(BLOCK_SEPARATOR)
        start = pos
        # Word boundaries for lexical highlighting; geometry is unknown.
        cursor = start
        for token in para_text.split(" "):
            if token:
                words.append(Word(cursor, cursor + len(token), 0.0, 0.0, 0.0, 0.0))
            cursor += len(token) + 1
        text_parts.append(para_text)
        pos += len(para_text)

    page = Page(number=1, text="".join(text_parts), width=0.0, height=0.0, words=words)
    return ParsedDocument(pages=[page], text=assemble_text([page]), is_ocr=False)
