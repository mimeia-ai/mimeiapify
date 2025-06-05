"""Context variable holding the current request's :class:`SharedStateRepo`."""

from contextvars import ContextVar
from ...redis.redis_handler.shared_state_repo import SharedStateRepo

_current_ss: ContextVar[SharedStateRepo] = ContextVar("current_shared_state")

__all__ = ["_current_ss", "SharedStateRepo"]
