"""Answer cache.

Key = sha256(document sha256 | question | output type | enum options | model |
prompt version). Re-running a grid must hit this; changing a prompt bumps
``PROMPT_VERSION`` and misses on purpose. The cached object is the model's
raw answer — verification runs again on every hit so a re-ingested document
verifies against its current text.
"""

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.schema import Answer
from app.models.review import CellCache, ReviewColumn


def cache_key(document_sha256: str, column: ReviewColumn, model: str, prompt_version: str) -> str:
    material = json.dumps(
        [
            document_sha256,
            " ".join(column.question.split()),
            column.output_type.value,
            sorted(column.enum_options or []),
            model,
            prompt_version,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def get_cached(session: AsyncSession, key: str) -> Answer | None:
    row = await session.get(CellCache, key)
    if row is None:
        return None
    return Answer.model_validate(row.answer)


async def put_cached(
    session: AsyncSession,
    *,
    key: str,
    workspace_id: uuid.UUID,
    model: str,
    prompt_version: str,
    answer: Answer,
) -> None:
    payload: dict[str, Any] = answer.model_dump()
    stmt = insert(CellCache).values(
        cache_key=key,
        workspace_id=workspace_id,
        model=model,
        prompt_version=prompt_version,
        answer=payload,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[CellCache.cache_key],
        set_={"answer": payload, "model": model, "prompt_version": prompt_version},
    )
    await session.execute(stmt)
