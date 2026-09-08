"""Wrap an LLMClient to record latency and token usage per call."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.llm.client import LLMClient
from app.llm.schema import (
    BatchItem,
    BatchStatus,
    ChatRequest,
    ExtractionRequest,
    ExtractionResult,
    PlaybookRequest,
    PlaybookResult,
)


@dataclass
class CallRecord:
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    questions: int


@dataclass
class InstrumentedClient:
    inner: LLMClient
    calls: list[CallRecord] = field(default_factory=list)
    name: str = ""

    def __post_init__(self) -> None:
        self.name = self.inner.name

    async def complete(self, request: ExtractionRequest) -> ExtractionResult:
        result = await self.inner.complete(request)
        self.calls.append(
            CallRecord(
                latency_ms=result.latency_ms,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                cached_input_tokens=result.usage.cached_input_tokens,
                questions=len(request.questions),
            )
        )
        return result

    async def batch_submit(self, items: list[BatchItem]) -> str:
        return await self.inner.batch_submit(items)

    async def batch_poll(self, batch_id: str) -> BatchStatus:
        return await self.inner.batch_poll(batch_id)

    def chat(self, request: ChatRequest) -> AsyncIterator[tuple[str, Any]]:
        return self.inner.chat(request)

    async def review_playbook(self, request: PlaybookRequest) -> PlaybookResult:
        return await self.inner.review_playbook(request)
