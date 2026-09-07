"""A deterministic stand-in for the model.

It answers each question by lexical overlap: the sentence in the document
that shares the most non-trivial words with the question becomes the quote,
copied verbatim from the passage so the verifier accepts it. That is enough to
exercise routing, grouping, caching, verification, streaming, batch, export,
and the UI without a key. It is NOT an extraction model; cells it produces
carry ``model="fake"`` and the UI shows a demo banner.

``fabricate=True`` returns quotes that are not in the document, which is how
the tests prove the verifier rejects them.
"""

import re
import uuid

from app.llm.schema import (
    Answer,
    AnswerSet,
    BatchItem,
    BatchStatus,
    ExtractionRequest,
    ExtractionResult,
    Quote,
    Usage,
)

_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "is",
    "are",
    "what",
    "which",
    "does",
    "do",
    "this",
    "that",
    "in",
    "to",
    "for",
    "any",
    "with",
    "be",
    "by",
    "on",
    "it",
    "its",
    "as",
    "at",
    "who",
    "how",
    "when",
    "there",
    "under",
    "agreement",
    "contract",
    "document",
    "party",
    "parties",
    "clause",
    "provision",
    "please",
    "state",
    "specify",
    "identify",
    "if",
    "has",
    "have",
}
_SENTENCE = re.compile(r"(?<=[.;:!?])\s+")
_WORD = re.compile(r"[a-z0-9£$€%]+")


def _keywords(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}


class FakeLLMClient:
    name = "fake"

    def __init__(self, *, fabricate: bool = False) -> None:
        self.fabricate = fabricate
        self.calls: list[ExtractionRequest] = []
        self._batches: dict[str, list[BatchItem]] = {}

    def _answer(
        self,
        request: ExtractionRequest,
        label: str,
        question: str,
        output_type: str,
        options: tuple[str, ...],
    ) -> Answer:
        keys = _keywords(question)
        best_score = 0
        best: tuple[str, str] | None = None  # (passage label, sentence)
        for passage in request.passages:
            for sentence in _SENTENCE.split(passage.text):
                words = _keywords(sentence)
                score = len(keys & words)
                if score > best_score and len(sentence.strip()) > 20:
                    best_score, best = score, (passage.label, sentence.strip())

        if best is None or best_score == 0:
            return Answer(column_id=label, value="", quotes=[], confidence="low", not_found=True)

        chunk_label, sentence = best
        # A fabrication is a plausible sentence that is simply not in the
        # document, which is what a hallucinating model produces.
        quote_text = (
            sentence
            if not self.fabricate
            else "The Supplier shall pay liquidated damages of ten per cent (10%) of the Fees "
            "for each week of delay beyond the agreed delivery date."
        )
        value = sentence
        if output_type == "boolean":
            value = "yes"
        elif output_type == "enum" and options:
            match = next((o for o in options if o.lower() in sentence.lower()), options[0])
            value = match
        elif output_type == "date":
            m = re.search(r"\b\d{1,2} \w+ \d{4}\b|\b\d{4}-\d{2}-\d{2}\b", sentence)
            value = m.group(0) if m else sentence
        elif output_type == "money":
            m = re.search(r"[£$€]\s?[\d,]+(?:\.\d+)?(?: per \w+)?", sentence)
            value = m.group(0) if m else sentence

        confidence = "high" if best_score >= 3 else "medium" if best_score == 2 else "low"
        return Answer(
            column_id=label,
            value=value,
            quotes=[Quote(chunk_id=chunk_label, text=quote_text)],
            confidence=confidence,
            not_found=False,
        )

    async def complete(self, request: ExtractionRequest) -> ExtractionResult:
        self.calls.append(request)
        answers = [
            self._answer(request, q.label, q.question, q.output_type, q.enum_options)
            for q in request.questions
        ]
        chars = sum(len(p.text) for p in request.passages)
        return ExtractionResult(
            answers=AnswerSet(answers=answers),
            model="fake",
            usage=Usage(input_tokens=chars // 4, output_tokens=50 * len(answers)),
            latency_ms=1,
        )

    async def batch_submit(self, items: list[BatchItem]) -> str:
        batch_id = f"fake-batch-{uuid.uuid4().hex[:12]}"
        self._batches[batch_id] = items
        return batch_id

    async def batch_poll(self, batch_id: str) -> BatchStatus:
        items = self._batches.get(batch_id)
        if items is None:
            return BatchStatus(completed=False, failed=True, detail="unknown batch")
        results = {item.custom_id: await self.complete(item.request) for item in items}
        return BatchStatus(completed=True, failed=False, results=results)
