"""Structure-aware chunking.

Rules, in priority order:

1. A chunk is a contiguous slice of the document text. Always. Section
   context travels alongside in ``section_path``, never spliced in.
2. Chunk boundaries fall on block boundaries, except when one block alone
   exceeds ``max_tokens``, in which case it is split at sentence ends.
3. Top-level sections (ARTICLE, "8. Indemnities") are the unit of packing.
   A section that fits in ``target_tokens`` is never split; several small
   whole sections may share a chunk. A section that does not fit is split on
   its clause boundaries, and those chunks never run into the next section.
   Either way a chunk starts on a clause boundary, and a chunk that begins
   mid-section never contains a section heading.
4. ``section_path`` is the deepest heading path common to everything in the
   chunk, so a merged chunk reports its parent, never a sibling's heading.
5. Overlap of one sentence is achieved by moving the next chunk's start
   *backwards* to the last sentence start of the previous chunk, within the
   same section. The slice invariant holds because the text is re-sliced from
   the source after the offsets are decided.
"""

import re
from dataclasses import dataclass

from app.ingestion.sections import SectionStack, detect_marker
from app.ingestion.types import (
    Block,
    ChunkDraft,
    Page,
    ParsedDocument,
    bboxes_for_span,
    estimate_tokens,
)

_SENTENCE_END = re.compile(r"(?<=[.;:!?])\s+(?=[A-Z(\d\"'])")
HARD_BOUNDARY_DEPTH = 1


@dataclass
class _Piece:
    """A block, or a sentence-split fragment of one, with its section path."""

    char_start: int
    char_end: int
    page_number: int
    section_path: str
    # The ARTICLE/PART this piece sits under, or None if the document has no
    # such level. Small sections merge only when they share it.
    root: str | None
    # Set on the first piece after a boundary the chunker must not cross.
    hard_boundary: bool


def _split_oversized(text: str, base: int, max_tokens: int) -> list[tuple[int, int]]:
    """Split a block at sentence ends so no fragment exceeds max_tokens."""
    if estimate_tokens(text) <= max_tokens:
        return [(base, base + len(text))]

    cuts = [m.end() for m in _SENTENCE_END.finditer(text)]
    if not cuts:
        # No sentence structure at all: fall back to whitespace near the limit.
        step = max_tokens * 4
        return [(base + i, base + min(i + step, len(text))) for i in range(0, len(text), step)]

    # Accumulate sentences; close the fragment just before the sentence that
    # would push it over the ceiling.
    out: list[tuple[int, int]] = []
    seg_start = 0
    prev_cut = 0
    for cut in [*cuts, len(text)]:
        if cut <= prev_cut:
            continue
        if estimate_tokens(text[seg_start:cut]) > max_tokens and prev_cut > seg_start:
            out.append((base + seg_start, base + prev_cut))
            seg_start = prev_cut
        prev_cut = cut
    out.append((base + seg_start, base + len(text)))
    return out


def _pieces(blocks: list[Block], max_tokens: int) -> list[_Piece]:
    stack = SectionStack()
    pieces: list[_Piece] = []
    for block in blocks:
        marker = detect_marker(block.text)
        hard = False
        if marker is not None:
            stack.push(marker)
            hard = marker.depth <= HARD_BOUNDARY_DEPTH
        for start, end in _split_oversized(block.text, block.char_start, max_tokens):
            pieces.append(
                _Piece(
                    char_start=start,
                    char_end=end,
                    page_number=block.page_number,
                    section_path=stack.path,
                    root=stack.root_label,
                    hard_boundary=hard,
                )
            )
            hard = False
    return pieces


def _last_sentence_start(text: str) -> int:
    """Offset of the final sentence within ``text`` (0 if it is one sentence)."""
    starts = [m.end() for m in _SENTENCE_END.finditer(text)]
    return starts[-1] if starts else 0


def _page_for_offset(pages: list[Page], offset: int) -> int:
    page_number = pages[0].number if pages else 1
    for page in pages:
        if page.char_offset <= offset:
            page_number = page.number
        else:
            break
    return page_number


def _common_path(paths: list[str]) -> str:
    parts = [p.split(" > ") if p else [] for p in paths]
    prefix: list[str] = []
    for level in zip(*parts, strict=False):
        if len(set(level)) != 1:
            break
        prefix.append(level[0])
    return " > ".join(prefix)


def _sections(pieces: list[_Piece]) -> list[list[_Piece]]:
    sections: list[list[_Piece]] = []
    for piece in pieces:
        if piece.hard_boundary or not sections:
            sections.append([])
        sections[-1].append(piece)
    return sections


def _pack(pieces: list[_Piece], text: str, target_tokens: int) -> list[list[_Piece]]:
    """Group pieces into chunks. See rule 3 in the module docstring."""

    def tokens(ps: list[_Piece]) -> int:
        return sum(estimate_tokens(text[p.char_start : p.char_end]) for p in ps)

    groups: list[list[_Piece]] = []
    buffer: list[_Piece] = []  # whole small sections awaiting a chunk

    def flush() -> None:
        nonlocal buffer
        if buffer:
            groups.append(buffer)
            buffer = []

    for section in _sections(pieces):
        if tokens(section) <= target_tokens:
            crosses_article = bool(buffer) and buffer[0].root != section[0].root
            if buffer and (crosses_article or tokens(buffer) + tokens(section) > target_tokens):
                flush()
            buffer.extend(section)
            continue

        flush()
        current: list[_Piece] = []
        for piece in section:
            if current and tokens(current) + tokens([piece]) > target_tokens:
                groups.append(current)
                current = []
            current.append(piece)
        if current:
            groups.append(current)
    flush()
    return groups


def chunk_document(
    parsed: ParsedDocument, *, target_tokens: int, max_tokens: int
) -> list[ChunkDraft]:
    pieces = _pieces(parsed.blocks, max_tokens)
    if not pieces:
        return []

    groups = _pack(pieces, parsed.text, target_tokens)

    # Resolve offsets, apply one-sentence backward overlap, re-slice.
    drafts: list[ChunkDraft] = []
    for ordinal, group in enumerate(groups):
        start = group[0].char_start
        end = group[-1].char_end
        if ordinal > 0 and not group[0].hard_boundary:
            prev_group = groups[ordinal - 1]
            same_section = (
                prev_group[-1].section_path.split(" > ")[:1]
                == group[0].section_path.split(" > ")[:1]
            )
            if same_section:
                prev = drafts[-1]
                overlap_start = prev.char_start + _last_sentence_start(
                    parsed.text[prev.char_start : prev.char_end]
                )
                if (
                    overlap_start < start
                    and estimate_tokens(parsed.text[overlap_start:end]) <= max_tokens
                ):
                    start = overlap_start

        text = parsed.text[start:end]
        drafts.append(
            ChunkDraft(
                ordinal=ordinal,
                text=text,
                section_path=_common_path([p.section_path for p in group]),
                char_start=start,
                char_end=end,
                page_start=_page_for_offset(parsed.pages, start),
                page_end=_page_for_offset(parsed.pages, max(start, end - 1)),
                token_count=estimate_tokens(text),
                bboxes=bboxes_for_span(parsed.pages, start, end),
            )
        )
    return drafts
