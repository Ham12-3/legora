"""Model clients.

``OpenAIClient`` uses the Responses API with a strict JSON schema, retries
429/500/503 with backoff (honouring Retry-After), and tracks RPM and TPM
against the configured budgets. ``FakeLLMClient`` lives in ``fake.py``.
"""

import asyncio
import json
import logging
import random
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol

import openai
from openai import AsyncOpenAI

from app.assistant.prompt import render_chat_messages
from app.assistant.stream import AnswerFieldStreamer
from app.config import Settings, get_settings
from app.llm.limits import RateLimiter
from app.llm.schema import (
    CELL_ANSWER_SCHEMA,
    CHAT_ANSWER_SCHEMA,
    AnswerSet,
    BatchItem,
    BatchStatus,
    ChatAnswer,
    ChatRequest,
    ChatResult,
    ExtractionRequest,
    ExtractionResult,
    Usage,
)
from app.review.prompt import render_messages

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class LLMClient(Protocol):
    name: str

    async def complete(self, request: ExtractionRequest) -> ExtractionResult: ...

    async def batch_submit(self, items: list[BatchItem]) -> str: ...

    async def batch_poll(self, batch_id: str) -> BatchStatus: ...

    def chat(self, request: ChatRequest) -> AsyncIterator[tuple[str, Any]]:
        """Yield (\"delta\", str) as the answer is written, then (\"done\", ChatResult)."""
        ...


def _estimate_request_tokens(request: ExtractionRequest) -> int:
    chars = len(request.system_prompt) + sum(len(p.text) for p in request.passages)
    chars += sum(len(q.question) for q in request.questions) + len(request.playbook or "")
    return chars // 4 + 500


def _response_format(
    name: str = "cell_answers", schema: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "name": name,
            "schema": schema or CELL_ANSWER_SCHEMA,
            "strict": True,
        }
    }


class OpenAIClient:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key, max_retries=0)
        self._settings = settings
        self._limiter = RateLimiter(
            rpm=settings.llm_rpm_budget,
            tpm=settings.llm_tpm_budget,
            max_concurrency=settings.llm_max_concurrency,
        )

    def _body(self, request: ExtractionRequest) -> dict[str, Any]:
        return {
            "model": request.model,
            "input": render_messages(request),
            "text": _response_format(),
            "metadata": request.metadata,
        }

    async def complete(self, request: ExtractionRequest) -> ExtractionResult:
        estimate = _estimate_request_tokens(request)
        body = self._body(request)
        attempt = 0
        async with self._limiter.semaphore:
            while True:
                await self._limiter.acquire(estimate)
                started = time.monotonic()
                try:
                    response = await self._client.responses.create(**body)
                    break
                except openai.APIStatusError as exc:
                    if (
                        exc.status_code not in RETRYABLE_STATUS
                        or attempt >= self._settings.llm_max_retries
                    ):
                        raise
                    delay = _retry_delay(exc, attempt)
                    log.warning(
                        "openai %s on attempt %d; sleeping %.1fs", exc.status_code, attempt, delay
                    )
                except (openai.APIConnectionError, openai.APITimeoutError) as exc:
                    if attempt >= self._settings.llm_max_retries:
                        raise
                    delay = min(2.0**attempt, 30.0) + random.uniform(0, 1)
                    log.warning("openai connection error (%s); sleeping %.1fs", exc, delay)
                attempt += 1
                await asyncio.sleep(delay)

        latency_ms = int((time.monotonic() - started) * 1000)
        usage = _usage_from(response)
        self._limiter.record_actual(usage.input_tokens + usage.output_tokens, estimate)
        answers = AnswerSet.model_validate_json(response.output_text)
        return ExtractionResult(
            answers=answers, model=response.model, usage=usage, latency_ms=latency_ms
        )

    # --- Assistant -------------------------------------------------------------

    async def chat(self, request: ChatRequest) -> AsyncIterator[tuple[str, Any]]:
        estimate = len(request.system_prompt) // 4 + sum(len(p.text) for p in request.passages) // 4
        estimate += sum(len(t.content) for t in request.history) // 4 + 400
        body: dict[str, Any] = {
            "model": request.model,
            "input": render_chat_messages(request),
            "text": _response_format("chat_answer", CHAT_ANSWER_SCHEMA),
            "metadata": request.metadata,
            "stream": True,
        }
        streamer = AnswerFieldStreamer()
        raw: list[str] = []
        final: Any = None
        started = time.monotonic()
        async with self._limiter.semaphore:
            await self._limiter.acquire(estimate)
            stream = await self._client.responses.create(**body)
            async for event in stream:
                kind = getattr(event, "type", "")
                if kind == "response.output_text.delta":
                    delta = str(getattr(event, "delta", ""))
                    raw.append(delta)
                    text = streamer.feed(delta)
                    if text:
                        yield ("delta", text)
                elif kind == "response.completed":
                    final = getattr(event, "response", None)
        latency_ms = int((time.monotonic() - started) * 1000)
        usage = _usage_from(final) if final is not None else Usage()
        self._limiter.record_actual(usage.input_tokens + usage.output_tokens, estimate)
        answer = ChatAnswer.model_validate_json("".join(raw))
        model = str(getattr(final, "model", request.model) or request.model)
        yield ("done", ChatResult(answer=answer, model=model, usage=usage, latency_ms=latency_ms))

    # --- Batch API -----------------------------------------------------------

    async def batch_submit(self, items: list[BatchItem]) -> str:
        lines = [
            json.dumps(
                {
                    "custom_id": item.custom_id,
                    "method": "POST",
                    "url": "/v1/responses",
                    "body": self._body(item.request),
                }
            )
            for item in items
        ]
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        upload = await self._client.files.create(
            file=("legora-batch.jsonl", payload), purpose="batch"
        )
        batch = await self._client.batches.create(
            input_file_id=upload.id, endpoint="/v1/responses", completion_window="24h"
        )
        return batch.id

    async def batch_poll(self, batch_id: str) -> BatchStatus:
        batch = await self._client.batches.retrieve(batch_id)
        if batch.status in {"validating", "in_progress", "finalizing"}:
            return BatchStatus(completed=False, failed=False, detail=batch.status)
        if batch.status in {"failed", "expired", "cancelled", "cancelling"}:
            return BatchStatus(completed=False, failed=True, detail=batch.status)

        results: dict[str, ExtractionResult] = {}
        errors: dict[str, str] = {}
        if batch.output_file_id:
            content = await self._client.files.content(batch.output_file_id)
            for raw in content.text.splitlines():
                if not raw.strip():
                    continue
                line = json.loads(raw)
                custom_id = str(line.get("custom_id"))
                resp = line.get("response") or {}
                if resp.get("status_code") != 200:
                    errors[custom_id] = f"status {resp.get('status_code')}"
                    continue
                body = resp.get("body") or {}
                text = _output_text_from_body(body)
                try:
                    answers = AnswerSet.model_validate_json(text)
                except ValueError as exc:
                    errors[custom_id] = f"unparseable output: {exc}"
                    continue
                usage_raw = body.get("usage") or {}
                results[custom_id] = ExtractionResult(
                    answers=answers,
                    model=str(body.get("model") or ""),
                    usage=Usage(
                        input_tokens=int(usage_raw.get("input_tokens", 0)),
                        output_tokens=int(usage_raw.get("output_tokens", 0)),
                    ),
                    latency_ms=0,
                )
        if batch.error_file_id:
            content = await self._client.files.content(batch.error_file_id)
            for raw in content.text.splitlines():
                if raw.strip():
                    line = json.loads(raw)
                    errors[str(line.get("custom_id"))] = json.dumps(line.get("error"))
        return BatchStatus(completed=True, failed=False, results=results, errors=errors)


def _retry_delay(exc: openai.APIStatusError, attempt: int) -> float:
    retry_after = exc.response.headers.get("retry-after") if exc.response is not None else None
    if retry_after:
        try:
            return float(min(float(retry_after), 60.0))
        except ValueError:
            pass
    return min(2.0**attempt, 30.0) + random.uniform(0, 1)


def _usage_from(response: Any) -> Usage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return Usage()
    details = getattr(usage, "input_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0)
    return Usage(
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cached_input_tokens=cached,
    )


def _output_text_from_body(body: dict[str, Any]) -> str:
    """Batch output bodies are raw Responses objects; concatenate their text."""
    parts: list[str] = []
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(str(content.get("text", "")))
    return "".join(parts)


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    from app.llm.fake import FakeLLMClient

    settings = settings or get_settings()
    provider = settings.llm_provider
    if provider == "auto":
        provider = "openai" if settings.openai_api_key else "fake"
        if provider == "fake":
            log.warning(
                "OPENAI_API_KEY unset: using the fake model. Cells are labelled model=fake."
            )
    if provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is unset")
        return OpenAIClient(settings)
    if provider == "fake":
        return FakeLLMClient()
    raise RuntimeError(f"unknown LLM_PROVIDER {provider!r}")
