from __future__ import annotations
from datetime import datetime
import logging

from .utils.tenant_cache import TenantCache
from ..ops import setex
from .utils.serde import dumps

logger = logging.getLogger("RedisTrigger")


class RedisTrigger(TenantCache):
    """
    Repository for expiration trigger key management.
    
    Extracted from RedisHandler SECTION: Expiration Trigger Key Management:
    - set_action_trigger() -> set()
    - delete_action_trigger() -> delete()
    - delete_all_triggers_by_identifier() -> delete_all_by_identifier()
    
    Single Responsibility: Expiration trigger management only
    """
    redis_alias: str = "expiry"
    
    def _key(self, action: str, identifier: str) -> str:
        """Build trigger key using KeyFactory"""
        return self.keys.trigger(self.tenant, action, identifier)

    # ---- Public API extracted from RedisHandler Trigger methods -------------
    async def set(self, action: str, identifier: str, ttl_seconds: int) -> bool:
        """
        Set expiration trigger key (was set_action_trigger)
        
        Creates a key that will expire after ttl_seconds, triggering an action.
        The value is just a timestamp for debugging - the key expiration is what matters.
        """
        if ttl_seconds <= 0:
            logger.warning(f"Invalid TTL {ttl_seconds}s for trigger {action}:{identifier}. Skipping.")
            return False

        key = self._key(action, identifier)
        value = f"trigger:{datetime.utcnow().isoformat()}"
        serialized_value = dumps(value)

        logger.debug(f"Setting trigger '{key}' with TTL {ttl_seconds}s")
        # Note: Using setex directly as trigger keys are simple key-value pairs, not hashes
        return await setex(key, ttl_seconds, serialized_value, alias=self.redis_alias)

    async def delete(self, action: str, identifier: str) -> int:
        """Delete specific trigger key (was delete_action_trigger)"""
        key = self._key(action, identifier)
        logger.debug(f"Deleting trigger key '{key}'")
        return await self.delete_key(key)

    async def delete_all_by_identifier(self, identifier: str) -> int:
        """
        Delete all triggers for an identifier (was delete_all_triggers_by_identifier)
        
        This creates a pattern that matches all trigger types for the identifier:
        tenant:exptrigger:*:safe_identifier
        """
        safe_identifier = identifier.replace(":", "_")
        pattern = f"{self.tenant}:{self.keys.trigger_prefix}:*:{safe_identifier}"
        
        logger.info(f"Deleting all triggers for identifier '{identifier}' (pattern: '{pattern}')")
        return await self._delete_by_pattern(pattern) 