from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel
import logging

from .utils.tenant_cache import TenantCache
from ..ops import get, set
from .utils.serde import dumps, loads

logger = logging.getLogger("RedisGeneric")


class RedisGeneric(TenantCache):
    """
    Repository for generic operations.
    
    Extracted from RedisHandler SECTION: Generic Operations:
    - get_generic() -> get()
    - set_generic() -> set()
    - delete_generic() -> delete()
    - key_exists() -> exists() [inherited from TenantCache]
    - renew_ttl_generic() -> renew_ttl() [inherited from TenantCache]
    - get_ttl_generic() -> get_ttl() [inherited from TenantCache]
    
    Single Responsibility: Generic key-value operations with tenant context
    Note: Prefer specific repositories (RedisUser, HandlerRepo, etc.) over this generic one
    """
    redis_alias: str = "default"
    
    def _key(self, key_base: str) -> str:
        """Build tenant-scoped key"""
        return f"{self.tenant}:{key_base}"

    # ---- Public API extracted from RedisHandler Generic methods -------------
    async def get(self, key_base: str, model: Optional[type[BaseModel]] = None) -> Optional[Any]:
        """
        Generic get with deserialization (was get_generic)
        
        Args:
            key_base: Base key name (tenant will be prefixed)
            model: Optional BaseModel class for typed deserialization
        """
        full_key = self._key(key_base)
        # Note: Using direct ops.get() as this is simple key-value, not hash operations
        raw_value = await get(full_key, alias=self.redis_alias)
        return loads(raw_value, model=model)

    async def set(self, key_base: str, value: Any, ex: Optional[int] = None) -> bool:
        """Generic set with serialization (Redis SET operation - replaces entire value)"""
        full_key = self._key(key_base)
        serialized_value = dumps(value)
        # Note: Using direct ops.set() as this is simple key-value, not hash operations
        return await set(full_key, serialized_value, ex=ex, alias=self.redis_alias)

    async def delete(self, key_base: str) -> int:
        """Generic delete (was delete_generic)"""
        full_key = self._key(key_base)
        return await self.delete_key(full_key)

    # Note: key_exists, renew_ttl, get_ttl are inherited from TenantCache
    # and work with full keys, so users can call:
    # repo.key_exists(repo._key("my_key"))
    # repo.renew_ttl(repo._key("my_key"), 3600)
    # repo.get_ttl(repo._key("my_key")) 