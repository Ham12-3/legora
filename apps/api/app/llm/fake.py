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
from collections.abc import AsyncIterator
from typing import Any

from app.llm.schema import (
    Answer,
    AnswerSet,
    BatchItem,
    BatchStatus,
    ChatAnswer,
    ChatCitation,
    ChatRequest,
    ChatResult,
    ExtractionRequest,
    ExtractionResult,
    PlaybookFinding,
    PlaybookFindingSet,
    PlaybookRequest,
    PlaybookResult,
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


def _stem(word: str) -> str:
    """Crude suffix stripping so 'indemnifies' meets 'indemnify'. Fake only."""
    for suffix in ("ies", "ing", "ment", "tion", "es", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def _keywords(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}


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

    async def chat(self, request: ChatRequest) -> AsyncIterator[tuple[str, Any]]:
        """Grounded fake: cite the two best-overlapping sentences, or refuse."""
        self.chat_calls: list[ChatRequest] = getattr(self, "chat_calls", [])
        self.chat_calls.append(request)
        keys = _keywords(request.question)
        candidates: list[tuple[int, str, str, str]] = []  # score, label, sentence, doc
        for passage in request.passages:
            doc = passage.section_path.split(" > ")[0].removeprefix("document: ")
            for sentence in _SENTENCE.split(passage.text):
                score = len(keys & _keywords(sentence))
                if score > 0 and len(sentence.strip()) > 20:
                    candidates.append((score, passage.label, sentence.strip(), doc))
        candidates.sort(key=lambda c: -c[0])
        picked = candidates[:2]

        if not picked:
            answer = ChatAnswer(
                answer="The selected documents do not appear to address this question.",
                citations=[],
                insufficient=True,
            )
        else:
            parts: list[str] = []
            citations: list[ChatCitation] = []
            for marker, (_, label, sentence, doc) in enumerate(picked, start=1):
                parts.append(f"In {doc}: {sentence} [{marker}]")
                quote = (
                    sentence
                    if not self.fabricate
                    else "The Supplier shall pay liquidated damages of ten per cent (10%) of the "
                    "Fees for each week of delay beyond the agreed delivery date."
                )
                citations.append(ChatCitation(marker=marker, chunk_id=label, text=quote))
            answer = ChatAnswer(answer=" ".join(parts), citations=citations, insufficient=False)

        # Stream the prose a few words at a time, like a real model would.
        words = answer.answer.split(" ")
        for i in range(0, len(words), 4):
            yield ("delta", " ".join(words[i : i + 4]) + (" " if i + 4 < len(words) else ""))
        yield (
            "done",
            ChatResult(
                answer=answer,
                model="fake",
                usage=Usage(input_tokens=sum(len(p.text) for p in request.passages) // 4),
                latency_ms=1,
            ),
        )

    async def review_playbook(self, request: PlaybookRequest) -> PlaybookResult:
        """Grounded fake: classify each rule by which position's words the best
        matching sentence shares, and quote that sentence verbatim."""
        self.playbook_calls: list[PlaybookRequest] = getattr(self, "playbook_calls", [])
        self.playbook_calls.append(request)
        findings: list[PlaybookFinding] = []
        for rule in request.rules:
            keys = _keywords(rule.topic) | _keywords(rule.preferred_position)
            best_score = 0
            best: tuple[str, str, str] | None = None  # label, sentence, section
            for passage in request.passages:
                for sentence in _SENTENCE.split(passage.text):
                    score = len(keys & _keywords(sentence))
                    if score > best_score and len(sentence.strip()) > 20:
                        best_score, best = (
                            score,
                            (passage.label, sentence.strip(), passage.section_path),
                        )
            if best is None or best_score < 2:
                findings.append(
                    PlaybookFinding(
                        rule_id=rule.label,
                        matched_position="not_addressed",
                        severity="medium",
                        rationale=f"The document does not appear to address {rule.topic.lower()}.",
                        suggested_language=rule.preferred_position,
                    )
                )
                continue
            label, sentence, section = best
            words = _keywords(sentence)
            scores = {
                "preferred": len(words & _keywords(rule.preferred_position)),
                "fallback": len(words & _keywords(rule.fallback_position)),
                "unacceptable": len(words & _keywords(rule.unacceptable_position)),
            }
            position = max(scores, key=lambda k: (scores[k], k == "preferred"))
            severity = {"preferred": "none", "fallback": "low", "unacceptable": "high"}[position]
            quote = (
                sentence
                if not self.fabricate
                else "The Supplier shall pay liquidated damages of ten per cent (10%) of the Fees "
                "for each week of delay beyond the agreed delivery date."
            )
            findings.append(
                PlaybookFinding(
                    rule_id=rule.label,
                    matched_position=position,
                    severity=severity,
                    clause_reference=section.split(" > ")[-1][:120] if section else "",
                    rationale=f"The clause reads: {sentence[:160]}",
                    quotes=[Quote(chunk_id=label, text=quote)],
                    suggested_language="" if position == "preferred" else rule.preferred_position,
                )
            )
        return PlaybookResult(
            findings=PlaybookFindingSet(findings=findings),
            model="fake",
            usage=Usage(input_tokens=sum(len(p.text) for p in request.passages) // 4),
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
