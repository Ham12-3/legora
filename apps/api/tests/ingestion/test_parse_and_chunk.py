"""Parser and chunker against the fixture contracts. No database.

``test_offsets_round_trip`` is the most important test in the codebase
(CLAUDE.md rule 3). Everything downstream — citations, highlights, the eval
harness — assumes that slicing the document text at a chunk's offsets returns
exactly the chunk's text.
"""

from itertools import pairwise
from pathlib import Path

import pytest

from app.ingestion.chunker import chunk_document
from app.ingestion.docx import parse_docx
from app.ingestion.pdf import parse_pdf
from app.ingestion.sections import detect_marker
from app.ingestion.types import ParsedDocument, blocks_from_pages, estimate_tokens

FIXTURES = Path(__file__).parent.parent / "fixtures"
CONTRACT_PDFS = ["msa.pdf", "nda.pdf", "saas_subscription.pdf", "employment.pdf", "lease.pdf"]
TARGET, MAX = 800, 1500


def load(name: str) -> ParsedDocument:
    data = (FIXTURES / name).read_bytes()
    return parse_docx(data) if name.endswith(".docx") else parse_pdf(data)


def flat(text: str) -> str:
    """Collapse the PDF's line wrapping so phrases can be searched for."""
    return " ".join(text.split())


@pytest.fixture(params=[*CONTRACT_PDFS, "msa.docx"])
def parsed(request: pytest.FixtureRequest) -> ParsedDocument:
    return load(request.param)


# --- the invariant -------------------------------------------------------------


def test_offsets_round_trip(parsed: ParsedDocument) -> None:
    chunks = chunk_document(parsed, target_tokens=TARGET, max_tokens=MAX)
    assert chunks, "chunker produced nothing"
    for chunk in chunks:
        assert parsed.text[chunk.char_start : chunk.char_end] == chunk.text, chunk.ordinal


def test_word_offsets_round_trip_within_pages(parsed: ParsedDocument) -> None:
    for page in parsed.pages:
        for word in page.words:
            token = page.text[word.start : word.end]
            assert token and not token.isspace()
            assert " " not in token and "\n" not in token
        # Page-local offsets, lifted by char_offset, land in the document text.
        if page.words:
            last = page.words[-1]
            assert (
                parsed.text[page.char_offset + last.start : page.char_offset + last.end]
                == page.text[last.start : last.end]
            )


def test_blocks_round_trip(parsed: ParsedDocument) -> None:
    for block in blocks_from_pages(parsed.pages):
        assert parsed.text[block.char_start : block.char_end] == block.text


# --- structure -----------------------------------------------------------------


def test_chunks_are_ordered_contiguous_and_bounded(parsed: ParsedDocument) -> None:
    chunks = chunk_document(parsed, target_tokens=TARGET, max_tokens=MAX)
    for prev, cur in pairwise(chunks):
        assert cur.ordinal == prev.ordinal + 1
        assert cur.char_start >= prev.char_start
        # Overlap is at most one sentence back into the previous chunk, never
        # a full re-read of it.
        assert cur.char_start > prev.char_start
        assert cur.char_end > prev.char_end
    for chunk in chunks:
        assert chunk.token_count <= MAX, (chunk.ordinal, chunk.token_count)
        assert chunk.page_start <= chunk.page_end
        assert estimate_tokens(chunk.text) == chunk.token_count

    # Coverage: every character of body text belongs to some chunk.
    covered = 0
    cursor = 0
    for chunk in chunks:
        start = max(chunk.char_start, cursor)
        covered += max(0, chunk.char_end - start)
        cursor = max(cursor, chunk.char_end)
    assert covered >= len(parsed.text.strip()) * 0.98


@pytest.mark.parametrize("target", [TARGET, 200, 60])
def test_clause_boundaries_are_respected(target: int) -> None:
    """Every chunk starts on a clause (block) boundary, or a sentence boundary
    inside an oversized block. A chunk that starts mid-section never runs into
    the next section's heading; only chunks made of whole sections may hold
    more than one heading."""
    parsed = load("msa.pdf")
    blocks = blocks_from_pages(parsed.pages)
    block_starts = {b.char_start for b in blocks}
    top_level_starts = {
        b.char_start for b in blocks if (m := detect_marker(b.text)) and m.depth <= 1
    }

    chunks = chunk_document(parsed, target_tokens=target, max_tokens=max(target * 2, 300))
    for chunk in chunks:
        starts_on_block = chunk.char_start in block_starts
        starts_on_sentence = chunk.char_start == 0 or parsed.text[chunk.char_start - 1] in " \n"
        assert starts_on_block or starts_on_sentence, chunk.ordinal

        heads_inside = [s for s in top_level_starts if chunk.char_start < s < chunk.char_end]
        if heads_inside:
            assert chunk.char_start in top_level_starts, (
                f"chunk {chunk.ordinal} starts mid-section but swallows a heading"
            )
            # ...and ends where a section ends: the next chunk begins a section.
            nxt = next((c for c in chunks if c.ordinal == chunk.ordinal + 1), None)
            assert (
                nxt is None
                or nxt.char_start in top_level_starts
                or nxt.char_start >= max(heads_inside)
            )


def test_merged_small_sections_report_the_common_parent() -> None:
    parsed = load("msa.pdf")
    chunks = chunk_document(parsed, target_tokens=TARGET, max_tokens=MAX)
    both = [
        c
        for c in chunks
        if "1. Definitions" in flat(c.text) and "2. Interpretation" in flat(c.text)
    ]
    assert both, "expected the two short sections of ARTICLE I to share a chunk"
    assert both[0].section_path == "ARTICLE I DEFINITIONS AND INTERPRETATION"


def test_section_paths_carry_context() -> None:
    parsed = load("msa.pdf")
    chunks = chunk_document(parsed, target_tokens=TARGET, max_tokens=MAX)

    indemnity = [c for c in chunks if "8.2 Supplier shall indemnify Customer" in flat(c.text)]
    assert indemnity, "clause 8.2 not found in any chunk"
    # Sections 8 and 9 are short enough to share a chunk, so the path is the
    # ARTICLE they have in common — never a sibling's heading.
    assert indemnity[0].section_path.startswith("ARTICLE IV RISK")
    assert "7. Confidentiality" not in indemnity[0].text, "merged across an ARTICLE"

    governing = [c for c in chunks if "laws of England and Wales, and the courts" in flat(c.text)]
    assert governing
    # 10 and 11 are short and share ARTICLE V, so the chunk reports the ARTICLE.
    assert governing[0].section_path.startswith("ARTICLE V GENERAL")

    # A small target forces splitting inside a section; children still know
    # their parent.
    fine = chunk_document(parsed, target_tokens=120, max_tokens=300)
    liability = [c for c in fine if "125%" in flat(c.text)]
    assert liability
    assert liability[0].section_path.startswith("ARTICLE IV RISK > 9. Limitation of Liability")


def test_oversized_block_is_split_at_sentences() -> None:
    parsed = load("msa.pdf")
    chunks = chunk_document(parsed, target_tokens=60, max_tokens=90)
    for chunk in chunks:
        assert chunk.token_count <= 90 or "." not in chunk.text[:-1], chunk.ordinal
        assert parsed.text[chunk.char_start : chunk.char_end] == chunk.text


def test_target_is_respected_on_average() -> None:
    parsed = load("msa.pdf")
    chunks = chunk_document(parsed, target_tokens=TARGET, max_tokens=MAX)
    sizes = [c.token_count for c in chunks]
    assert max(sizes) <= MAX
    # Not pathologically fragmented: small sections were packed together.
    assert sorted(sizes)[len(sizes) // 2] >= 200


# --- geometry ------------------------------------------------------------------


def test_pdf_bboxes_cover_the_chunks_pages() -> None:
    parsed = load("msa.pdf")
    assert len(parsed.pages) >= 2
    chunks = chunk_document(parsed, target_tokens=TARGET, max_tokens=MAX)
    for chunk in chunks:
        pages = {int(p) for p in chunk.bboxes}
        assert pages, chunk.ordinal
        assert min(pages) >= chunk.page_start and max(pages) <= chunk.page_end
        for boxes in chunk.bboxes.values():
            for x0, y0, x1, y1 in boxes:
                assert 0 <= x0 < x1 <= parsed.pages[0].width + 1
                assert 0 <= y0 < y1 <= parsed.pages[0].height + 1


def test_multi_page_chunk_spans_pages() -> None:
    parsed = load("msa.pdf")
    chunks = chunk_document(parsed, target_tokens=TARGET, max_tokens=MAX)
    assert any(c.page_start != c.page_end for c in chunks), (
        "expected at least one chunk to cross a page"
    )


# --- formats -------------------------------------------------------------------


def test_docx_preserves_paragraph_order_and_headings() -> None:
    parsed = load("msa.docx")
    blocks = blocks_from_pages(parsed.pages)
    texts = [b.text for b in blocks]
    assert texts[0] == "MASTER SERVICES AGREEMENT"
    assert texts.index("8. Indemnities") < texts.index("9. Limitation of Liability")
    assert parsed.pages[0].words, "docx words should exist for lexical highlighting"
    assert parsed.is_ocr is False


def test_scanned_pdf_is_flagged() -> None:
    parsed = load("scanned_nda.pdf")
    assert parsed.is_ocr is True
    assert all(p.is_ocr for p in parsed.pages)
    # With OCR disabled in tests there is no text; with Tesseract present
    # there is. Either way the flag is what the UI keys off.


def test_text_pdf_is_not_flagged() -> None:
    assert load("nda.pdf").is_ocr is False
