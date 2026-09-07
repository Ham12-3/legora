"""Citation verification against a real parsed fixture. No database."""

import uuid
from pathlib import Path

import pytest

from app.ingestion.chunker import chunk_document
from app.ingestion.pdf import parse_pdf
from app.ingestion.types import ParsedDocument
from app.models.chunk import Chunk
from app.review.verify import normalize, verify_quote

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def doc() -> tuple[ParsedDocument, list[Chunk]]:
    parsed = parse_pdf((FIXTURES / "msa.pdf").read_bytes())
    drafts = chunk_document(parsed, target_tokens=800, max_tokens=1500)
    chunks = [
        Chunk(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            ordinal=d.ordinal,
            text=d.text,
            section_path=d.section_path,
            page_start=d.page_start,
            page_end=d.page_end,
            char_start=d.char_start,
            char_end=d.char_end,
            token_count=d.token_count,
            bboxes=d.bboxes,
        )
        for d in drafts
    ]
    return parsed, chunks


def _chunk_containing(chunks: list[Chunk], phrase: str) -> Chunk:
    for c in chunks:
        if phrase in " ".join(c.text.split()):
            return c
    raise AssertionError(phrase)


def test_normalize_collapses_whitespace_and_maps_offsets() -> None:
    n = normalize("Supplier  shall\n indemnify “Customer”.")
    assert n.text == 'Supplier shall indemnify "Customer".'
    start = n.text.index("indemnify")
    assert n.index_map[start] == "Supplier  shall\n indemnify".index("indemnify")


def test_exact_quote_in_named_chunk(doc: tuple[ParsedDocument, list[Chunk]]) -> None:
    parsed, chunks = doc
    chunk = _chunk_containing(chunks, "8.2 Supplier shall indemnify Customer")
    quote = "Supplier shall indemnify Customer against all losses"
    span = verify_quote(quote, chunk, parsed=parsed, chunks=chunks, fuzzy_threshold=0.9)
    assert span is not None
    assert span.match_kind == "exact"
    assert " ".join(span.quoted_text.split()) == quote
    assert parsed.text[span.char_start : span.char_end] == span.quoted_text
    assert span.chunk is chunk
    assert span.page >= 1
    assert span.bboxes, "PDF citations carry word boxes"


def test_quote_with_line_wrap_and_curly_quotes_still_matches(
    doc: tuple[ParsedDocument, list[Chunk]],
) -> None:
    parsed, chunks = doc
    chunk = _chunk_containing(chunks, "Confidential Information")
    # The model normalises whitespace and typography; the PDF has line breaks.
    quote = "the following terms have the following meanings"
    span = verify_quote(quote, chunk, parsed=parsed, chunks=chunks, fuzzy_threshold=0.9)
    assert span is not None and span.match_kind == "exact"


def test_relocated_quote_when_wrong_chunk_named(doc: tuple[ParsedDocument, list[Chunk]]) -> None:
    parsed, chunks = doc
    right = _chunk_containing(chunks, "8.2 Supplier shall indemnify Customer")
    wrong = next(c for c in chunks if c is not right)
    quote = "Supplier shall indemnify Customer against all losses"
    span = verify_quote(quote, wrong, parsed=parsed, chunks=chunks, fuzzy_threshold=0.9)
    assert span is not None
    assert span.match_kind == "relocated"
    assert span.chunk is right


def test_fuzzy_quote_with_small_errors(doc: tuple[ParsedDocument, list[Chunk]]) -> None:
    parsed, chunks = doc
    chunk = _chunk_containing(chunks, "8.2 Supplier shall indemnify Customer")
    # Two transcription slips in ~60 characters: above 0.9 similarity.
    quote = "Supplier shall indemnify Customer against all loses arising form"
    span = verify_quote(quote, chunk, parsed=parsed, chunks=chunks, fuzzy_threshold=0.9)
    assert span is not None
    assert span.match_kind == "fuzzy"
    assert span.similarity >= 0.9
    # The citation carries the *source* text, not the model's version.
    assert "losses arising from" in " ".join(span.quoted_text.split())


def test_fabricated_quote_is_rejected(doc: tuple[ParsedDocument, list[Chunk]]) -> None:
    parsed, chunks = doc
    chunk = _chunk_containing(chunks, "8.2 Supplier shall indemnify Customer")
    quote = "Supplier shall indemnify Customer for consequential losses of any kind whatsoever"
    assert verify_quote(quote, chunk, parsed=parsed, chunks=chunks, fuzzy_threshold=0.9) is None


def test_fuzzy_does_not_roam_the_whole_document(doc: tuple[ParsedDocument, list[Chunk]]) -> None:
    parsed, chunks = doc
    wrong = _chunk_containing(chunks, "Governing Law")
    quote = "Supplier shall indemnify Customer against all loses arising form"
    # Near-miss text exists elsewhere, but the model named the wrong passage:
    # too weak to call a citation.
    assert verify_quote(quote, wrong, parsed=parsed, chunks=chunks, fuzzy_threshold=0.9) is None


def test_tiny_quotes_are_rejected(doc: tuple[ParsedDocument, list[Chunk]]) -> None:
    parsed, chunks = doc
    assert verify_quote("a", chunks[0], parsed=parsed, chunks=chunks, fuzzy_threshold=0.9) is None
