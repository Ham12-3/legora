"""The request and answer contract between the executor and any model client.

``CELL_ANSWER_SCHEMA`` is the strict JSON Schema handed to Structured Outputs.
Schema conformance guarantees shape, not truth: ``app.review.verify`` checks
every quote against the source afterwards.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]


class Quote(BaseModel):
    chunk_id: str  # the passage label, e.g. "c12"
    text: str


class Answer(BaseModel):
    column_id: str  # the question label, e.g. "q1"
    value: str
    quotes: list[Quote] = Field(default_factory=list)
    confidence: Confidence = "low"
    not_found: bool = False


class AnswerSet(BaseModel):
    answers: list[Answer]


CELL_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "column_id": {"type": "string"},
                    "value": {"type": "string"},
                    "quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "chunk_id": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["chunk_id", "text"],
                            "additionalProperties": False,
                        },
                    },
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "not_found": {"type": "boolean"},
                },
                "required": ["column_id", "value", "quotes", "confidence", "not_found"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["answers"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Passage:
    label: str  # "c12"
    section_path: str
    text: str


@dataclass(frozen=True)
class Question:
    label: str  # "q1"
    question: str
    output_type: str
    enum_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionRequest:
    """Everything a client needs to ask the model about one document.

    The rendering order is fixed by ``app.review.prompt`` for cache hits:
    system, playbook, document, questions LAST.
    """

    model: str
    system_prompt: str
    document_title: str
    outline: tuple[str, ...]
    passages: tuple[Passage, ...]
    questions: tuple[Question, ...]
    playbook: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class ExtractionResult:
    answers: AnswerSet
    model: str
    usage: Usage
    latency_ms: int


@dataclass(frozen=True)
class BatchItem:
    custom_id: str
    request: ExtractionRequest


@dataclass(frozen=True)
class BatchStatus:
    """Poll result. ``results`` is populated only when ``completed`` is true;
    a missing custom_id in ``results`` means that item failed (see errors)."""

    completed: bool
    failed: bool
    results: dict[str, ExtractionResult] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    detail: str = ""


# --- assistant ------------------------------------------------------------------


class ChatCitation(BaseModel):
    marker: int
    chunk_id: str  # passage label, e.g. "d2c14"
    text: str


class ChatAnswer(BaseModel):
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    insufficient: bool = False


CHAT_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "marker": {"type": "integer"},
                    "chunk_id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["marker", "chunk_id", "text"],
                "additionalProperties": False,
            },
        },
        "insufficient": {"type": "boolean"},
    },
    "required": ["answer", "citations", "insufficient"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ChatRequest:
    """A grounded question over passages from one or more documents.

    Rendering order (``app.assistant.prompt``): system, passages, history,
    then the question LAST.
    """

    model: str
    system_prompt: str
    passages: tuple[Passage, ...]
    history: tuple[ChatTurn, ...]
    question: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatResult:
    answer: ChatAnswer
    model: str
    usage: Usage
    latency_ms: int
