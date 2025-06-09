"""
UserThreads
===========

Light-weight repository wrapper that stores / retrieves **agent thread-ids**
for one user inside the `"user"` Redis pool (DB 11).

* Works with **Agency-Swarm v 0.6.x** `threads_callbacks`.
* No Airtable, no thread-pools, no busy-waits.
* Async API — call from the event-loop, or bridge with
  `asyncio.run_coroutine_threadsafe()` if you are inside a blocking agent
  thread.

Key Redis layout
----------------
```
<tenant>:user:<user_id>   # Redis hash (HSET)
└── agent_threads         # field containing a JSON object, e.g.
                         # {"main_thread":"...","CEO":{"Coder":"..."}}
```

Usage with Agency-Swarm v0.6.x
-------------------------------

```python
import asyncio
from mimeiapify.symphony_ai.symphony_concurrency.tools.user_threads import UserThreads
from mimeiapify.symphony_ai.symphony_concurrency.globals import GlobalSymphony
from agency_swarm import Agency

# Create UserThreads instance
ut = UserThreads(tenant="mimeia", user_id="user123")

# Option 1: From blocking context (Agency-Swarm v0.6.x)
agency = Agency(
    agents=[main_agent, ceo_agent, coder_agent],
    threads_callbacks={
        "load": lambda: asyncio.run_coroutine_threadsafe(
            ut.load_threads(), GlobalSymphony.get().loop
        ).result(),
        "save": lambda threads: asyncio.run_coroutine_threadsafe(
            ut.save_threads(threads), GlobalSymphony.get().loop
        ).result(),
    },
    max_prompt_tokens=4000,
    max_completion_tokens=4000,
)

# Option 2: From async context (recommended)
async def handle_request():
    threads = await ut.load_threads()
    # ... use threads with agency
    await ut.save_threads(updated_threads)
```

FastAPI Integration
-------------------

```python
from fastapi import FastAPI, WebSocket
from mimeiapify.symphony_ai.redis.context import _current_ss
from mimeiapify.symphony_ai.symphony_concurrency.tools.user_threads import UserThreads

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    while True:
        data = await websocket.receive_json()
        tenant = data.get("tenant", "default")
        user_id = data.get("user_id")
        
        # Create scoped UserThreads
        ut = UserThreads(tenant=tenant, user_id=user_id)
        
        # Load existing threads for continuity
        existing_threads = await ut.load_threads()
        
        # Create agency with thread persistence
        agency = Agency(
            agents=[main_agent],
            threads_callbacks={
                "load": lambda: asyncio.run_coroutine_threadsafe(
                    ut.load_threads(), GlobalSymphony.get().loop
                ).result(),
                "save": lambda threads: asyncio.run_coroutine_threadsafe(
                    ut.save_threads(threads), GlobalSymphony.get().loop
                ).result(),
            }
        )
        
        # Process message
        result = agency.get_completion(data["message"])
        await websocket.send_json({"response": result})
```
"""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict

from mimeiapify.symphony_ai.redis.redis_handler.user import RedisUser
from mimeiapify.symphony_ai.symphony_concurrency.globals import GlobalSymphony

logger = logging.getLogger("UserThreads")


class UserThreads:
    """
    Thin façade over :class:`RedisUser` to satisfy Agency-Swarm thread
    persistence callbacks (``load`` / ``save`` / ``delete``).

    This class provides thread-safe access to agent thread persistence,
    allowing Agency-Swarm to maintain conversation continuity across requests
    by storing thread IDs in Redis.

    Parameters
    ----------
    tenant : str
        Tenant / namespace prefix used by all Redis keys.
    user_id : str
        WhatsApp ID (or any unique user identifier) whose threads we manage.

    Attributes
    ----------
    tenant : str
        The tenant identifier for namespace isolation.
    user_id : str
        The unique user identifier.
    repo : RedisUser
        The underlying Redis repository for user data operations.

    Examples
    --------
    Basic usage:

    >>> ut = UserThreads(tenant="mimeia", user_id="user123")
    >>> threads = await ut.load_threads()
    >>> threads["main_thread"] = "thread_abc123"
    >>> await ut.save_threads(threads)

    With Agency-Swarm callbacks:

    >>> agency = Agency(
    ...     agents=[agent],
    ...     threads_callbacks={
    ...         "load": ut.sync_load_threads,
    ...         "save": ut.sync_save_threads,
    ...     }
    ... )
    """

    def __init__(self, *, tenant: str, user_id: str) -> None:
        self.tenant = tenant
        self.user_id = user_id
        self.repo = RedisUser(tenant=tenant, user_id=user_id)  # → "user" pool

    # ------------------------------------------------------------------ #
    # Public API used by Agency-Swarm v0.6 `threads_callbacks`
    # ------------------------------------------------------------------ #

    async def load_threads(self) -> Dict[str, Any]:
        """
        Fetch ``agent_threads`` hash-field from Redis.

        Returns an **empty dict** if no record exists, allowing Agency-Swarm
        to start fresh conversations.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing thread mappings. Structure varies by Agency-Swarm
            version but typically: {"main_thread": "thread_id", "Agent1": {"Agent2": "thread_id"}}

        Raises
        ------
        Exception
            If Redis operation fails (logged and returns empty dict for graceful degradation)

        Examples
        --------
        >>> threads = await ut.load_threads()
        >>> print(threads.get("main_thread"))  # None if no threads exist
        """
        try:
            data = await self.repo.get_field("agent_threads")
            logger.debug("Loaded threads for %s/%s: %s", self.tenant, self.user_id, data)
            return data or {}
        except Exception as exc:                         # pragma: no cover
            logger.error("load_threads failed for %s/%s: %s", self.tenant, self.user_id, exc)
            return {}

    async def save_threads(self, new_threads: Dict[str, Any]) -> None:
        """
        Compare current vs *new_threads* and write if changed.

        Performs an optimistic update - only writes to Redis if the thread
        structure has actually changed, reducing unnecessary I/O.

        Parameters
        ----------
        new_threads : Dict[str, Any]
            The updated thread structure from Agency-Swarm

        Raises
        ------
        Exception
            If Redis operation fails

        Examples
        --------
        >>> new_threads = {"main_thread": "thread_abc123"}
        >>> await ut.save_threads(new_threads)
        """
        try:
            current = await self.repo.get_field("agent_threads") or {}
            if current == new_threads:
                logger.debug("Threads unchanged for %s/%s; skipping save", self.tenant, self.user_id)
                return
            await self.repo.update_field("agent_threads", new_threads)
            logger.debug("Saved threads for %s/%s", self.tenant, self.user_id)
        except Exception as exc:                         # pragma: no cover
            logger.error("save_threads failed for %s/%s: %s", self.tenant, self.user_id, exc)
            raise

    async def delete_threads(self) -> None:
        """
        Remove the ``agent_threads`` field so the next request starts fresh.

        This is useful for resetting conversation state, clearing thread history,
        or handling user logout scenarios.

        Raises
        ------
        Exception
            If Redis operation fails

        Examples
        --------
        >>> await ut.delete_threads()  # User starts fresh conversation
        """
        try:
            await self.repo.delete_field("agent_threads")
            logger.debug("Deleted threads for %s/%s", self.tenant, self.user_id)
        except Exception as exc:                         # pragma: no cover
            logger.error("delete_threads failed for %s/%s: %s", self.tenant, self.user_id, exc)
            raise

    # ------------------------------------------------------------------ #
    # Synchronous bridge methods for Agency-Swarm v0.6.x callbacks
    # ------------------------------------------------------------------ #

    def sync_load_threads(self) -> Dict[str, Any]:
        """
        Synchronous wrapper for load_threads() compatible with Agency-Swarm callbacks.

        Uses asyncio.run_coroutine_threadsafe to bridge from blocking agency
        threads back to the main event loop.

        Returns
        -------
        Dict[str, Any]
            Thread mappings dictionary

        Examples
        --------
        >>> agency = Agency(
        ...     agents=[agent],
        ...     threads_callbacks={"load": ut.sync_load_threads}
        ... )
        """
        loop = GlobalSymphony.get().loop
        future = asyncio.run_coroutine_threadsafe(self.load_threads(), loop)
        return future.result()

    def sync_save_threads(self, threads: Dict[str, Any]) -> None:
        """
        Synchronous wrapper for save_threads() compatible with Agency-Swarm callbacks.

        Parameters
        ----------
        threads : Dict[str, Any]
            Thread mappings to save

        Examples
        --------
        >>> agency = Agency(
        ...     agents=[agent],
        ...     threads_callbacks={"save": ut.sync_save_threads}
        ... )
        """
        loop = GlobalSymphony.get().loop
        future = asyncio.run_coroutine_threadsafe(self.save_threads(threads), loop)
        future.result()

    def sync_delete_threads(self) -> None:
        """
        Synchronous wrapper for delete_threads() compatible with Agency-Swarm callbacks.

        Examples
        --------
        >>> ut.sync_delete_threads()  # Clear user's conversation history
        """
        loop = GlobalSymphony.get().loop
        future = asyncio.run_coroutine_threadsafe(self.delete_threads(), loop)
        future.result()

    # ------------------------------------------------------------------ #
    # Utility methods
    # ------------------------------------------------------------------ #

    async def thread_exists(self, agent_name: str = "main_thread") -> bool:
        """
        Check if a specific thread exists for this user.

        Parameters
        ----------
        agent_name : str, default "main_thread"
            Name of the agent/thread to check

        Returns
        -------
        bool
            True if thread exists, False otherwise
        """
        threads = await self.load_threads()
        return agent_name in threads

    async def get_thread_id(self, agent_name: str = "main_thread") -> str | None:
        """
        Get the thread ID for a specific agent.

        Parameters
        ----------
        agent_name : str, default "main_thread"
            Name of the agent whose thread ID to retrieve

        Returns
        -------
        str | None
            Thread ID if exists, None otherwise
        """
        threads = await self.load_threads()
        return threads.get(agent_name)

    async def clear_specific_thread(self, agent_name: str) -> None:
        """
        Remove a specific agent's thread while preserving others.

        Parameters
        ----------
        agent_name : str
            Name of the agent thread to remove
        """
        threads = await self.load_threads()
        if agent_name in threads:
            del threads[agent_name]
            await self.save_threads(threads)
            logger.debug("Cleared thread for agent '%s' (user: %s/%s)", 
                        agent_name, self.tenant, self.user_id)
