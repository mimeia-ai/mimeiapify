"""
Example expiration handlers for the Redis key-expiry trigger system.

This file shows how to register handlers for different types of TTL-driven workflows.
"""

import logging
from mimeiapify.symphony_ai.redis.listeners import expiration_registry

logger = logging.getLogger("Redis Expirty Trigger Examples")


@expiration_registry.on_expire_action("process_message_batch")
async def _process_batched_messages(waid: str, expired_key: str):
    """
    Triggered when key
        <tenant>:EXPTRIGGER:process_message_batch:<waid>
    expires.
    
    This handler processes accumulated messages for a WhatsApp ID
    after a batch timeout period.
    """
    tenant = expired_key.split(":", 1)[0]
    logger.info("[%s] Processing batched messages for WhatsApp ID: %s", tenant, waid)
    
    # Example processing logic:
    # 1. Retrieve batched messages from Redis
    # 2. Send consolidated message or perform batch operation
    # 3. Clean up temporary data
    
    # Your implementation here...
    logger.debug("Batch processing completed for %s", waid)


@expiration_registry.on_expire_action("cleanup_temp_session")
async def _cleanup_temporary_session(session_id: str, expired_key: str):
    """
    Triggered when key
        <tenant>:EXPTRIGGER:cleanup_temp_session:<session_id>
    expires.
    
    This handler cleans up temporary session data after expiry.
    """
    tenant = expired_key.split(":", 1)[0]
    logger.info("[%s] Cleaning up temporary session: %s", tenant, session_id)
    
    # Example cleanup logic:
    # 1. Remove temporary files
    # 2. Clear cache entries
    # 3. Update session status
    
    # Your implementation here...
    logger.debug("Session cleanup completed for %s", session_id)


@expiration_registry.on_expire_action("send_reminder")
async def _send_reminder_notification(user_id: str, expired_key: str):
    """
    Triggered when key
        <tenant>:EXPTRIGGER:send_reminder:<user_id>
    expires.
    
    This handler sends a reminder notification to a user after a delay.
    """
    tenant = expired_key.split(":", 1)[0]
    logger.info("[%s] Sending reminder notification to user: %s", tenant, user_id)
    
    # Example reminder logic:
    # 1. Check if reminder is still needed
    # 2. Send notification via email/SMS/push
    # 3. Update reminder status
    
    # Your implementation here...
    logger.debug("Reminder sent to user %s", user_id)


@expiration_registry.on_expire_action("expire_cache_entry")
async def _expire_cache_entry(cache_key: str, expired_key: str):
    """
    Triggered when key
        <tenant>:EXPTRIGGER:expire_cache_entry:<cache_key>
    expires.
    
    This handler performs additional cleanup when cache entries expire.
    """
    tenant = expired_key.split(":", 1)[0]
    logger.info("[%s] Cache entry expired: %s", tenant, cache_key)
    
    # Example cache cleanup logic:
    # 1. Invalidate related cache entries
    # 2. Update cache statistics
    # 3. Trigger cache refresh if needed
    
    # Your implementation here...
    logger.debug("Cache cleanup completed for %s", cache_key) 