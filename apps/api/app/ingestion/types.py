"""Shapes shared across the ingestion stages.

The single most important invariant in the codebase (CLAUDE.md rule 3):

    assemble_text(pages)[chunk.char_start:chunk.char_end] == chunk.text

Every offset in this package is either page-local (``Word``) or
document-global (``Block``, ``ChunkDraft``), and the conversion between the
two goes through ``Page.char_offset`` only.
"""

from dataclasses import dataclass, field

PAGE_SEPARATOR = "\n"


@dataclass(frozen=True)
class Word:
    """One token of page text with its bounding box in PDF points.

    Offsets are relative to the owning page's ``text``. DOCX has no geometry;
    its words carry a zero bbox and the UI highlights by paragraph instead.
    """

    start: int
    end: int
    x0: float
    y0: float
    x1: float
    y1: float

    def as_row(self) -> list[float]:
        return [self.start, self.end, self.x0, self.y0, self.x1, self.y1]


@dataclass
class Page:
    number: int  # 1-based
    text: str
    width: float
    height: float
    words: list[Word] = field(default_factory=list)
    is_ocr: bool = False
    # Filled in by assemble_text: where this page starts in the document text.
    char_offset: int = 0


@dataclass(frozen=True)
class Block:
    """A paragraph-sized unit of text with document-global offsets.

    Blocks are what the chunker sees. For PDFs they are PyMuPDF text blocks;
    for DOCX they are paragraphs and table cells.
    """

    text: str
    char_start: int
    char_end: int
    page_number: int


BLOCK_SEPARATOR = "\n\n"


@dataclass
class ParsedDocument:
    pages: list[Page]
    text: str  # assemble_text(pages), cached
    is_ocr: bool

    @property
    def blocks(self) -> list[Block]:
        return blocks_from_pages(self.pages)


def blocks_from_pages(pages: list[Page]) -> list[Block]:
    """Re-derive paragraph blocks from page text.

    Parsers write page text with ``BLOCK_SEPARATOR`` between paragraphs, so
    the chunk stage can rebuild the block structure from ``document_pages``
    rows alone and retry without re-parsing.
    """
    blocks: list[Block] = []
    for page in pages:
        pos = 0
        for raw in page.text.split(BLOCK_SEPARATOR):
            if raw.strip():
                lead = len(raw) - len(raw.lstrip())
                trail = len(raw) - len(raw.rstrip())
                start = page.char_offset + pos + lead
                end = page.char_offset + pos + len(raw) - trail
                blocks.append(
                    Block(text=raw.strip(), char_start=start, char_end=end, page_number=page.number)
                )
            pos += len(raw) + len(BLOCK_SEPARATOR)
    return blocks


def assemble_text(pages: list[Page]) -> str:
    """Join pages and stamp each with its document-global start offset."""
    offset = 0
    parts: list[str] = []
    for i, page in enumerate(pages):
        if i > 0:
            offset += len(PAGE_SEPARATOR)
        page.char_offset = offset
        parts.append(page.text)
        offset += len(page.text)
    return PAGE_SEPARATOR.join(parts)


@dataclass
class ChunkDraft:
    ordinal: int
    text: str
    section_path: str
    char_start: int
    char_end: int
    page_start: int
    page_end: int
    token_count: int
    bboxes: dict[str, list[list[float]]] = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """Cheap, offline, deterministic. Legal English runs ~4.2 chars/token.

    Good enough to hit a soft target; swap for a real tokenizer if the
    ``chunk_max_tokens`` ceiling ever needs to be exact.
    """
    return max(1, (len(text) + 3) // 4)
