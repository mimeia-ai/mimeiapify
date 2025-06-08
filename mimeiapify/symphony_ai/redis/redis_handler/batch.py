from __future__ import annotations
from typing import Any, List, Set
import logging

from .utils.tenant_cache import TenantCache
from .utils.key_factory import KeyFactory
from ..ops import rpush_and_sadd, lrange, ltrim, llen, smembers, srem
from .utils.serde import dumps, loads

logger = logging.getLogger("RedisBatch")


class RedisBatch(TenantCache):
    """
    Repository for batch processing operations.
    
    Extracted from RedisHandler SECTION: Batch Processing Methods:
    - enqueue_batch_item() -> enqueue()
    - get_batch_list_chunk() -> get_chunk()
    - trim_batch_list() -> trim()
    - get_batch_list_length() -> get_length()
    - get_pending_tenants() -> get_pending_tenants() [class method]
    - remove_tenant_from_pending() -> remove_from_pending() [class method]
    
    Single Responsibility: Batch queue management and tenant tracking
    """
    redis_alias: str = "handlers"
    
    def _list_key(self, service: str, entity_key: str, action: str) -> str:
        """Build batch list key using KeyFactory"""
        return self.keys.batch_list(self.tenant, service, entity_key, action)

    @classmethod
    def _pending_set_key(cls, service: str) -> str:
        """Build global pending set key using KeyFactory"""
        return cls.keys.pending_set(cls, service)

    # ---- Public API extracted from RedisHandler Batch methods ---------------
    async def enqueue(self, service: str, entity_key: str, action: str, data: Any) -> bool:
        """
        Enqueue item for batch processing (was enqueue_batch_item)
        
        Atomically adds data to tenant-specific list and adds tenant to global pending set.
        """
        list_key = self._list_key(service, entity_key, action)
        global_set_key = self.keys.pending_set(service)
        
        serialized_data = dumps(data)
        tenant_member = self.tenant
        
        logger.debug(f"Enqueuing batch item: List='{list_key}', Set='{global_set_key}', Member='{tenant_member}'")
        
        rpush_res, sadd_res = await rpush_and_sadd(
            list_key=list_key,
            list_values=[serialized_data],
            set_key=global_set_key,
            set_members=[tenant_member],
            alias=self.redis_alias
        )
        
        if rpush_res is None or sadd_res is None:
            logger.error(f"Failed atomic enqueue for service '{service}'. RPUSH: {rpush_res}, SADD: {sadd_res}")
            return False
        
        logger.info(f"Batch item enqueued for service '{service}'. List length: {rpush_res}, Added to set: {sadd_res > 0}")
        return True

    async def get_chunk(self, service: str, entity_key: str, action: str, start: int = 0, end: int = -1) -> List[Any]:
        """Get range of items from batch list, deserialized (was get_batch_list_chunk)"""
        list_key = self._list_key(service, entity_key, action)
        logger.debug(f"Getting batch chunk ({start}-{end}) from '{list_key}'")
        
        raw_items = await lrange(list_key, start, end, alias=self.redis_alias)
        if not raw_items:
            return []
        
        # Deserialize each item
        deserialized_items = []
        for i, item_str in enumerate(raw_items):
            try:
                deserialized_items.append(loads(item_str))
            except Exception as e:
                logger.error(f"Failed to deserialize item index {start+i} from list '{list_key}': {e}. Raw: '{item_str[:100]}...'")
                deserialized_items.append(None)  # Add None for robustness
        
        return deserialized_items

    async def trim(self, service: str, entity_key: str, action: str, start: int, end: int) -> bool:
        """Trim batch list to specified range (was trim_batch_list)"""
        list_key = self._list_key(service, entity_key, action)
        logger.debug(f"Trimming batch list '{list_key}' to keep range ({start}-{end})")
        return await ltrim(list_key, start, end, alias=self.redis_alias)

    async def get_length(self, service: str, entity_key: str, action: str) -> int:
        """Get current length of batch list (was get_batch_list_length)"""
        list_key = self._list_key(service, entity_key, action)
        return await llen(list_key, alias=self.redis_alias)

    # ---- Global operations (work across all tenants) ------------------------
    @classmethod
    async def get_pending_tenants(cls, service: str) -> Set[str]:
        """
        Get set of tenant prefixes with pending batches (was get_pending_tenants)
        
        This is a class method because it operates on global keys, not tenant-specific ones.
        """
        key_factory = KeyFactory()
        global_set_key = key_factory.pending_set(service)
        logger.debug(f"[Global] Getting pending tenants from set '{global_set_key}'")
        return await smembers(global_set_key, alias="handlers")

    @classmethod
    async def remove_from_pending(cls, service: str, tenant_prefix: str) -> int:
        """
        Remove tenant from global pending set (was remove_tenant_from_pending)
        
        This is a class method because it operates on global keys, not tenant-specific ones.
        """
        key_factory = KeyFactory()
        global_set_key = key_factory.pending_set(service)
        logger.debug(f"[Global] Removing tenant '{tenant_prefix}' from pending set '{global_set_key}'")
        return await srem(global_set_key, tenant_prefix, alias="handlers") 