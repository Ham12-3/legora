"""Embedding providers behind one small interface.

``embed_texts`` always returns one vector per input, each of ``embed_dim``
floats, or ``None`` when embeddings are disabled. Callers batch; providers
do not.
"""

import hashlib
import logging
import math
import struct
from typing import Protocol

from openai import AsyncOpenAI

from app.config import Settings, get_settings

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.embed_model
        self._dim = settings.embed_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model, input=texts, dimensions=self._dim
        )
        # The API returns items in request order, but be explicit about it.
        ordered = sorted(response.data, key=lambda d: d.index)
        return [list(d.embedding) for d in ordered]


class FakeEmbedder:
    """Deterministic unit vectors from a hash of the text. Tests only."""

    name = "fake"

    def __init__(self, dim: int) -> None:
        self._dim = dim
        self.batches: list[int] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(len(texts))
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        counter = 0
        while len(values) < self._dim:
            block = hashlib.sha256(seed + struct.pack("<I", counter)).digest()
            values.extend(struct.unpack("<8f", block))
            counter += 1
        values = [v if math.isfinite(v) else 0.0 for v in values[: self._dim]]
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]


def get_embedder(settings: Settings | None = None) -> Embedder | None:
    """Resolve the configured provider. ``None`` means skip embeddings."""
    settings = settings or get_settings()
    provider = settings.embeddings_provider
    if provider == "auto":
        provider = "openai" if settings.openai_api_key else "none"
    if provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("EMBEDDINGS_PROVIDER=openai but OPENAI_API_KEY is unset")
        return OpenAIEmbedder(settings)
    if provider == "fake":
        return FakeEmbedder(settings.embed_dim)
    if provider == "none":
        log.warning("embeddings disabled: chunks will be stored without vectors")
        return None
    raise RuntimeError(f"unknown EMBEDDINGS_PROVIDER {provider!r}")
