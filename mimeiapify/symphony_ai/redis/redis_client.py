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
from typing import Optional, AsyncIterator, ClassVar, Literal
from contextlib import asynccontextmanager
import logging

from redis.asyncio import Redis, ConnectionPool

log = logging.getLogger("RedisClient")

# Predefined Redis pool aliases with their database numbers
PoolAlias = Literal["default", "handlers", "expiry", "pubsub", "symphony_shared_state", "user"]

POOL_DB_MAPPING = {
    "default": 15,
    "user": 11,
    "handlers": 10, 
    "symphony_shared_state": 9,
    "expiry": 8,
    "pubsub": 7
}


class RedisClient:
    """
    Fork-safe, asyncio-native **multi-pool** Redis manager.

    Supports exactly 4 predefined pools:
    - "default" (db 15): General-purpose operations
    - "handlers" (db 10): TTL-based handlers
    - "expiry" (db 9): Key-expiry listener  
    - "pubsub" (db 8): AsyncSendMessage pub/sub

    Every worker process keeps its own pools to avoid post-fork descriptor reuse.
    """

    _pools: ClassVar[dict[PoolAlias, ConnectionPool]] = {}
    _clients: ClassVar[dict[PoolAlias, Redis]] = {}
    _pid: ClassVar[Optional[int]] = None

    # ---------- life-cycle --------------------------------------------------

    @classmethod
    def setup_single_url(cls, base_url: str, *, max_connections: int = 64) -> None:
        """
        Set up all 4 Redis pools from a single base URL by appending database numbers.
        
        Args:
            base_url: Base Redis URL (e.g., "redis://localhost:6379")
            max_connections: Max connections per pool
            
        Example:
            RedisClient.setup_single_url("redis://localhost:6379")
            # Creates:
            # - default: redis://localhost:6379/15
            # - handlers: redis://localhost:6379/10  
            # - expiry: redis://localhost:6379/9
            # - pubsub: redis://localhost:6379/8
        """
        # Ensure base URL doesn't already have a database
        if base_url.rstrip('/').split('/')[-1].isdigit():
            log.warning(f"Base URL '{base_url}' appears to contain a database number. Using as-is for base.")
            base_url = '/'.join(base_url.rstrip('/').split('/')[:-1])
        
        for alias, db_num in POOL_DB_MAPPING.items():
            url = f"{base_url.rstrip('/')}/{db_num}"
            cls._setup_pool(alias, url, max_connections)

    @classmethod  
    def setup_multiple_urls(cls, urls: dict[PoolAlias, str], *, max_connections: int = 64) -> None:
        """
        Set up Redis pools from explicit URLs for each pool.
        
        Args:
            urls: Mapping of pool alias to Redis URL
            max_connections: Max connections per pool
            
        Example:
            RedisClient.setup_multiple_urls({
                "default": "redis://localhost:6379/15",
                "handlers": "redis://cache:6379/10",
                "expiry": "redis://localhost:6379/9", 
                "pubsub": "redis://localhost:6379/8"
            })
        """
        # Validate all required aliases are provided
        missing = set(POOL_DB_MAPPING.keys()) - set(urls.keys())
        if missing:
            raise ValueError(f"Missing required pool aliases: {missing}")
        
        extra = set(urls.keys()) - set(POOL_DB_MAPPING.keys())
        if extra:
            raise ValueError(f"Unknown pool aliases: {extra}. Only {list(POOL_DB_MAPPING.keys())} are allowed.")
            
        for alias, url in urls.items():
            cls._setup_pool(alias, url, max_connections)

    @classmethod
    def _setup_pool(cls, alias: PoolAlias, url: str, max_connections: int) -> None:
        """Internal helper to set up a single pool."""
        pid = os.getpid()
        if cls._pid is None:
            cls._pid = pid
        elif cls._pid != pid:
            # process forked – discard inherited pools
            cls._pools.clear()
            cls._clients.clear()
            cls._pid = pid

        if alias in cls._pools:
            log.debug(f"Redis pool '{alias}' already exists in PID {pid}")
            return

        log.info(f"Initialising Redis pool '{alias}' in PID {pid} ({url})")
        pool = ConnectionPool.from_url(
            url,
            decode_responses=True,
            encoding="utf-8",
            max_connections=max_connections,
        )
        client = Redis(connection_pool=pool)
        cls._pools[alias] = pool
        cls._clients[alias] = client

    @classmethod
    async def close(cls, alias: PoolAlias | None = None) -> None:
        """Close one or all Redis pools for this process."""
        pid = os.getpid()
        if cls._pid != pid:
            log.debug("No Redis pool to close for PID %s", pid)
            return

        aliases = [alias] if alias else list(cls._pools.keys())
        for a in aliases:
            pool = cls._pools.pop(a, None)
            if pool:
                log.info("Closing Redis pool '%s' in PID %s", a, pid)
                await pool.disconnect()
                cls._clients.pop(a, None)
        if not cls._pools:
            cls._pid = None

    # ---------- access helpers ---------------------------------------------

    @classmethod
    async def get(cls, alias: PoolAlias = "default") -> Redis:
        """Return the Redis client for the given alias."""
        client = cls._clients.get(alias)
        if client is None or cls._pid != os.getpid():
            log.error("RedisClient.get() called before setup() in this process.")
            raise RuntimeError(
                f"RedisClient must be set up for alias '{alias}' first."
            )
        # quick health check – keep it cheap
        try:
            await client.ping()
            log.debug("Redis PING successful for '%s'.", alias)
        except Exception as exc:
            log.error("Redis ping failed for '%s': %s", alias, exc, exc_info=True)
            raise
        return client

    @classmethod
    @asynccontextmanager
    async def connection(cls, alias: PoolAlias = "default") -> AsyncIterator[Redis]:
        """
        Async context manager for Redis connection.

        Usage::

            async with RedisClient.connection("handlers") as r:
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

A fork-safe, asyncio-native helper with **4 predefined Redis pools**:

| Pool      | Database | Purpose                    |
|-----------|----------|----------------------------|
| default   | 15       | General-purpose operations |  
| handlers  | 10       | TTL-based handlers         |
| expiry    | 9        | Key-expiry listener        |
| pubsub    | 8        | AsyncSendMessage pub/sub   |

```python
from symphony_concurrency.redis_client import RedisClient

# Option 1: Single URL (creates all 4 pools automatically)
RedisClient.setup_single_url("redis://localhost:6379")

# Option 2: Explicit URLs per pool
RedisClient.setup_multiple_urls({
    "default": "redis://localhost:6379/15",
    "handlers": "redis://cache:6379/10", 
    "expiry": "redis://localhost:6379/9",
    "pubsub": "redis://localhost:6379/8"
})

# Usage
async with RedisClient.connection("handlers") as r:
    await r.set("key", "value")
    
redis = await RedisClient.get("expiry")
await redis.publish("events", "hello")
```

All pools are fork-safe and isolated per worker process.
"""