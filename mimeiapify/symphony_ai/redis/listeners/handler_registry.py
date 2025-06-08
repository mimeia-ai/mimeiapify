"""Expiration-handler registry (thread-safe, process-local)."""

from __future__ import annotations
import asyncio, logging
from functools import wraps
from typing import Callable, Coroutine, Any, Dict, Optional
from pydantic import BaseModel, Field

from mimeiapify.symphony_ai.redis.redis_handler.utils.key_factory import KeyFactory

logger = logging.getLogger("Redis ExpirationHandlerRegistry")

AsyncHandler = Callable[[str, str], Coroutine[Any, Any, None]]


class ExpirationHandlerRegistry(BaseModel):
    """
    Map *key-prefix*  →  async handler coroutine.

    Prefix format we expect in keys:
        <tenant>:EXPTRIGGER:<action>:<identifier>
    """
    
    keys: KeyFactory = Field(default_factory=KeyFactory)
    handlers: Dict[str, AsyncHandler] = Field(default_factory=dict)
    
    model_config = {"arbitrary_types_allowed": True}

    def model_post_init(self, __context) -> None:
        """Called after Pydantic initialization"""
        logger.info("Expiration-handler registry initialised")

    # ------------------------------------------------------------------ API
    def on_expire_action(self, action_name: str) -> Callable[[AsyncHandler], AsyncHandler]:
        """
        Decorator:

            @expiration_registry.on_expire_action("process_message_batch")
            async def _handler(identifier: str, full_key: str): ...
        """
        full_prefix = f"{self.keys.trigger_prefix}:{action_name}:"

        def decorator(fn: AsyncHandler) -> AsyncHandler:
            if not asyncio.iscoroutinefunction(fn):
                raise TypeError("Handler must be *async*")
            if full_prefix in self.handlers:
                logger.warning("Overwriting trigger handler for '%s'", full_prefix)
            self.handlers[full_prefix] = fn
            logger.info("Registered trigger '%s' → %s", full_prefix, fn.__name__)

            @wraps(fn)
            async def wrapper(*a, **k):
                return await fn(*a, **k)

            return wrapper

        return decorator

    # --------------------------------------------------------- look-ups
    def _best_match(self, key: str) -> Optional[str]:
        return max((p for p in self.handlers if key.startswith(p)), key=len, default=None)

    def resolve(self, expired_key: str) -> Optional[tuple[AsyncHandler, str]]:
        """
        Return `(handler, identifier)` or `None` if no handler matches.
        """
        prefix = self._best_match(expired_key)
        if not prefix:
            return None
        identifier = expired_key.removeprefix(prefix).split(":", 1)[-1]
        return self.handlers[prefix], identifier


# single shared instance
expiration_registry = ExpirationHandlerRegistry() 