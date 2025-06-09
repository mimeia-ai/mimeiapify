# mimeiapify/symphony_ai/symphony_concurrency/globals.py
import os, asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import Optional, ClassVar
from pydantic import BaseModel, Field, PositiveInt, ConfigDict
from redis.asyncio import Redis
import anyio
import logging
from collections import defaultdict
from redis.exceptions import ResponseError

from ..redis.redis_client import RedisClient

log = logging.getLogger("GlobalSymphony")

class GlobalSymphonyConfig(BaseModel):
    """
    Configuration for thread pools and shared resources used by GlobalSymphony.

    Attributes:
        workers_user (PositiveInt): Number of threads for user pool (default: CPU * 4).
        workers_tool (PositiveInt): Number of threads for tool pool (default: 32).
        workers_agent (PositiveInt): Number of threads for agent pool (default: 16).
        max_concurrent (PositiveInt): Maximum concurrent tasks (default: 128).
        redis_url (str | dict[str, str]): Single Redis URL or explicit URLs for 4 pools (default: 'redis://localhost:6379').
        redis_enable_key_events (bool): Enable Redis keyspace events bootstrap (default: True).
        redis_keyevent_flags (str): Redis keyspace event flags to enable (default: 'Ex').
    """
    workers_user:  PositiveInt = Field(default_factory=lambda: os.cpu_count() * 4)
    workers_tool:  PositiveInt = 32
    workers_agent: PositiveInt = 16
    max_concurrent: PositiveInt = 128
    redis_url: str | dict[str, str] = "redis://localhost:6379"
    # NEW Redis server bootstrap options
    redis_enable_key_events: bool = True            # turn CONFIG SET on/off
    redis_keyevent_flags: str = "Ex"                # usually "Ex", can be "Kxg" etc.

    model_config = ConfigDict(extra="forbid")


async def _bootstrap_redis_servers(
    *,
    aliases: list[str],
    flags: str = "Ex",
    timeout: int = 10,
) -> None:
    """
    Ensure each *physical* Redis server (host:port) has notify-keyspace-events
    set to `flags`.  Runs once per server even if many DBs share it.
    """
    # 1. deduplicate by host:port
    by_server = defaultdict(list)  # (host,port) -> [alias, ...]
    for alias in aliases:
        redis_client = await RedisClient.get(alias)
        # Extract host and port from connection pool
        conn_kwargs = redis_client.connection_pool.connection_kwargs
        host = conn_kwargs.get("host", "localhost")
        port = conn_kwargs.get("port", 6379)
        by_server[(host, port)].append(alias)

    # 2. iterate servers
    for (host, port), alias_list in by_server.items():
        alias = alias_list[0]              # pick any client on that server
        redis = await RedisClient.get(alias)

        try:
            async with asyncio.timeout(timeout):
                await redis.ping()
        except Exception as exc:
            log.critical("Redis %s:%s unreachable: %s", host, port, exc)
            continue

        try:
            cfg = await redis.config_get("notify-keyspace-events")
            current = cfg.get("notify-keyspace-events", "")
            if all(f in current for f in flags):
                log.debug("Redis %s:%s already has '%s'", host, port, current)
                continue

            await redis.config_set("notify-keyspace-events", current + flags)
            log.info("Set notify-keyspace-events='%s' on %s:%s", current + flags, host, port)
        except ResponseError as exc:
            log.warning("Cannot CONFIG SET on %s:%s (%s). "
                        "Manually ensure notify-keyspace-events includes '%s'.",
                        host, port, exc, flags)
        except Exception as exc:           # pragma: no cover
            log.error("Unexpected error bootstrapping Redis %s:%s: %s", host, port, exc, exc_info=True)


class GlobalSymphony:
    """
    Singleton runtime container for event loop, thread pools, concurrency limiter, and optional Redis.

    Use `await GlobalSymphony.create(cfg)` to initialize, then `GlobalSymphony.get()` to access the singleton.

    Attributes:
        loop (asyncio.AbstractEventLoop): The running event loop.
        pool_user (ThreadPoolExecutor): Thread pool for user tasks.
        pool_tool (ThreadPoolExecutor): Thread pool for tool tasks.
        pool_agent (ThreadPoolExecutor): Thread pool for agent tasks.
        limiter (anyio.CapacityLimiter): Concurrency limiter.
        redis (Optional[Redis]): Optional Redis connection.
    """
    _instance: ClassVar[Optional["GlobalSymphony"]] = None

    # ---- runtime attributes ----
    loop:            asyncio.AbstractEventLoop
    pool_user:       ThreadPoolExecutor
    pool_tool:       ThreadPoolExecutor
    pool_agent:      ThreadPoolExecutor
    limiter:         anyio.CapacityLimiter
    redis:           Optional[Redis]

    def __new__(cls, *_, **__):
        raise RuntimeError("Use GlobalSymphony.create()")

    @classmethod
    async def create(cls, cfg: GlobalSymphonyConfig) -> "GlobalSymphony":
        """
        Initialize the GlobalSymphony singleton with the given configuration.
        If already initialized, returns the existing instance.

        Args:
            cfg (GlobalSymphonyConfig): Configuration for pools and resources.

        Returns:
            GlobalSymphony: The singleton instance.
        """
        if cls._instance is not None:
            log.info("GlobalSymphony already initialized; returning existing instance.")
            return cls._instance     # idempotent

        log.debug("Initializing GlobalSymphony singleton...")
        loop = asyncio.get_running_loop()        # must be inside async ctx
        self = cls._instance = object.__new__(cls)
        self.loop = loop

        # Thread-pools
        log.debug(f"Creating ThreadPoolExecutor: user={cfg.workers_user}, tool={cfg.workers_tool}, agent={cfg.workers_agent}")
        self.pool_user  = ThreadPoolExecutor(max_workers=cfg.workers_user,
                                             thread_name_prefix="user")
        self.pool_tool  = ThreadPoolExecutor(max_workers=cfg.workers_tool,
                                             thread_name_prefix="tool")
        self.pool_agent = ThreadPoolExecutor(max_workers=cfg.workers_agent,
                                             thread_name_prefix="agent")

        # Concurrency limiter
        log.debug(f"Setting up CapacityLimiter: max_concurrent={cfg.max_concurrent}")
        self.limiter = anyio.CapacityLimiter(cfg.max_concurrent)

        # Optional Redis
        if cfg.redis_url:
            if isinstance(cfg.redis_url, str):
                log.info(f"Setting up Redis with single URL: {cfg.redis_url}")
                RedisClient.setup_single_url(cfg.redis_url)
                log.debug("Redis pools established from single URL.")
            else:  # dict mapping
                log.info(f"Setting up Redis with explicit URLs for pools: {list(cfg.redis_url.keys())}")
                try:
                    RedisClient.setup_multiple_urls(cfg.redis_url)
                    log.debug("Redis pools established from multiple URLs.")
                except ValueError as e:
                    log.error(f"Invalid Redis pool configuration: {e}")
                    raise ValueError(f"Redis setup failed: {e}") from e
            
            # Bootstrap Redis server(s) with keyspace notifications
            if cfg.redis_enable_key_events:
                await _bootstrap_redis_servers(
                    aliases=list(RedisClient._clients.keys()),
                    flags=cfg.redis_keyevent_flags,
                    timeout=10
                )
            
            # Keep default client handy (may still be None)
            self.redis = await RedisClient.get("default")
        else:
            self.redis = None
            log.info("Redis not configured (redis_url is empty).")
        log.info("GlobalSymphony initialized.")
        return self

    @classmethod
    def get(cls) -> "GlobalSymphony":
        """
        Get the singleton instance of GlobalSymphony.
        Raises if not yet initialized.

        Returns:
            GlobalSymphony: The singleton instance.
        """
        if cls._instance is None:
            log.error("GlobalSymphony.get() called before create().")
            raise RuntimeError("GlobalSymphony.create() not called yet")
        return cls._instance

    @classmethod
    async def shutdown(cls) -> None:
        """
        Gracefully shutdown the GlobalSymphony singleton and clean up all resources.

        This method should be called during application shutdown (e.g., FastAPI lifespan)
        to properly close thread pools, Redis connections, and reset the singleton state.

        Example:
            ```python
            # In FastAPI lifespan
            @asynccontextmanager
            async def lifespan(app: FastAPI):
                # Startup
                await GlobalSymphony.create(config)
                yield
                # Shutdown
                await GlobalSymphony.shutdown()
            ```
        """
        if cls._instance is None:
            log.debug("GlobalSymphony.shutdown() called but no instance exists.")
            return

        instance = cls._instance
        log.info("Shutting down GlobalSymphony...")

        # Shutdown thread pools gracefully
        try:
            log.debug("Shutting down thread pools...")
            instance.pool_user.shutdown(wait=True)
            instance.pool_tool.shutdown(wait=True) 
            instance.pool_agent.shutdown(wait=True)
            log.debug("Thread pools shut down successfully.")
        except Exception as exc:
            log.error("Error shutting down thread pools: %s", exc)

        # Close Redis connections
        try:
            log.debug("Closing Redis connections...")
            # Close all Redis clients managed by RedisClient
            await RedisClient.close()
            log.debug("Redis connections closed successfully.")
        except Exception as exc:
            log.error("Error closing Redis connections: %s", exc)

        # Reset singleton instance
        cls._instance = None
        log.info("GlobalSymphony shutdown completed.")


"""
# GlobalSymphony 📯

A runtime singleton that centralises the **event-loop** plus three category-
specific `ThreadPoolExecutor`s and an optional **Redis** connection.

| Resource        | Purpose                               | Default size     |
|-----------------|---------------------------------------|------------------|
| `pool_user`     | Outer `get_completion` calls          | `CPU × 4` threads |
| `pool_tool`     | Blocking DB / file / subprocess work  | 32 threads        |
| `pool_agent`    | Inter-agent `SendMessage` recursion   | 16 threads        |
| `limiter`       | AnyIO `CapacityLimiter` for graceful back-pressure | 128 permits |

```python
from symphony_concurrency.globals import GlobalSymphony, GlobalSymphonyConfig

# Single Redis URL - creates 4 predefined pools automatically
async def startup():
    cfg = GlobalSymphonyConfig(redis_url="redis://localhost:6379",
                               workers_tool=64)
    await GlobalSymphony.create(cfg)

# Multi-URL Redis setup with explicit pool URLs  
async def startup_with_explicit_pools():
    cfg = GlobalSymphonyConfig(
        redis_url={
            "default": "redis://localhost:6379/15",
            "handlers": "redis://cache:6379/10", 
            "expiry": "redis://localhost:6379/9",
            "pubsub": "redis://localhost:6379/8",
        },
        workers_tool=64,
        redis_enable_key_events=True,  # Automatically set notify-keyspace-events
        redis_keyevent_flags="Ex"      # Enable expiry events
    )
    await GlobalSymphony.create(cfg)

# Proper shutdown for resource cleanup
async def shutdown():
    await GlobalSymphony.shutdown()

sym = GlobalSymphony.get()            # anywhere in your code
sym.pool_tool.submit(do_io_blocking)  # reuse shared pool
```

Call GlobalSymphony.create() once per worker process (e.g. in
FastAPI lifespan). All subsequent GlobalSymphony.get() calls return the
same instance. Always call GlobalSymphony.shutdown() during application
shutdown to properly close thread pools and Redis connections.

**Redis Configuration:**
- `redis_url` as a string: Creates 4 pools automatically (default/15, handlers/10, expiry/9, pubsub/8)
- `redis_url` as a dict: Must provide all 4 pool URLs explicitly
- Set `redis_url=''` if you do not need Redis

**Redis Keyspace Events:**
- `redis_enable_key_events=True`: Automatically configures notify-keyspace-events on Redis servers
- `redis_keyevent_flags="Ex"`: Enables expiry events (default), can be "Kxg" for more event types
- Bootstrap runs once per unique Redis server (host:port), even with multiple pools

Access different Redis pools via `RedisClient.get(alias)` after setup:
- `RedisClient.get("default")` - general operations (db 15)
- `RedisClient.get("handlers")` - TTL handlers (db 10)  
- `RedisClient.get("expiry")` - expiry listener (db 9)
- `RedisClient.get("pubsub")` - pub/sub messaging (db 8)
"""