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
    Fork-safe, asyncio-native Redis client manager.

    Ensures one connection pool per OS process. Handles safe setup, teardown, and access.

    Class Attributes:
        _instance (Optional[Redis]): The Redis client instance for this process.
        _pool (Optional[ConnectionPool]): The Redis connection pool.
        _pid (Optional[int]): The process ID for which the pool is valid.
    """
    _instance: ClassVar[Optional[Redis]] = None
    _pool: ClassVar[Optional[ConnectionPool]] = None
    _pid: ClassVar[Optional[int]] = None

    # ---------- life-cycle --------------------------------------------------

    @classmethod
    def setup(cls, url: str, max_connections: int = 64) -> None:
        """
        Set up the Redis connection pool for the current process.
        Safe to call multiple times in the same PID (no-op if already set up).

        Args:
            url (str): Redis connection URL.
        """
        pid = os.getpid()
        if cls._pid == pid and cls._instance:
            log.debug("Redis already initialised in PID %s", pid)
            return

        log.info("Initialising Redis in PID %s for %s", pid, url)
        cls._pool = ConnectionPool.from_url(
            url,
            decode_responses=True,
            encoding="utf-8",
            max_connections=max_connections   # tweak as needed
        )
        cls._instance = Redis(connection_pool=cls._pool)
        cls._pid = pid
        log.debug("Redis connection pool created for PID %s", pid)

    @classmethod
    async def close(cls) -> None:
        """
        Close the Redis connection pool for the current process.
        """
        pid = os.getpid()
        if cls._pid != pid or cls._pool is None:
            log.debug("No Redis pool to close for PID %s", pid)
            return
        log.info("Closing Redis pool in PID %s", pid)
        await cls._pool.disconnect()
        cls._instance = cls._pool = cls._pid = None
        log.debug("Redis pool closed for PID %s", pid)

    # ---------- access helpers ---------------------------------------------

    @classmethod
    async def get(cls) -> Redis:
        """
        Get the Redis client for the current process.
        Performs a cheap health check (PING).

        Returns:
            Redis: The Redis client instance.
        Raises:
            RuntimeError: If setup() was not called in this process.
        """
        if cls._instance is None or cls._pid != os.getpid():
            log.error("RedisClient.get() called before setup() in this process.")
            raise RuntimeError(
                "RedisClient.setup() must be called in this process first."
            )
        # quick health check – keep it cheap
        try:
            await cls._instance.ping()
            log.debug("Redis PING successful.")
        except Exception as exc:
            log.error("Redis ping failed: %s", exc, exc_info=True)
            raise
        return cls._instance

    @classmethod
    @asynccontextmanager
    async def connection(cls) -> AsyncIterator[Redis]:
        """
        Async context manager for Redis connection.

        Usage::

            async with RedisClient.connection() as r:
                await r.set("key", "value")
        """
        client = await cls.get()
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
RedisClient.setup("redis://localhost:6379/0")

async with RedisClient.connection() as r:
    await r.publish("events", "hello")
```

setup(url) – call once in every worker process. Safe re-entry.

get() – returns the redis.asyncio.Redis instance; performs a cheap
PING health-check.

connection() – async context-manager wrapper.

close() – optional explicit pool shutdown during graceful
termination.

Default max_connections = 64. Tune via ConnectionPool kwargs if you
expect heavy pub/sub traffic.
"""