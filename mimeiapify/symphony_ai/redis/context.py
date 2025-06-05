"""Context variable holding the current request's :class:`RedisSharedState`."""

from contextvars import ContextVar
from .redis_handler.shared_state import RedisSharedState

_current_ss: ContextVar[RedisSharedState] = ContextVar("current_shared_state")

__all__ = ["_current_ss", "RedisSharedState"] 