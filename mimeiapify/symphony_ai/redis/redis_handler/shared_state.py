from __future__ import annotations
from typing import Any, Dict, Optional, Mapping
from pydantic import BaseModel, Field
import logging

from .utils.tenant_cache import TenantCache
from ..ops import hget, hdel, scan_keys
from .utils.serde import dumps, loads

logger = logging.getLogger("RedisSharedState")


class RedisSharedState(TenantCache):
    """
    Repository for shared state management between tools and agents.
    
    Stores tool/agent scratch-space under keys like:
    <tenant>:SS:<state_name>:<user_id>
    
    This replaces the previous RedisSharedState class with a focused,
    single-responsibility implementation that reuses our refactored components.
    
    Example usage:
        shared_state = SharedState(tenant="mimeia", user_id="user123")
        await shared_state.set("conversation", {"step": 1, "context": {...}})
        step = await shared_state.get_field("conversation", "step")
    """
    user_id: str = Field(..., min_length=1)
    redis_alias: str = "symphony_shared_state"

    def _key(self, state_name: str) -> str:
        """Build shared state key using KeyFactory"""
        return self.keys.shared_state(self.tenant, state_name, self.user_id)

    # ---- Public API for shared state management -------------------------
    async def upsert(self, state_name: str, data: Mapping[str, Any]) -> bool:
        """
        Store the entire hash for a given state name (Redis HSET upsert behavior).
        Overwrites existing data and renews TTL.
        
        Args:
            state_name: Name of the state (e.g., "conversation", "context")
            data: Dictionary of state data to store
        """
        key = self._key(state_name)
        return await self._hset_with_ttl(key, dict(data))

    async def get(self, state_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve all fields of the hash for the given state name.
        
        Args:
            state_name: Name of the state to retrieve
            
        Returns:
            Dictionary of state data or None if not found
        """
        key = self._key(state_name)
        return await self._get_hash(key)

    async def get_field(self, state_name: str, field: str) -> Optional[Any]:
        """
        Retrieve a single field from the state hash.
        
        Args:
            state_name: Name of the state
            field: Field name within the state
            
        Returns:
            Field value or None if not found
        """
        key = self._key(state_name)
        raw_value = await hget(key, field, alias=self.redis_alias)
        return loads(raw_value) if raw_value is not None else None

    async def update_field(self, state_name: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Update a single field in the state hash and renew TTL.
        
        Args:
            state_name: Name of the state
            field: Field name to update
            value: New value for the field
            ttl: Optional TTL override
        """
        key = self._key(state_name)
        return await self._hset_with_ttl(key, {field: value}, ttl)

    async def delete_field(self, state_name: str, field: str) -> int:
        """
        Delete a specific field from the state hash.
        
        Args:
            state_name: Name of the state
            field: Field name to delete
            
        Returns:
            Number of fields deleted (0 or 1)
        """
        # Note: hdel doesn't have an inherited equivalent, so direct ops call is appropriate
        key = self._key(state_name)
        return await hdel(key, field, alias=self.redis_alias)

    async def delete(self, state_name: str) -> int:
        """
        Delete the entire state hash.
        
        Args:
            state_name: Name of the state to delete
            
        Returns:
            Number of keys deleted (0 or 1)
        """
        key = self._key(state_name)
        return await self.delete_key(key)

    async def exists(self, state_name: str) -> bool:
        """Check if state exists"""
        key = self._key(state_name)
        return await self.key_exists(key)

    async def list_states(self) -> list[str]:
        """
        List all state names for this user.
        Returns the state names without the full key prefix.
        """
        pattern = f"{self.tenant}:{self.keys.shared_state_prefix}:*:{self.user_id.replace(':', '_')}"
        cursor = '0'
        state_names = []
        
        try:
            while True:
                next_cursor, keys_batch = await scan_keys(
                    match_pattern=pattern, cursor=cursor, count=100, alias=self.redis_alias
                )
                
                for full_key in keys_batch:
                    # Extract state name from key: tenant:SS:state_name:user_id
                    parts = full_key.split(':')
                    if len(parts) >= 4 and parts[1] == self.keys.shared_state_prefix:
                        state_name = ':'.join(parts[2:-1])  # Handle state names with colons
                        # Convert back from safe name if needed
                        state_name = state_name.replace('_', ':') if '_' in state_name else state_name
                        state_names.append(state_name)
                
                if next_cursor == '0':
                    break
                cursor = next_cursor
                    
        except Exception as e:
            logger.error(f"Error listing states for user '{self.user_id}': {e}", exc_info=True)
            
        return state_names

    async def clear_all_states(self) -> int:
        """
        Delete all states for this user.
        
        Returns:
            Number of states deleted
        """
        pattern = f"{self.tenant}:{self.keys.shared_state_prefix}:*:{self.user_id.replace(':', '_')}"
        logger.info(f"Clearing all shared states for user '{self.user_id}' (pattern: '{pattern}')")
        return await self._delete_by_pattern(pattern) 