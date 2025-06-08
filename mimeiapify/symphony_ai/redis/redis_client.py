# mimeiapify/symphony_ai/redis/redis_client.py

"""
Redis helper that is **fork-safe** and asyncio-native.

Why so elaborate?
-----------------
• Gunicorn / Uvicorn workers often `fork()` after import time.
  Re-using a parent-process connection in the child silently breaks
  pub/sub and can leak file descriptors.

• Each worker therefore needs its *own* connection-pool.
"""

from __future__ import annotations
import os, asyncio, logging
from typing import Optional, AsyncIterator, ClassVar
from contextlib import asynccontextmanager
import logging

from redis.asyncio import Redis, ConnectionPool

log = logging.getLogger("symphony.redis")


class RedisClient:
    """
    Fork-safe, asyncio-native **multi-pool** Redis manager.

    You can register any number of pools, each indexed by an *alias*
    (string) or by the full connection URL. Every worker process keeps its
    own pools to avoid post-fork descriptor reuse.
    """

    _pools: ClassVar[dict[str, ConnectionPool]] = {}
    _clients: ClassVar[dict[str, Redis]] = {}
    _pid: ClassVar[Optional[int]] = None

    # ---------- life-cycle --------------------------------------------------

    @classmethod
    def setup(
        cls,
        url: str,
        *,
        alias: str | None = None,
        max_connections: int = 64,
    ) -> None:
        """
        Register (or re-use) a Redis connection pool for this process.

        If ``alias`` is omitted the URL itself is used as key.  For backward
        compatibility the first pool created without an explicit alias is also
        registered under ``"default"``.
        """
        pid = os.getpid()
        if cls._pid is None:
            cls._pid = pid
        elif cls._pid != pid:
            # process forked – discard inherited pools
            cls._pools.clear()
            cls._clients.clear()
            cls._pid = pid

        key = alias or url
        if key in cls._pools:
            return

        log.info("Initialising Redis pool '%s' in PID %s (%s)", key, pid, url)
        pool = ConnectionPool.from_url(
            url,
            decode_responses=True,
            encoding="utf-8",
            max_connections=max_connections,
        )
        client = Redis(connection_pool=pool)
        cls._pools[key] = pool
        cls._clients[key] = client
        if alias is None and "default" not in cls._pools:
            cls._pools["default"] = pool
            cls._clients["default"] = client

    @classmethod
    async def close(cls, alias: str | None = None) -> None:
        """Close one or all Redis pools for this process."""
        pid = os.getpid()
        if cls._pid != pid:
            log.debug("No Redis pool to close for PID %s", pid)
            return

        keys = [alias] if alias else list(cls._pools.keys())
        for k in keys:
            pool = cls._pools.pop(k, None)
            if pool:
                log.info("Closing Redis pool '%s' in PID %s", k, pid)
                await pool.disconnect()
                cls._clients.pop(k, None)
        if not cls._pools:
            cls._pid = None

    # ---------- access helpers ---------------------------------------------

    @classmethod
    async def get(cls, alias: str | None = None) -> Redis:
        """Return the Redis client for the given alias (default ``"default"``)."""
        key = alias or "default"
        client = cls._clients.get(key)
        if client is None or cls._pid != os.getpid():
            log.error("RedisClient.get() called before setup() in this process.")
            raise RuntimeError(
                f"RedisClient.setup() must be called for alias '{key}' first."
            )
        # quick health check – keep it cheap
        try:
            await client.ping()
            log.debug("Redis PING successful for '%s'.", key)
        except Exception as exc:
            log.error("Redis ping failed for '%s': %s", key, exc, exc_info=True)
            raise
        return client

    @classmethod
    @asynccontextmanager
    async def connection(cls, alias: str | None = None) -> AsyncIterator[Redis]:
        """
        Async context manager for Redis connection.

        Usage::

            async with RedisClient.connection() as r:
                await r.set("key", "value")
        """
        client = await cls.get(alias)
        try:
            yield client
        finally:
            # Nothing to close – pool handles connections
            pass

"""
# RedisClient 🔌

A fork-safe, asyncio-native helper that guarantees **one connection-pool per OS process**. 
Re-using the parent's TCP sockets after a `fork()` (common with Gunicorn / Uvicorn) breaks pub/sub; this wrapper avoids it.

```python
from symphony_concurrency.redis_client import RedisClient

# FastAPI lifespan
RedisClient.setup("redis://localhost:6379/0")  # registers alias "default"

async with RedisClient.connection() as r:
    await r.publish("events", "hello")
```

setup(url) – call once in every worker process. Safe re-entry.
setup(url, alias="cache") – additional pools.

get(alias="default") – returns the redis.asyncio.Redis instance; performs a cheap
PING health-check.

connection(alias=None) – async context-manager wrapper.

close() – optional explicit pool shutdown during graceful
termination.

Default max_connections = 64. Tune via ConnectionPool kwargs if you
expect heavy pub/sub traffic.
"""