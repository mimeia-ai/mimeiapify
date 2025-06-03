# mimeiapify/symphony_ai/symphony_concurrency/globals.py
import os, asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import Optional, ClassVar
from pydantic import BaseModel, Field, PositiveInt, ConfigDict
from redis.asyncio import Redis
import anyio
import logging

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
        redis_url (str): Redis connection URL (default: 'redis://localhost:6379/0').
    """
    workers_user:  PositiveInt = Field(default_factory=lambda: os.cpu_count() * 4)
    workers_tool:  PositiveInt = 32
    workers_agent: PositiveInt = 16
    max_concurrent: PositiveInt = 128
    redis_url: str = "redis://localhost:6379/0"

    model_config = ConfigDict(extra="forbid")


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
    _instance: ClassVar["GlobalSymphony"] | None = None

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
            log.info(f"Setting up Redis at {cfg.redis_url}")
            RedisClient.setup(cfg.redis_url)     # sync
            self.redis = await RedisClient.get() # <- await, not asyncio.run
            log.debug("Redis connection established.")
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

async def startup():
    cfg = GlobalSymphonyConfig(redis_url="redis://cache:6379/2",
                               workers_tool=64)
    await GlobalSymphony.create(cfg)

sym = GlobalSymphony.get()            # anywhere in your code
sym.pool_tool.submit(do_io_blocking)  # reuse shared pool
```
Call GlobalSymphony.create() once per worker process (e.g. in
FastAPI lifespan). All subsequent GlobalSymphony.get() calls return the
same instance.

Set redis_url='' if you do not need Redis.
"""