"""PDF parsing with PyMuPDF, keeping word-level geometry.

Page text is *built from the words*, not taken from ``get_text("text")``,
so that every word's offset into the page text is exact by construction:
words in a line are joined with single spaces, lines with "\\n", and blocks
with a blank line. That construction is the whole reason citations can be
highlighted later.
"""

import logging
from collections.abc import Iterable

import pymupdf

from app.config import get_settings
from app.ingestion.types import BLOCK_SEPARATOR, Page, ParsedDocument, Word, assemble_text

log = logging.getLogger(__name__)

# (x0, y0, x1, y1, "word", block_no, line_no, word_no)
_RawWord = tuple[float, float, float, float, str, int, int, int]


def _build_page(number: int, width: float, height: float, raw: Iterable[_RawWord]) -> Page:
    words: list[Word] = []
    text_parts: list[str] = []
    pos = 0
    prev_block = prev_line = None

    for x0, y0, x1, y1, token, block_no, line_no, _ in raw:
        token = token.strip()
        if not token:
            continue
        if prev_block is None:
            pass
        elif block_no != prev_block:
            text_parts.append(BLOCK_SEPARATOR)
            pos += len(BLOCK_SEPARATOR)
        elif line_no != prev_line:
            text_parts.append("\n")
            pos += 1
        else:
            text_parts.append(" ")
            pos += 1

        words.append(Word(pos, pos + len(token), x0, y0, x1, y1))
        text_parts.append(token)
        pos += len(token)
        prev_block, prev_line = block_no, line_no

    return Page(number=number, text="".join(text_parts), width=width, height=height, words=words)


def _ocr_words(page: pymupdf.Page) -> list[_RawWord] | None:
    settings = get_settings()
    if not settings.ocr_enabled:
        return None
    try:
        textpage = page.get_textpage_ocr(language=settings.ocr_language, dpi=300, full=True)
        words: list[_RawWord] = page.get_text("words", textpage=textpage)
        return words
    except Exception as exc:  # Tesseract missing, tessdata missing, etc.
        log.warning("OCR unavailable for page %d: %s", page.number, exc)
        return None


def parse_pdf(data: bytes) -> ParsedDocument:
    settings = get_settings()
    pages: list[Page] = []
    any_ocr = False

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for index, page in enumerate(doc):
            raw: list[_RawWord] = page.get_text("words")
            extractable = sum(len(w[4].strip()) for w in raw)
            is_ocr = False
            if extractable < settings.ocr_min_chars_per_page:
                # Scanned or image-only. Even if OCR is off or fails we keep the
                # flag so the UI can warn that this page has no reliable text.
                is_ocr = True
                any_ocr = True
                ocr = _ocr_words(page)
                if ocr:
                    raw = ocr

            rect = page.rect
            built = _build_page(index + 1, rect.width, rect.height, raw)
            built.is_ocr = is_ocr
            pages.append(built)

    return ParsedDocument(pages=pages, text=assemble_text(pages), is_ocr=any_ocr)
