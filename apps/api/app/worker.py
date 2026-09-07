"""arq worker.

The ingestion pipeline lands in Phase 2. The worker exists now so that compose,
the Redis connection, and the deployment shape are proven before anything
depends on them. ``ping`` is the only job: arq refuses to start a worker with
no registered functions, and it doubles as an end-to-end queue check.
"""

from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.config import get_settings


async def ping(ctx: dict[str, Any]) -> str:
    """Round-trip check that the queue is live."""
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    ctx["settings"] = get_settings()


async def shutdown(ctx: dict[str, Any]) -> None:
    return None


class WorkerSettings:
    """Consumed by ``arq app.worker.WorkerSettings``."""

    functions: ClassVar[list[Any]] = [ping]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 600
