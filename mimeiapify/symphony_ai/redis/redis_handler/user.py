from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import logging

from .utils.tenant_cache import TenantCache
from ..ops import hincrby_with_expire, hdel, hget
from .utils.serde import dumps, loads

logger = logging.getLogger("RedisUser")


class RedisUser(TenantCache):
    """
    Repository for user-specific operations.
    
    Extracted from RedisHandler SECTION: User-specific Methods:
    - get_user_data() -> get()
    - get_field() -> get_field()
    - update_user_field() -> update_field()  
    - increment_user_field() -> increment_field()
    - append_to_user_list_field() -> append_to_list()
    - create_user_record() -> upsert()
    - find_user_by_field() -> find_by_field()
    - delete_user_record() -> delete()
    - delete_user_hash_field() -> delete_field()
    - user_exists() -> exists()
    
    Single Responsibility: User data management only
    
    Example usage:
        user = RedisUser(tenant="mimeia", user_id="user123")
        await user.upsert({"name": "Alice", "score": 100})
        data = await user.get()
        name = await user.get_field("name")
    """
    user_id: str = Field(..., min_length=1)
    redis_alias: str = "user"
    
    def _key(self) -> str:
        """Build user key using KeyFactory"""
        return self.keys.user(self.tenant, self.user_id)

    # ---- Public API extracted from RedisHandler User methods ----------------
    async def get(self, models: Optional[Dict[str, type[BaseModel]]] = None) -> Optional[Dict[str, Any]]:
        """
        Get full user data hash (was get_user_data)
        
        Args:
            models: Optional mapping of field names to BaseModel classes for typed deserialization
                   e.g., {"profile": UserProfile, "preferences": UserPreferences}
        """
        key = self._key()
        result = await self._get_hash(key, models=models)
        if not result:
            logger.debug(f"User data not found for user_id '{self.user_id}' (key: '{key}')")
        return result

    async def upsert(self, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Create or update user record with multiple fields (Redis HSET upsert behavior)"""
        key = self._key()
        return await self._hset_with_ttl(key, data, ttl)

    async def update_field(self, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Update single field in user hash"""
        key = self._key()
        return await self._hset_with_ttl(key, {field: value}, ttl)

    async def increment_field(self, field: str, increment: int = 1, ttl: Optional[int] = None) -> Optional[int]:
        """Atomically increment integer field (was increment_user_field)"""
        key = self._key()
        
        new_value, expire_res = await hincrby_with_expire(
            key=key,
            field=field, 
            increment=increment,
            ttl=ttl or self.ttl_default,
            alias=self.redis_alias
        )
        
        if new_value is not None and expire_res:
            return new_value
        else:
            logger.warning(f"Failed to increment user field '{field}' for user_id '{self.user_id}'")
            return None

    async def append_to_list(self, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Append value to list field (was append_to_user_list_field)"""
        key = self._key()
        return await self._append_to_list_field(key, field, value, ttl)

    async def find_by_field(self, field: str, value: Any, models: Optional[Dict[str, type[BaseModel]]] = None) -> Optional[Dict[str, Any]]:
        """
        Find first user where field matches value (was find_user_by_field)
        
        Args:
            field: Field name to search
            value: Value to match
            models: Optional mapping of field names to BaseModel classes for typed deserialization
        """
        pattern = self.keys.user(self.tenant, "*")
        return await self._find_by_field(pattern, field, value, models=models)

    async def delete(self) -> int:
        """Delete entire user record (was delete_user_record)"""
        key = self._key()
        return await self.delete_key(key)

    async def delete_field(self, field: str) -> int:
        """Delete specific field from user hash (was delete_user_hash_field)"""
        key = self._key()
        return await hdel(key, field, alias=self.redis_alias)

    async def exists(self) -> bool:
        """Check if user exists (was user_exists)"""
        key = self._key()
        return await self.key_exists(key)

    async def get_field(self, field: str) -> Optional[Any]:
        """Get a specific field from the user's data"""
        key = self._key()
        raw_value = await hget(key, field, alias=self.redis_alias)
        return loads(raw_value) if raw_value is not None else None 