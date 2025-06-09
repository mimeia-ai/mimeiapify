"""
Redis Pub/Sub helper for Symphony
=================================

* Connects via **GlobalSymphony**   (alias **"pubsub"** → DB 7 by default)
* Provides high-level helpers:

    •  ``publish_json(channel, obj)``          – async, auto-serialises
    •  ``async for payload in subscribe(channel, *, max_queue=None)``

* Robust to reconnects; caller can cancel the async generator to unsubscribe
  gracefully.

Implementation choices
----------------------
* Uses **redis.asyncio**'s `PubSub` object (single TCP socket) as recommended
  by redis-py maintainers.
* Serialises with existing Symphony serde utilities (supports BaseModel, Enum, 
  datetime, Redis-optimized booleans, etc.)
* Optional *back-pressure*: if you pass ``max_queue=N`` the generator yields
  only after the consumer has processed the previous N messages; otherwise
  it mirrors raw pub/sub semantics (fire-and-forget), which is OK for
  transient "chatty agent" streams.

Typical usage
-------------
```python
from mimeiapify.symphony_ai.symphony_concurrency.pubsub import pubsub_client as ps

# --- publish from AsyncSendMessage thread ---
await ps.publish_json("run:ae3f", message_output.model_dump())

# --- consume in FastAPI background task ---
async for frame in ps.subscribe("run:ae3f"):
    await websocket.send_json(frame)
```

"""

from __future__ import annotations
import asyncio
import logging
import contextlib
from typing import Any, AsyncGenerator, Optional, Deque
from collections import deque

from redis.exceptions import ConnectionError as SyncConnectionError
from redis.asyncio.connection import ConnectionError as AsyncConnectionError
from redis.asyncio.client import PubSub

from mimeiapify.symphony_ai.redis.redis_client import RedisClient
from mimeiapify.symphony_ai.redis.redis_handler.utils.serde import dumps, loads

__all__ = [
    "publish_json",
    "subscribe",
]

log = logging.getLogger("symphony.pubsub")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def publish_json(channel: str, obj: Any, *, alias: str = "pubsub") -> None:
    """
    Publish *obj* to *channel* on the `alias` pool (default `"pubsub"`).

    Uses Symphony's sophisticated serde utilities for serialization - supports
    BaseModel, Enum, datetime, Redis-optimized booleans, etc.
    """
    redis = await RedisClient.get(alias)
    payload = dumps(obj)
    await redis.publish(channel, payload)
    log.debug("PUBLISH %s (%s bytes)", channel, len(payload))

async def subscribe(
    channel: str,
    *,
    alias: str = "pubsub",
    max_queue: Optional[int] = None,
    reconnect_delay: int = 5,
) -> AsyncGenerator[Any, None]:
    """
    Async generator yielding payloads published on *channel* (string).

    Args
    ----
    alias
        RedisClient pool alias (default ``"pubsub"`` → DB 7).
    max_queue
        If set, pause reading when internal queue length exceeds this value
        (simple in-memory back-pressure).
    reconnect_delay
        Seconds to wait before re-subscribing after a connection error.

    Example
    -------
    ```python
    async for payload in subscribe("run:1234", max_queue=20):
        await websocket.send_json(payload)
    ```
    """
    queue: Deque[Any] = deque()

    async def _reader_task(pubsub: PubSub):
        async for message in pubsub.listen():
            if message is None or message.get("type") != "message":
                continue
            data = loads(message["data"])
            queue.append(data)
            # Back-pressure: wait if queue is full
            while max_queue and len(queue) >= max_queue:
                await asyncio.sleep(0.05)

    while True:  # reconnect loop
        pubsub: PubSub | None = None
        reader: asyncio.Task | None = None
        try:
            redis = await RedisClient.get(alias)
            pubsub = redis.pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe(channel)
            log.debug("SUBSCRIBE %s (alias=%s)", channel, alias)

            reader = asyncio.create_task(_reader_task(pubsub))
            while True:
                if queue:
                    yield queue.popleft()
                else:
                    await asyncio.sleep(0.01)
        except (SyncConnectionError, AsyncConnectionError) as exc:
            log.warning("PubSub connection error: %s – retry in %ss", exc, reconnect_delay)
        except asyncio.CancelledError:
            log.debug("subscribe(%s) cancelled", channel)
            break
        finally:
            if reader:
                reader.cancel()
                with contextlib.suppress(Exception):
                    await reader
            if pubsub:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
        await asyncio.sleep(reconnect_delay) 