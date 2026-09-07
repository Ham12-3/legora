"""Enqueue side of the arq queue.

The API never runs a stage itself (CLAUDE.md rule 6); it hands document ids
to the worker. ``queue_enabled=false`` turns enqueueing into a no-op so the
test suite and offline tooling do not need Redis.
"""

import logging
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings

log = logging.getLogger(__name__)

_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue(job_name: str, *args: Any) -> None:
    if not get_settings().queue_enabled:
        log.debug("queue disabled; dropping %s%r", job_name, args)
        return
    pool = await get_pool()
    await pool.enqueue_job(job_name, *args)


async def enqueue_ingestion(document_id: Any) -> None:
    await enqueue("parse_document", str(document_id))
