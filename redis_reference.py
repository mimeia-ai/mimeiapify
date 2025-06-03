# redis_handler.py (Rewritten - Final Version)

from typing import Any, Optional, Dict, List, Union, Set, Tuple
from enum import Enum
from datetime import datetime
import json
import logging

# Use relative imports within the library
# ONLY RedisCoreMethods is imported for Redis operations
from .redis_core_methods import RedisCoreMethods

logger = logging.getLogger("RedisHandler") # Use standard logging practice

# Define constants for commonly used key prefixes/formats
USER_KEY_PREFIX = "waid"
TABLE_KEY_PREFIX = "DF"
TABLE_PKID_MARKER = "pkid"
EXP_TRIGGER_PREFIX = "EXPTRIGGER"
BATCH_LIST_PREFIX = "batch"
GLOBAL_PENDING_BATCHES_PREFIX = "pending_batches"


class RedisHandler:
    """
    Handles interactions with Redis, managing tenant context, key construction,
    data serialization/deserialization, and providing high-level business logic methods.

    All instance methods automatically operate within the context of the tenant_prefix
    by calling methods in RedisCoreMethods.
    Class methods operate on global keys where appropriate (e.g., batch sets).
    This class does NOT interact directly with the RedisClient.
    """
    DEFAULT_TTL = 86400  # 24 hours in seconds

    def __init__(self, tenant_prefix: str, default_ttl: Optional[int] = None,
                 handler_ttl: Optional[int] = None, template_ttl: Optional[int] = None, table_ttl: Optional[int] = None):
        """
        Initialize the RedisHandler with the tenant prefix and optional TTL settings.

        Args:
            tenant_prefix: The prefix to use for tenant-specific Redis keys.
            default_ttl: Optional override for the default TTL (used for users).
            handler_ttl: Optional override for handler state TTL.
            template_ttl: Optional override for template TTL (currently unused but kept for potential future).
            table_ttl: Optional override for table data TTL.
        """
        if not tenant_prefix:
            raise ValueError("tenant_prefix cannot be empty")

        self.tenant_prefix = tenant_prefix
        # Use provided TTLs or fall back to the class default
        self.user_ttl = default_ttl if default_ttl is not None else self.DEFAULT_TTL
        self.handler_ttl = handler_ttl if handler_ttl is not None else self.DEFAULT_TTL
        self.template_ttl = template_ttl if template_ttl is not None else self.DEFAULT_TTL # Keep for compatibility
        self.table_ttl = table_ttl if table_ttl is not None else self.DEFAULT_TTL

        logger.debug(f"RedisHandler initialized for tenant_prefix: '{self.tenant_prefix}'")

    # =========================================================================
    # SECTION: Internal Key Building Helpers
    # =========================================================================

    def _build_tenant_key(self, base_key: str) -> str:
        """Constructs the final Redis key with the instance's tenant prefix."""
        return f"{self.tenant_prefix}:{base_key}"

    def _build_batch_list_key(self, service: str, entity_key: str, action: str) -> str:
        """Builds the tenant-specific key for a batch processing list."""
        base_key = f"{BATCH_LIST_PREFIX}:{service}:{entity_key}:{action}"
        return self._build_tenant_key(base_key)

    @classmethod
    def _build_global_pending_set_key(cls, service: str) -> str:
        """Builds the global key for the set tracking tenants with pending batches."""
        # No tenant prefix for global keys
        return f"{GLOBAL_PENDING_BATCHES_PREFIX}:{service}"

    # =========================================================================
    # SECTION: Internal Serialization/Deserialization Helpers
    # =========================================================================

    def _serialize_value(self, value: Any) -> str:
        """Serializes a Python value into a string suitable for Redis storage."""
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return str(int(value)) # "1" or "0"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            return value
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, Enum):
            return str(value.value)
        else:
            try:
                # ensure_ascii=False prevents converting non-ASCII chars to \u sequences
                return json.dumps(value, ensure_ascii=False)
            except TypeError as e:
                logger.warning(f"Could not JSON serialize value of type {type(value)}. Falling back to str(). Error: {e}. Value: {value!r}")
                return str(value)

    def _deserialize_value(self, value_str: Optional[str]) -> Any:
        """Deserializes a string value retrieved from Redis back into a Python object."""
        if value_str is None:
            return None
        if value_str == "null":
            return None
        if value_str == "1":
            return True
        if value_str == "0":
            return False
        try:
            # Attempt JSON decoding first for lists, dicts, etc.
            return json.loads(value_str)
        except (json.JSONDecodeError, TypeError):
            # If not JSON, return the original string
            return value_str

    def _serialize_hash_dict(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Serializes all values in a dictionary for storing in a Redis hash."""
        return {field: self._serialize_value(value) for field, value in data.items()}

    def _deserialize_hash_dict(self, raw_data: Dict[str, str]) -> Dict[str, Any]:
        """Deserializes all values in a dictionary retrieved from a Redis hash."""
        if not raw_data:
            return {}
        return {field: self._deserialize_value(value_str) for field, value_str in raw_data.items()}

    # =========================================================================
    # SECTION: Internal Generic Helpers
    # =========================================================================

    async def _find_hash_by_field_internal(self, pattern_base: str, field: str, value_to_match: Any) -> Optional[Dict[str, Any]]:
        """
        Internal helper to find the first hash matching a key pattern and exact field value,
        using only RedisCoreMethods.
        """
        full_pattern = self._build_tenant_key(pattern_base)
        compare_value_str = self._serialize_value(value_to_match) # Serialize target value once

        logger.debug(f"Searching hash pattern '{full_pattern}' where field '{field}' == '{compare_value_str}'")

        cursor = '0' # Initial cursor for scan
        try:
            while True:
                # Use RedisCoreMethods.scan_keys
                next_cursor, keys_batch = await RedisCoreMethods.scan_keys(match_pattern=full_pattern, cursor=cursor, count=100)

                for full_key in keys_batch:
                    # Use RedisCoreMethods.hget to get the raw string value
                    current_value_str = await RedisCoreMethods.hget(full_key, field)

                    # Compare raw string from Redis with our serialized target
                    if current_value_str is not None and current_value_str == compare_value_str:
                        logger.info(f"Match found for field '{field}' value in key '{full_key}'")
                        # Match found: get the full hash data (raw string dictionary)
                        raw_hash_data = await RedisCoreMethods.hgetall(full_key)
                        # Deserialize the entire hash and return it
                        return self._deserialize_hash_dict(raw_hash_data)

                # Check if SCAN is complete
                if next_cursor == '0':
                    logger.debug(f"SCAN finished for pattern '{full_pattern}'. No match found for field '{field}'.")
                    return None # No match found

                cursor = next_cursor # Continue scan

        except Exception as e:
            logger.error(f"Error during _find_hash_by_field_internal (pattern='{full_pattern}', field='{field}'): {e}", exc_info=True)
            return None

    async def _delete_keys_by_pattern_internal(self, pattern_base: str) -> int:
        """Internal helper to find and delete keys matching a pattern using SCAN and DELETE via RedisCoreMethods."""
        full_pattern = self._build_tenant_key(pattern_base)
        total_deleted_count = 0
        cursor = '0'
        batch_size = 100 # How many keys to fetch/delete at once

        logger.debug(f"Deleting keys matching pattern '{full_pattern}' using SCAN/DELETE")
        try:
            while True:
                next_cursor, keys_batch = await RedisCoreMethods.scan_keys(match_pattern=full_pattern, cursor=cursor, count=batch_size)

                if keys_batch:
                    logger.debug(f"Deleting batch of {len(keys_batch)} keys starting with '{keys_batch[0]}...'")
                    # Call RedisCoreMethods.delete with unpacked list of keys
                    deleted_in_batch = await RedisCoreMethods.delete(*keys_batch)
                    if deleted_in_batch >= 0: # delete returns number deleted or 0 on error
                        total_deleted_count += deleted_in_batch
                    else:
                         # Should not happen based on current RedisCoreMethods.delete impl, but good to check
                         logger.warning(f"RedisCoreMethods.delete returned unexpected negative value for batch starting with {keys_batch[0]}...")

                if next_cursor == '0': # SCAN complete
                    break
                cursor = next_cursor

            logger.info(f"Completed deletion for pattern '{full_pattern}'. Total keys deleted: {total_deleted_count}.")

        except Exception as e:
            logger.error(f"Error during SCAN/DELETE for pattern '{full_pattern}': {e}", exc_info=True)
            # Return count deleted so far

        return total_deleted_count

    async def _append_to_list_in_hash_field(self, key_base: str, field: str, value_to_append: Any, ttl: int) -> bool:
        """
        Internal helper to append a value to a field treated as a JSON list within a hash.
        Uses RedisCoreMethods.hget and RedisCoreMethods.hset_with_expire.
        Note: Not fully atomic between read and write due to Python logic.
        """
        full_key = self._build_tenant_key(key_base)
        try:
            # 1. Read current value using RedisCoreMethods.hget
            current_data_raw = await RedisCoreMethods.hget(full_key, field)

            # 2. Deserialize or initialize list (Python logic)
            current_list = []
            if current_data_raw is not None:
                try:
                    deserialized_value = self._deserialize_value(current_data_raw)
                    if isinstance(deserialized_value, list):
                        current_list = deserialized_value
                    else:
                        logger.warning(f"Field '{field}' in key '{full_key}' is not a list (type: {type(deserialized_value)}). Overwriting.")
                        current_list = []
                except Exception as e:
                    logger.warning(f"Could not deserialize list field '{field}' in key '{full_key}', assuming override. Error: {e}")
                    current_list = []

            # 3. Append new Python value (Python logic)
            current_list.append(value_to_append)

            # 4. Serialize updated list (Python logic)
            serialized_list = self._serialize_value(current_list)

            # 5. Write back using RedisCoreMethods.hset_with_expire for atomic set+expire
            hset_res, expire_res = await RedisCoreMethods.hset_with_expire(
                key=full_key,
                mapping={field: serialized_list},
                ttl=ttl
            )

            success = hset_res is not None and expire_res
            if not success:
                 logger.warning(f"Core method hset_with_expire failed during list append for field '{field}' in key '{full_key}'. HSET: {hset_res}, EXPIRE: {expire_res}")
            return success

        except Exception as e:
            # Catch errors from hget or serialization/deserialization
            logger.error(f"Error in _append_to_list_in_hash_field for '{field}' in '{full_key}': {e}", exc_info=True)
            return False

    # =========================================================================
    # SECTION: User-specific Methods
    # =========================================================================

    async def get_user_data(self, waid: str) -> Optional[Dict[str, Any]]:
        """Retrieves the full user data hash, deserialized."""
        key_base = f"{USER_KEY_PREFIX}:{waid}"
        full_key = self._build_tenant_key(key_base)
        # Use RedisCoreMethods.hgetall
        raw_data = await RedisCoreMethods.hgetall(full_key)
        if not raw_data:
            logger.debug(f"User data not found for waid '{waid}' (key: '{full_key}')")
            return None
        # Deserialize the result
        return self._deserialize_hash_dict(raw_data)

    async def update_user_field(self, waid: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Updates a single field in the user hash and renews TTL atomically using RedisCoreMethods."""
        key_base = f"{USER_KEY_PREFIX}:{waid}"
        full_key = self._build_tenant_key(key_base)
        ttl_to_use = ttl if ttl is not None else self.user_ttl
        # Serialize the value
        serialized_value = self._serialize_value(value)

        # Use RedisCoreMethods.hset_with_expire
        hset_res, expire_res = await RedisCoreMethods.hset_with_expire(
            key=full_key,
            mapping={field: serialized_value},
            ttl=ttl_to_use
        )
        success = hset_res is not None and expire_res
        if not success:
             logger.warning(f"Failed to update user field '{field}' for waid '{waid}'. HSET: {hset_res}, EXPIRE: {expire_res}")
        return success

    async def increment_user_field(self, waid: str, field: str, increment: int = 1, ttl: Optional[int] = None) -> Optional[int]:
        """Atomically increments an integer field in the user hash and renews TTL using RedisCoreMethods."""
        key_base = f"{USER_KEY_PREFIX}:{waid}"
        full_key = self._build_tenant_key(key_base)
        ttl_to_use = ttl if ttl is not None else self.user_ttl

        # Use RedisCoreMethods.hincrby_with_expire
        new_value, expire_res = await RedisCoreMethods.hincrby_with_expire(
            key=full_key,
            field=field,
            increment=increment,
            ttl=ttl_to_use
        )

        if new_value is not None and expire_res:
            return new_value
        else:
            logger.warning(f"Failed to increment user field '{field}' for waid '{waid}'. Value: {new_value}, Expire OK: {expire_res}")
            return None

    async def append_to_user_list_field(self, waid: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Appends a value to a field treated as a JSON list within the user hash."""
        key_base = f"{USER_KEY_PREFIX}:{waid}"
        ttl_to_use = ttl if ttl is not None else self.user_ttl
        # Calls the internal helper which uses hget and hset_with_expire
        return await self._append_to_list_in_hash_field(key_base, field, value, ttl_to_use)

    async def create_user_record(self, waid: str, user_data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Creates or overwrites a user hash with the provided data and sets TTL atomically using RedisCoreMethods."""
        key_base = f"{USER_KEY_PREFIX}:{waid}"
        full_key = self._build_tenant_key(key_base)
        ttl_to_use = ttl if ttl is not None else self.user_ttl
        # Serialize the entire hash data
        serialized_data = self._serialize_hash_dict(user_data)

        if not serialized_data:
            logger.warning(f"Creating user '{waid}' with empty data. Deleting key '{full_key}'.")
            # Delete the key to represent an empty state
            delete_count = await RedisCoreMethods.delete(full_key)
            return delete_count >= 0 # delete returns num deleted (0 or 1) or 0 on error

        # Use RedisCoreMethods.hset_with_expire
        hset_res, expire_res = await RedisCoreMethods.hset_with_expire(
            key=full_key,
            mapping=serialized_data,
            ttl=ttl_to_use
        )
        success = hset_res is not None and expire_res
        if not success:
             logger.warning(f"Failed to create user record for waid '{waid}'. HSET: {hset_res}, EXPIRE: {expire_res}")
        return success

    async def find_user_by_field(self, field: str, value: Any) -> Optional[Dict[str, Any]]:
        """Finds the first user hash where a specific field matches the given value."""
        pattern_base = f"{USER_KEY_PREFIX}:*"
        # Calls internal helper which uses scan_keys, hget, hgetall
        return await self._find_hash_by_field_internal(pattern_base, field, value)

    async def delete_user_record(self, waid: str) -> int:
        """Deletes the entire user hash using RedisCoreMethods."""
        key_base = f"{USER_KEY_PREFIX}:{waid}"
        full_key = self._build_tenant_key(key_base)
        # Use RedisCoreMethods.delete
        return await RedisCoreMethods.delete(full_key)

    async def delete_user_hash_field(self, waid: str, field: str) -> int:
        """Deletes a specific field from the user hash using RedisCoreMethods."""
        key_base = f"{USER_KEY_PREFIX}:{waid}"
        full_key = self._build_tenant_key(key_base)
        # Use RedisCoreMethods.hdel
        return await RedisCoreMethods.hdel(full_key, field)

    async def user_exists(self, waid: str) -> bool:
        """Checks if a user record (key) exists using RedisCoreMethods."""
        key_base = f"{USER_KEY_PREFIX}:{waid}"
        full_key = self._build_tenant_key(key_base)
        # Use RedisCoreMethods.exists
        return await RedisCoreMethods.exists(full_key) > 0

    # =========================================================================
    # SECTION: Handler State Management
    # =========================================================================

    async def set_handler_state(self, handler_name: str, user_id: str, state_data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Sets the state for a specific handler and user, overwriting existing data atomically using RedisCoreMethods."""
        key_base = f"{handler_name}:{user_id}"
        full_key = self._build_tenant_key(key_base)
        ttl_to_use = ttl if ttl is not None else self.handler_ttl
        serialized_data = self._serialize_hash_dict(state_data)

        if not serialized_data:
            logger.warning(f"Setting handler state '{key_base}' with empty data. Deleting key '{full_key}'.")
            delete_count = await RedisCoreMethods.delete(full_key)
            return delete_count >= 0

        hset_res, expire_res = await RedisCoreMethods.hset_with_expire(
            key=full_key,
            mapping=serialized_data,
            ttl=ttl_to_use
        )
        success = hset_res is not None and expire_res
        if not success:
             logger.warning(f"Failed to set handler state '{key_base}'. HSET: {hset_res}, EXPIRE: {expire_res}")
        return success

    async def get_handler_state(self, handler_name: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the full handler state hash, deserialized."""
        key_base = f"{handler_name}:{user_id}"
        full_key = self._build_tenant_key(key_base)
        raw_data = await RedisCoreMethods.hgetall(full_key)
        if not raw_data:
            logger.debug(f"Handler state not found for '{key_base}'")
            return None
        return self._deserialize_hash_dict(raw_data)
    
    async def get_handler_state_field(self, handler_name: str, user_id: str, field: str) -> Optional[Any]:
        """Retrieves a specific field from the handler state hash."""
        key_base = f"{handler_name}:{user_id}"
        full_key = self._build_tenant_key(key_base)
        return await RedisCoreMethods.hget(full_key, field)
    
    async def update_handler_state_field(self, handler_name: str, user_id: str, field: str, value: Any) -> bool:
        """Updates a single field in the handler state hash"""
        key_base = f"{handler_name}:{user_id}"
        full_key = self._build_tenant_key(key_base)
        return await RedisCoreMethods.hset(full_key, field, value)

    async def increment_handler_state_field(self, handler_name: str, user_id: str, field: str, increment: int = 1, ttl: Optional[int] = None) -> Optional[int]:
        """Atomically increments an integer field in the handler state hash and renews TTL using RedisCoreMethods."""
        key_base = f"{handler_name}:{user_id}"
        full_key = self._build_tenant_key(key_base)
        ttl_to_use = ttl if ttl is not None else self.handler_ttl

        new_value, expire_res = await RedisCoreMethods.hincrby_with_expire(
            key=full_key,
            field=field,
            increment=increment,
            ttl=ttl_to_use
        )

        if new_value is not None and expire_res:
            return new_value
        else:
            logger.warning(f"Failed to increment handler field '{field}' for '{key_base}'. Value: {new_value}, Expire OK: {expire_res}")
            return None

    async def append_to_handler_state_list_field(self, handler_name: str, user_id: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Appends a value to a field treated as a JSON list within the handler state hash."""
        key_base = f"{handler_name}:{user_id}"
        ttl_to_use = ttl if ttl is not None else self.handler_ttl
        return await self._append_to_list_in_hash_field(key_base, field, value, ttl_to_use)

    async def handler_exists(self, handler_name: str, user_id: str) -> bool:
        """Checks if a handler state key exists using RedisCoreMethods."""
        key_base = f"{handler_name}:{user_id}"
        full_key = self._build_tenant_key(key_base)
        return await RedisCoreMethods.exists(full_key) > 0

    async def delete_handler_state(self, handler_name: str, user_id: str) -> int:
        """Deletes the handler state hash using RedisCoreMethods."""
        key_base = f"{handler_name}:{user_id}"
        full_key = self._build_tenant_key(key_base)
        return await RedisCoreMethods.delete(full_key)

    async def create_or_update_handler(self, handler_name: str, user_id: str, state_data: Dict[str, Any], ttl: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Gets existing state, merges with new data, and sets the updated state using RedisCoreMethods."""
        ttl_to_use = ttl if ttl is not None else self.handler_ttl
        logger.debug(f"Create/Update handler '{handler_name}' for user '{user_id}'")

        # Get existing state (uses hgetall via get_handler_state)
        existing_state = await self.get_handler_state(handler_name, user_id) or {}

        # Merge new data over existing (Python logic)
        new_state = {
            **existing_state,
            **state_data,
            "handler_type": handler_name,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Set the merged state (uses hset_with_expire via set_handler_state)
        success = await self.set_handler_state(handler_name, user_id, new_state, ttl_to_use)

        if success:
             logger.debug(f"Successfully set updated state for handler '{handler_name}' user '{user_id}'")
             return new_state # Return the final state
        else:
             logger.error(f"Failed to set state during create_or_update_handler for '{handler_name}' user '{user_id}'")
             return None # Indicate failure

    # =========================================================================
    # SECTION: Table Data Management (Generic DataFrames/Rows)
    # =========================================================================

    def _build_table_key_base(self, table_name: str, pkid: str) -> str:
        """Helper to build the base key part for table data."""
        # Ensure components are safe for key construction if necessary
        safe_table_name = table_name.replace(":", "_") # Basic safety
        safe_pkid = pkid.replace(":", "_")
        return f"{TABLE_KEY_PREFIX}:{safe_table_name}:{TABLE_PKID_MARKER}:{safe_pkid}"

    async def set_table_data(self, table_name: str, pkid: str, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Sets data for a specific row (identified by pkid) in a logical table atomically using RedisCoreMethods."""
        key_base = self._build_table_key_base(table_name, pkid)
        full_key = self._build_tenant_key(key_base)
        ttl_to_use = ttl if ttl is not None else self.table_ttl
        serialized_data = self._serialize_hash_dict(data)

        if not serialized_data:
            logger.warning(f"Setting table data '{key_base}' with empty data. Deleting key '{full_key}'.")
            delete_count = await RedisCoreMethods.delete(full_key)
            return delete_count >= 0

        hset_res, expire_res = await RedisCoreMethods.hset_with_expire(
            key=full_key,
            mapping=serialized_data,
            ttl=ttl_to_use
        )
        success = hset_res is not None and expire_res
        if not success:
             logger.warning(f"Failed to set table data '{key_base}'. HSET: {hset_res}, EXPIRE: {expire_res}")
        return success

    async def get_table_data(self, table_name: str, pkid: str) -> Optional[Dict[str, Any]]:
        """Retrieves the full data hash for a table row, deserialized."""
        key_base = self._build_table_key_base(table_name, pkid)
        full_key = self._build_tenant_key(key_base)
        raw_data = await RedisCoreMethods.hgetall(full_key)
        if not raw_data:
             logger.debug(f"Table data not found for '{key_base}'")
             return None
        return self._deserialize_hash_dict(raw_data)

    async def increment_table_data_field(self, table_name: str, pkid: str, field: str, increment: int = 1, ttl: Optional[int] = None) -> Optional[int]:
        """Atomically increments an integer field in a table row hash and renews TTL using RedisCoreMethods."""
        key_base = self._build_table_key_base(table_name, pkid)
        full_key = self._build_tenant_key(key_base)
        ttl_to_use = ttl if ttl is not None else self.table_ttl

        new_value, expire_res = await RedisCoreMethods.hincrby_with_expire(
            key=full_key,
            field=field,
            increment=increment,
            ttl=ttl_to_use
        )
        if new_value is not None and expire_res:
            return new_value
        else:
            logger.warning(f"Failed to increment table field '{field}' for '{key_base}'. Value: {new_value}, Expire OK: {expire_res}")
            return None

    async def append_to_table_data_list_field(self, table_name: str, pkid: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Appends a value to a field treated as a JSON list within a table row hash."""
        key_base = self._build_table_key_base(table_name, pkid)
        ttl_to_use = ttl if ttl is not None else self.table_ttl
        return await self._append_to_list_in_hash_field(key_base, field, value, ttl_to_use)

    async def table_data_exists(self, table_name: str, pkid: str) -> bool:
        """Checks if a table row key exists using RedisCoreMethods."""
        key_base = self._build_table_key_base(table_name, pkid)
        full_key = self._build_tenant_key(key_base)
        return await RedisCoreMethods.exists(full_key) > 0

    async def delete_table_data(self, table_name: str, pkid: str) -> int:
        """Deletes the table row hash using RedisCoreMethods."""
        key_base = self._build_table_key_base(table_name, pkid)
        full_key = self._build_tenant_key(key_base)
        return await RedisCoreMethods.delete(full_key)

    async def create_or_update_table_field(self, table_name: str, pkid: str, field: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Updates a single field in a table row hash and renews TTL atomically using RedisCoreMethods."""
        key_base = self._build_table_key_base(table_name, pkid)
        full_key = self._build_tenant_key(key_base)
        ttl_to_use = ttl if ttl is not None else self.table_ttl
        serialized_value = self._serialize_value(value)

        hset_res, expire_res = await RedisCoreMethods.hset_with_expire(
            key=full_key,
            mapping={field: serialized_value},
            ttl=ttl_to_use
        )
        success = hset_res is not None and expire_res
        if not success:
             logger.warning(f"Failed to update table field '{field}' for '{key_base}'. HSET: {hset_res}, EXPIRE: {expire_res}")
        return success

    async def find_table_by_field(self, table_name: str, field: str, value: Any) -> Optional[Dict[str, Any]]:
        """Finds the first row in a table where a specific field matches the given value."""
        pattern_base = f"{TABLE_KEY_PREFIX}:{table_name.replace(':', '_')}:{TABLE_PKID_MARKER}:*"
        return await self._find_hash_by_field_internal(pattern_base, field, value)

    async def delete_all_tables_by_pkid(self, pkid: str) -> int:
        """Deletes all table data rows across all tables that share the same pkid using RedisCoreMethods."""
        safe_pkid = pkid.replace(":", "_")
        table_pattern_base = f"{TABLE_KEY_PREFIX}:*:{TABLE_PKID_MARKER}:{safe_pkid}"
        logger.info(f"Deleting all table data with pkid '{pkid}' (using pattern base '{table_pattern_base}')")
        # Calls internal helper which uses scan_keys, delete
        return await self._delete_keys_by_pattern_internal(table_pattern_base)

    # =========================================================================
    # SECTION: Expiration Trigger Key Management
    # =========================================================================

    def _build_trigger_key_base(self, action: str, identifier: str) -> str:
        """Helper to build the base key part for expiration triggers."""
        safe_action = action.replace(":", "_")
        safe_identifier = identifier.replace(":", "_")
        return f"{EXP_TRIGGER_PREFIX}:{safe_action}:{safe_identifier}"

    async def set_action_trigger(self, action: str, identifier: str, ttl_seconds: int) -> bool:
        """Sets a dedicated key (with tenant prefix) to trigger an action upon expiration using RedisCoreMethods."""
        if ttl_seconds <= 0:
             logger.warning(f"Invalid TTL {ttl_seconds}s for action trigger {action}:{identifier}. Skipping set.")
             return False

        key_base = self._build_trigger_key_base(action, identifier)
        full_key = self._build_tenant_key(key_base)
        # Value can be simple, used mainly for the TTL via SETEX
        value = f"trigger:{datetime.utcnow().isoformat()}"
        serialized_value = self._serialize_value(value)

        logger.debug(f"Setting action trigger '{full_key}' with TTL {ttl_seconds}s")
        # Use RedisCoreMethods.setex
        return await RedisCoreMethods.setex(full_key, ttl_seconds, serialized_value)

    async def delete_action_trigger(self, action: str, identifier: str) -> int:
        """Deletes a specific action trigger key using RedisCoreMethods."""
        key_base = self._build_trigger_key_base(action, identifier)
        full_key = self._build_tenant_key(key_base)
        logger.debug(f"Deleting action trigger key '{full_key}'")
        return await RedisCoreMethods.delete(full_key)

    async def delete_all_triggers_by_identifier(self, identifier: str) -> int:
        """Deletes all expiration triggers for a specific identifier within the tenant using RedisCoreMethods."""
        safe_identifier = identifier.replace(":", "_")
        trigger_pattern_base = f"{EXP_TRIGGER_PREFIX}:*:{safe_identifier}"
        logger.info(f"Deleting all triggers for identifier '{identifier}' (using pattern base '{trigger_pattern_base}')")
        return await self._delete_keys_by_pattern_internal(trigger_pattern_base)

    # =========================================================================
    # SECTION: Batch Processing Methods
    # =========================================================================

    async def enqueue_batch_item(self, service: str, entity_key: str, action: str, data: Any) -> bool:
        """
        Enqueues an item for batch processing atomically using RedisCoreMethods.
        Adds data to a tenant-specific list and adds the tenant to a global pending set.
        """
        # 1. Build tenant list key and global set key
        list_key = self._build_batch_list_key(service, entity_key, action)
        global_set_key = self._build_global_pending_set_key(service)

        # 2. Serialize data for the list item
        serialized_data = self._serialize_value(data)
        # Tenant prefix is the member for the global set
        tenant_id_member = self.tenant_prefix

        logger.debug(f"Enqueuing batch item: List='{list_key}', Set='{global_set_key}', Member='{tenant_id_member}'")

        # 3. Call RedisCoreMethods.rpush_and_sadd for atomicity
        rpush_res, sadd_res = await RedisCoreMethods.rpush_and_sadd(
            list_key=list_key,
            list_values=[serialized_data], # Expects a sequence
            set_key=global_set_key,
            set_members=[tenant_id_member] # Expects a sequence
        )

        # Check results (both should be non-None on success)
        if rpush_res is None or sadd_res is None:
            logger.error(f"Failed atomic enqueue for service '{service}'. RPUSH: {rpush_res}, SADD: {sadd_res}")
            return False

        logger.info(f"Batch item enqueued for service '{service}'. List length: {rpush_res}, Added to set: {sadd_res > 0}")
        return True

    async def get_batch_list_chunk(self, service: str, entity_key: str, action: str, start: int = 0, end: int = -1) -> List[Any]:
        """Gets a range of items from a tenant's batch list, deserializing them using RedisCoreMethods."""
        list_key = self._build_batch_list_key(service, entity_key, action)
        logger.debug(f"Getting batch chunk ({start}-{end}) from '{list_key}'")

        # Use RedisCoreMethods.lrange to get raw strings
        raw_items = await RedisCoreMethods.lrange(list_key, start, end)
        if not raw_items:
            return []

        # Deserialize each item
        deserialized_items = []
        for i, item_str in enumerate(raw_items):
            try:
                deserialized_items.append(self._deserialize_value(item_str))
            except Exception as e:
                 logger.error(f"Failed deserialize item index {start+i} from list '{list_key}': {e}. Raw: '{item_str[:100]}...'")
                 # Decide how to handle errors: Add None, skip, or raise? Add None for robustness.
                 deserialized_items.append(None)
        return deserialized_items

    async def trim_batch_list(self, service: str, entity_key: str, action: str, start: int, end: int) -> bool:
        """Trims a tenant's batch list to the specified range using RedisCoreMethods."""
        list_key = self._build_batch_list_key(service, entity_key, action)
        logger.debug(f"Trimming batch list '{list_key}' to keep range ({start}-{end})")
        # Use RedisCoreMethods.ltrim
        return await RedisCoreMethods.ltrim(list_key, start, end)

    async def get_batch_list_length(self, service: str, entity_key: str, action: str) -> int:
        """Gets the current length of a tenant's batch list using RedisCoreMethods."""
        list_key = self._build_batch_list_key(service, entity_key, action)
        # Use RedisCoreMethods.llen
        return await RedisCoreMethods.llen(list_key)

    @classmethod
    async def get_pending_tenants(cls, service: str) -> Set[str]:
        """Gets the set of tenant prefixes that have pending batches for a service using RedisCoreMethods."""
        global_set_key = cls._build_global_pending_set_key(service)
        logger.debug(f"[Global] Getting pending tenants from set '{global_set_key}'")
        # Use RedisCoreMethods.smembers
        return await RedisCoreMethods.smembers(global_set_key)

    @classmethod
    async def remove_tenant_from_pending(cls, service: str, tenant_prefix: str) -> int:
        """Removes a specific tenant prefix from the global pending set for a service using RedisCoreMethods."""
        global_set_key = cls._build_global_pending_set_key(service)
        logger.debug(f"[Global] Removing tenant '{tenant_prefix}' from pending set '{global_set_key}'")
        # Use RedisCoreMethods.srem
        return await RedisCoreMethods.srem(global_set_key, tenant_prefix)

    # =========================================================================
    # SECTION: Generic Operations (Use specific methods preferably)
    # =========================================================================

    async def get_generic(self, key_base: str) -> Optional[Any]:
        """Generic get using RedisCoreMethods, attempts deserialization."""
        full_key = self._build_tenant_key(key_base)
        raw_value = await RedisCoreMethods.get(full_key)
        return self._deserialize_value(raw_value)

    async def set_generic(self, key_base: str, value: Any, ex: Optional[int] = None) -> bool:
        """Generic set using RedisCoreMethods, serializes value."""
        full_key = self._build_tenant_key(key_base)
        serialized_value = self._serialize_value(value)
        # Uses RedisCoreMethods.set (which handles optional expiration)
        return await RedisCoreMethods.set(full_key, serialized_value, ex=ex)

    async def delete_generic(self, key_base: str) -> int:
        """Generic delete using RedisCoreMethods."""
        full_key = self._build_tenant_key(key_base)
        return await RedisCoreMethods.delete(full_key)

    async def key_exists(self, key_base: str) -> bool:
        """Generic key existence check using RedisCoreMethods."""
        full_key = self._build_tenant_key(key_base)
        return await RedisCoreMethods.exists(full_key) > 0

    async def renew_ttl_generic(self, key_base: str, ttl: int) -> bool:
        """Generic TTL renewal using RedisCoreMethods."""
        full_key = self._build_tenant_key(key_base)
        # Use RedisCoreMethods.expire
        return await RedisCoreMethods.expire(full_key, ttl)

    async def get_ttl_generic(self, key_base: str) -> int:
        """Generic get TTL using RedisCoreMethods."""
        full_key = self._build_tenant_key(key_base)
        # Use RedisCoreMethods.get_ttl
        return await RedisCoreMethods.get_ttl(full_key)