# ruff: noqa: RUF001 -- the translation table below is a list of the ambiguous characters
"""Citation verification: the difference between a legal tool and a toy.

The model returns, per answer, a verbatim quote and the passage it came from.
Nothing about that is trusted. Each quote is located in the source text in
Python:

    exact      the quote appears in the named passage (whitespace and typographic
               quotes normalised)
    fuzzy      a window of the named passage matches at >= threshold similarity;
               the citation carries the corrected source text
    relocated  the quote appears verbatim elsewhere in the document; the model
               named the wrong passage, the text is still real

Anything else is dropped, and the cell is marked unverified. Offsets are
document-global so the citation maps straight to a page and word boxes.
"""

import difflib
import unicodedata
from dataclasses import dataclass

from app.ingestion.types import ParsedDocument, bboxes_for_span
from app.models.chunk import Chunk

_QUOTE_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "–": "-",
        "—": "-",
        "−": "-",
        " ": " ",
    }
)


@dataclass(frozen=True)
class Normalized:
    text: str
    index_map: list[int]  # normalized index -> original index


def normalize(text: str) -> Normalized:
    """Collapse whitespace runs to one space and fold typographic punctuation,
    keeping a map back to original offsets."""
    out: list[str] = []
    index_map: list[int] = []
    pending_space = False
    for i, ch in enumerate(unicodedata.normalize("NFKC", text).translate(_QUOTE_MAP)):
        if ch.isspace():
            pending_space = bool(out)
            continue
        if pending_space:
            out.append(" ")
            index_map.append(i)
            pending_space = False
        out.append(ch)
        index_map.append(i)
    return Normalized("".join(out), index_map)


def _map_span(norm: Normalized, start: int, end: int) -> tuple[int, int]:
    if end <= start:
        return norm.index_map[start], norm.index_map[start] + 1
    return norm.index_map[start], norm.index_map[end - 1] + 1


@dataclass(frozen=True)
class VerifiedSpan:
    chunk: Chunk | None
    quoted_text: str  # the corrected source slice
    char_start: int  # document-global
    char_end: int
    page: int
    bboxes: dict[str, list[list[float]]]
    match_kind: str  # exact | fuzzy | relocated
    similarity: float


def _fuzzy_locate(haystack: str, needle: str, threshold: float) -> tuple[int, int, float] | None:
    """Best window of ``haystack`` resembling ``needle`` at >= threshold."""
    n = len(needle)
    if n < 8 or len(haystack) < n // 2:
        return None
    best: tuple[int, int, float] | None = None
    step = max(1, n // 12)
    for width in {n, int(n * 0.9), int(n * 1.1)}:
        if width <= 0 or width > len(haystack):
            continue
        for start in range(0, len(haystack) - width + 1, step):
            window = haystack[start : start + width]
            matcher = difflib.SequenceMatcher(None, window, needle, autojunk=False)
            if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
                continue
            ratio = matcher.ratio()
            if ratio >= threshold and (best is None or ratio > best[2]):
                best = (start, start + width, ratio)
    return best


def verify_quote(
    quote_text: str,
    named_chunk: Chunk | None,
    *,
    parsed: ParsedDocument,
    chunks: list[Chunk],
    fuzzy_threshold: float,
) -> VerifiedSpan | None:
    needle = normalize(quote_text).text.strip()
    if len(needle) < 3:
        return None

    def build(
        chunk: Chunk | None, doc_start: int, doc_end: int, kind: str, sim: float
    ) -> VerifiedSpan:
        page = _page_for(parsed, doc_start)
        return VerifiedSpan(
            chunk=chunk,
            quoted_text=parsed.text[doc_start:doc_end],
            char_start=doc_start,
            char_end=doc_end,
            page=page,
            bboxes=bboxes_for_span(parsed.pages, doc_start, doc_end),
            match_kind=kind,
            similarity=sim,
        )

    # 1. Exact, in the named passage.
    if named_chunk is not None:
        norm = normalize(named_chunk.text)
        idx = norm.text.find(needle)
        if idx >= 0:
            s, e = _map_span(norm, idx, idx + len(needle))
            return build(
                named_chunk, named_chunk.char_start + s, named_chunk.char_start + e, "exact", 1.0
            )

    # 2. Relocated: exact somewhere else in the document. The words are real;
    #    only the passage label was wrong.
    doc_norm = normalize(parsed.text)
    idx = doc_norm.text.find(needle)
    if idx >= 0:
        s, e = _map_span(doc_norm, idx, idx + len(needle))
        owner = next((c for c in chunks if c.char_start <= s < c.char_end), None)
        kind = "exact" if owner is not None and owner is named_chunk else "relocated"
        return build(owner, s, e, kind, 1.0)

    # 3. Fuzzy, in the named passage only. A near-miss elsewhere in the
    #    document is too weak a signal to call a citation.
    if named_chunk is not None:
        norm = normalize(named_chunk.text)
        located = _fuzzy_locate(norm.text, needle, fuzzy_threshold)
        if located is not None:
            start, end, ratio = located
            s, e = _map_span(norm, start, end)
            return build(
                named_chunk, named_chunk.char_start + s, named_chunk.char_start + e, "fuzzy", ratio
            )

    return None


def _page_for(parsed: ParsedDocument, offset: int) -> int:
    page_number = parsed.pages[0].number if parsed.pages else 1
    for page in parsed.pages:
        if page.char_offset <= offset:
            page_number = page.number
        else:
            break
    return page_number
