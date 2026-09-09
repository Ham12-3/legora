"""Cell status events over Redis pub/sub, consumed by the SSE endpoint.

One channel per review. Payloads are the serialised cell the grid needs to
redraw one square. When Redis is not available (tests), publishing is a
no-op and the grid falls back to refetching.
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis

from app.config import get_settings

log = logging.getLogger(__name__)

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url)
    return _redis


def channel(review_id: uuid.UUID) -> str:
    return f"review:{review_id}"


async def publish(review_id: uuid.UUID, event: str, payload: dict[str, Any]) -> None:
    if not get_settings().queue_enabled:  # queue_enabled doubles as "Redis is here"
        return
    try:
        await _client().publish(channel(review_id), json.dumps({"event": event, "data": payload}))
    except Exception as exc:  # events are best-effort; never fail a cell over them
        log.warning("event publish failed: %s", exc)


async def subscribe(review_id: uuid.UUID) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    pubsub = _client().pubsub()
    await pubsub.subscribe(channel(review_id))
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if message is None:
                yield ("heartbeat", {})
                continue
            body = json.loads(message["data"])
            yield (str(body["event"]), dict(body["data"]))
    finally:
        await pubsub.unsubscribe(channel(review_id))
        await pubsub.aclose()  # type: ignore[no-untyped-call]
