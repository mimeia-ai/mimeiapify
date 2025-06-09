"""
AsyncBaseTool
=============

A *synchronous-looking* Agency-Swarm tool that internally awaits coroutines
on the **main event-loop** managed by GlobalSymphony.

Usage
-----

```python
from agency_swarm.tools import BaseTool
from mimeiapify.symphony_ai.symphony_concurrency.tools.async_tool import AsyncBaseTool
from mimeiapify.symphony_ai.redis.context import _current_ss

class RunQuery(AsyncBaseTool):
    query: str

    async def _arun(self) -> str:
        db = ...  # async client previously stashed in GlobalSymphony
        rows = await db.fetch(self.query)
        return str(rows)            # <- returned to Agent as normal

# in agent json schema
tools = [RunQuery]
```

"""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Awaitable
from agency_swarm.tools import BaseTool
from pydantic import ConfigDict

from mimeiapify.symphony_ai.symphony_concurrency.globals import GlobalSymphony
from mimeiapify.symphony_ai.redis.context import _current_ss
from mimeiapify.symphony_ai.redis.redis_handler.shared_state import RedisSharedState

logger = logging.getLogger("symphony.tools.async")

__all__ = ["AsyncBaseTool"]


class AsyncBaseTool(BaseTool):
    """
    Derive from this class instead of `BaseTool` when your tool must perform
    *async* I/O (httpx, asyncpg, Supabase, …) **but** the Agency-Swarm core
    expects a *blocking* `run()`.

    Implement the coroutine `_arun(self, *args, **kwargs)`; **do not** override
    `run()`.  At runtime `run()`:

    1. Grabs the main loop from `GlobalSymphony`.
    2. Schedules `_arun()` with `asyncio.run_coroutine_threadsafe()`.
    3. Blocks the worker thread until the coroutine completes.
    """

    # ------------------------------------------------------------------
    # 🛠  Pydantic config — allow BaseTool to attach `name`, `description`, …
    model_config = ConfigDict(
        extra="allow",               # <- key line: let BaseTool set dynamic attributes
        arbitrary_types_allowed=True
    )

    # --------------------------- public API -----------------------------

    def run(self, *args: Any, **kwargs: Any) -> Any:  # noqa: D401, PLR0911
        """
        Synchronous entry-point invoked by Agency-Swarm.  Do **not** change.
        """
        sym = GlobalSymphony.get()
        loop = sym.loop
        try:
            coro = self._arun(*args, **kwargs)
        except AttributeError:
            raise NotImplementedError(
                f"{self.__class__.__name__} must implement async def _arun(...)"
            ) from None

        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result()        # blocks this worker thread only
        except Exception as exc:          # pragma: no cover
            # Defensive logging that won't fail if name attribute is missing
            tool_name = getattr(self, "name", self.__class__.__name__)
            logger.exception("Tool %s raised: %s", tool_name, exc)
            raise

    # ------------------------ subclass contract ------------------------

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        """
        Override in subclass; perform async work and return *plain* data that
        the agent can serialise (str, dict, list, pydantic model, …).
        """
        raise NotImplementedError

    # ===================================================================
    # 🆕  Redis-shared-state helpers
    # ===================================================================

    # quick alias so subclasses can do `self.ss.get(...)`
    @property
    def ss(self) -> RedisSharedState:
        """
        The request-bound :class:`RedisSharedState`.

        Raises
        ------
        LookupError
            if no shared state is bound to the current context
            (i.e., tool invoked outside a FastAPI request).
        """
        return _current_ss.get()

    # -- convenience sync wrappers --------------------------------------
    #
    # Tools are still *sync* from Agency-Swarm's perspective.  These tiny
    # helpers make it trivial to call the async Redis repo without
    # repeating the bridge pattern.

    def _await(self, coro: Awaitable[Any], /, timeout: int | None = None) -> Any:
        """
        Run *coro* on the main event-loop and block this thread.

        Timeout (seconds) can be passed; otherwise `.result()` waits forever.
        """
        loop = GlobalSymphony.get().loop
        fut  = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout)

    # CRUD Sync thin-wrappers -------------------------------------------------

    def get_state(self, key: str) -> dict | None:
        return self._await(self.ss.get(key))

    def upsert_state(self, key: str, data: dict, ttl: int | None = None) -> bool:
        return self._await(self.ss.upsert(key, data))

    def get_field(self, key: str, field: str) -> Any:
        return self._await(self.ss.get_field(key, field))

    def update_field(self, key: str, field: str, value: Any, ttl: int | None = None) -> bool:
        return self._await(self.ss.update_field(key, field, value, ttl))

    def delete_field(self, key: str, field: str) -> int:
        """Delete a specific field from the state hash. Returns number of fields deleted (0 or 1)."""
        return self._await(self.ss.delete_field(key, field))

    def delete_state(self, key: str) -> int:
        """Delete the entire state hash. Returns number of keys deleted (0 or 1)."""
        return self._await(self.ss.delete(key))

    def clear_all_states(self) -> int:
        """Delete all states for this user. Returns number of states deleted."""
        return self._await(self.ss.clear_all_states())

    def list_states(self) -> list[str]:
        """List all state names for this user."""
        return self._await(self.ss.list_states())

    def state_exists(self, key: str) -> bool:
        """Check if state exists."""
        return self._await(self.ss.exists(key)) 