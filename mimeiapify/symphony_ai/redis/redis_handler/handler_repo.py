from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel
import logging

from .tenant_cache import TenantCache
from ..ops import hset_with_expire, hincrby_with_expire, hget, hset
from .serde import dumps

logger = logging.getLogger("HandlerRepo")


class HandlerRepo(TenantCache):
    """
    Repository for handler state management.
    
    Extracted from RedisHandler SECTION: Handler State Management:
    - set_handler_state() -> set()
    - get_handler_state() -> get()
    - get_handler_state_field() -> get_field()
    - update_handler_state_field() -> update_field()
    - increment_handler_state_field() -> increment_field()
    - append_to_handler_state_list_field() -> append_to_list()
    - handler_exists() -> exists()
    - delete_handler_state() -> delete()
    - create_or_update_handler() -> upsert()
    
    Single Responsibility: Handler state management only
    """
    
    def _key(self, handler_name: str, user_id: str) -> str:
        """Build handler key using KeyFactory"""
        return self.keys.handler(self.tenant, handler_name, user_id)

    # ---- Public API extracted from RedisHandler Handler methods -------------
    async def get(self, handler_name: str, user_id: str, models: Optional[Dict[str, type[BaseModel]]] = None) -> Optional[Dict[str, Any]]:
        """
        Get full handler state hash (was get_handler_state)
        
        Args:
            handler_name: Name of the handler
            user_id: User identifier
            models: Optional mapping of field names to BaseModel classes for typed deserialization
                   e.g., {"context": HandlerContext, "metadata": HandlerMetadata}
        """
        key = self._key(handler_name, user_id)
        result = await self._get_hash(key, models=models)
        if not result:
            logger.debug(f"Handler state not found for '{handler_name}:{user_id}'")
        return result

    async def set(self, handler_name: str, user_id: str, state_data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set handler state, overwriting existing (was set_handler_state)"""
        key = self._key(handler_name, user_id)
        return await self._hset_with_ttl(key, state_data, ttl)

    async def get_field(self, handler_name: str, user_id: str, field: str) -> Optional[Any]:
        """Get specific field from handler state (was get_handler_state_field)"""
        key = self._key(handler_name, user_id)
        return await hget(key, field)

    async def update_field(self, handler_name: str, user_id: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Update single field in handler state (was update_handler_state_field)"""
        key = self._key(handler_name, user_id)
        serialized_value = dumps(value)
        
        if ttl:
            # Use atomic version with TTL renewal
            hset_res, expire_res = await hset_with_expire(
                key=key,
                mapping={field: serialized_value},
                ttl=ttl
            )
            success = hset_res is not None and expire_res
            if not success:
                logger.warning(f"Failed to update handler field '{field}' for '{handler_name}:{user_id}'")
            return success
        else:
            # Use simple hset without TTL renewal
            result = await hset(key, field=field, value=serialized_value)
            return result >= 0

    async def increment_field(self, handler_name: str, user_id: str, field: str, increment: int = 1, ttl: Optional[int] = None) -> Optional[int]:
        """Atomically increment integer field (was increment_handler_state_field)"""
        key = self._key(handler_name, user_id)
        
        new_value, expire_res = await hincrby_with_expire(
            key=key,
            field=field,
            increment=increment,
            ttl=ttl or self.ttl_default
        )
        
        if new_value is not None and expire_res:
            return new_value
        else:
            logger.warning(f"Failed to increment handler field '{field}' for '{handler_name}:{user_id}'")
            return None

    async def append_to_list(self, handler_name: str, user_id: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Append value to list field (was append_to_handler_state_list_field)"""
        key = self._key(handler_name, user_id)
        return await self._append_to_list_field(key, field, value, ttl)

    async def exists(self, handler_name: str, user_id: str) -> bool:
        """Check if handler state exists (was handler_exists)"""
        key = self._key(handler_name, user_id)
        return await self.key_exists(key)

    async def delete(self, handler_name: str, user_id: str) -> int:
        """Delete handler state (was delete_handler_state)"""
        key = self._key(handler_name, user_id)
        return await self.delete_key(key)

    async def upsert(self, handler_name: str, user_id: str, state_data: Dict[str, Any], ttl: Optional[int] = None, models: Optional[Dict[str, type[BaseModel]]] = None) -> Optional[Dict[str, Any]]:
        """
        Merge new data with existing state and save (was create_or_update_handler)
        Returns the final merged state or None on failure
        
        Args:
            handler_name: Name of the handler
            user_id: User identifier  
            state_data: New state data to merge
            ttl: Optional TTL override
            models: Optional mapping for BaseModel deserialization when reading existing state
        """
        logger.debug(f"Upsert handler '{handler_name}' for user '{user_id}'")
        
        # Get existing state with optional BaseModel deserialization
        existing_state = await self.get(handler_name, user_id, models=models) or {}
        
        # Merge new data with existing
        new_state = {
            **existing_state,
            **state_data,
            "handler_type": handler_name,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Save merged state
        success = await self.set(handler_name, user_id, new_state, ttl)
        
        if success:
            logger.debug(f"Successfully upserted handler '{handler_name}' for user '{user_id}'")
            return new_state
        else:
            logger.error(f"Failed to upsert handler '{handler_name}' for user '{user_id}'")
            return None 