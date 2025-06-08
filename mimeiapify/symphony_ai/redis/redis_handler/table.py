from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel
import logging

from .utils.tenant_cache import TenantCache
from ..ops import hincrby_with_expire, hget
from .utils.serde import dumps, loads

logger = logging.getLogger("RedisTable")


class RedisTable(TenantCache):
    """
    Repository for table data management (generic DataFrames/rows).
    
    Extracted from RedisHandler SECTION: Table Data Management:
    - set_table_data() -> upsert()
    - get_table_data() -> get()
    - get_field() -> get_field()
    - increment_table_data_field() -> increment_field()
    - append_to_table_data_list_field() -> append_to_list()
    - table_data_exists() -> exists()
    - delete_table_data() -> delete()
    - create_or_update_table_field() -> update_field()
    - find_table_by_field() -> find_by_field()
    - delete_all_tables_by_pkid() -> delete_all_by_pkid()
    
    Single Responsibility: Table/DataFrame data management only
    """
    redis_alias: str = "handlers"
    
    def _key(self, table_name: str, pkid: str) -> str:
        """Build table key using KeyFactory"""
        return self.keys.table(self.tenant, table_name, pkid)

    # ---- Public API extracted from RedisHandler Table methods ---------------
    async def get(self, table_name: str, pkid: str, models: Optional[Dict[str, type[BaseModel]]] = None) -> Optional[Dict[str, Any]]:
        """
        Get full table row data (was get_table_data)
        
        Args:
            table_name: Name of the table
            pkid: Primary key identifier
            models: Optional mapping of field names to BaseModel classes for typed deserialization
                   e.g., {"metadata": RowMetadata, "config": RowConfig}
        """
        key = self._key(table_name, pkid)
        result = await self._get_hash(key, models=models)
        if not result:
            logger.debug(f"Table data not found for '{table_name}:{pkid}'")
        return result

    async def upsert(self, table_name: str, pkid: str, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set table row data (Redis HSET upsert behavior)"""
        key = self._key(table_name, pkid)
        return await self._hset_with_ttl(key, data, ttl)

    async def get_field(self, table_name: str, pkid: str, field: str) -> Optional[Any]:
        """Get a specific field from table row data"""
        key = self._key(table_name, pkid)
        raw_value = await hget(key, field, alias=self.redis_alias)
        return loads(raw_value) if raw_value is not None else None

    async def update_field(self, table_name: str, pkid: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Update single field in table row"""
        key = self._key(table_name, pkid)
        return await self._hset_with_ttl(key, {field: value}, ttl)

    async def increment_field(self, table_name: str, pkid: str, field: str, increment: int = 1, ttl: Optional[int] = None) -> Optional[int]:
        """Atomically increment integer field (was increment_table_data_field)"""
        key = self._key(table_name, pkid)
        
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
            logger.warning(f"Failed to increment table field '{field}' for '{table_name}:{pkid}'")
            return None

    async def append_to_list(self, table_name: str, pkid: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Append value to list field (was append_to_table_data_list_field)"""
        key = self._key(table_name, pkid)
        return await self._append_to_list_field(key, field, value, ttl)

    async def exists(self, table_name: str, pkid: str) -> bool:
        """Check if table row exists (was table_data_exists)"""
        key = self._key(table_name, pkid)
        return await self.key_exists(key)

    async def delete(self, table_name: str, pkid: str) -> int:
        """Delete table row (was delete_table_data)"""
        key = self._key(table_name, pkid)
        return await self.delete_key(key)

    async def find_by_field(self, table_name: str, field: str, value: Any, models: Optional[Dict[str, type[BaseModel]]] = None) -> Optional[Dict[str, Any]]:
        """
        Find first row in table where field matches value (was find_table_by_field)
        
        Args:
            table_name: Name of the table
            field: Field name to search
            value: Value to match
            models: Optional mapping of field names to BaseModel classes for typed deserialization
        """
        pattern = self.keys.table(self.tenant, table_name, "*")
        return await self._find_by_field(pattern, field, value, models=models)

    async def delete_all_by_pkid(self, pkid: str) -> int:
        """
        Delete all table rows across all tables with same pkid (was delete_all_tables_by_pkid)
        
        This creates a pattern that matches any table with the given pkid:
        tenant:df:*:pkid:safe_pkid
        """
        safe_pkid = pkid.replace(":", "_")
        pattern = f"{self.tenant}:{self.keys.table_prefix}:*:{self.keys.pk_marker}:{safe_pkid}"
        
        logger.info(f"Deleting all table data with pkid '{pkid}' (pattern: '{pattern}')")
        return await self._delete_by_pattern(pattern) 