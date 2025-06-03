"""
Redis Handler Package - Refactored from God Class

This package refactors the monolithic RedisHandler class following SOLID principles:

Single Responsibility:
- UserRepo: User data management
- HandlerRepo: Handler state management  
- TableRepo: Table/DataFrame operations
- TriggerRepo: Expiration trigger management
- BatchRepo: Batch processing and tenant tracking
- SharedStateRepo: Shared state between tools and agents
- GenericRepo: Generic key-value operations

Each repository inherits from TenantCache which provides:
- Tenant-scoped key building via KeyFactory
- Common Redis operation patterns
- TTL management
- Serialization via serde module

Usage:
    from symphony_ai.redis.redis_handler import UserRepo, HandlerRepo, SharedStateRepo
    
    users = UserRepo(tenant="my_tenant", ttl_default=3600)
    await users.upsert("user123", {"name": "Alice", "score": 100})
    
    handlers = HandlerRepo(tenant="my_tenant") 
    await handlers.set("chat_handler", "user123", {"state": "waiting"})
    
    shared_state = SharedStateRepo(tenant="my_tenant", user_id="user123")
    await shared_state.set("conversation", {"step": 1, "context": {...}})
"""

from .user_repo import UserRepo
from .handler_repo import HandlerRepo
from .table_repo import TableRepo
from .trigger_repo import TriggerRepo
from .batch_repo import BatchRepo
from .shared_state_repo import SharedStateRepo
from .generic_repo import GenericRepo
from .tenant_cache import TenantCache
from .key_factory import KeyFactory
from . import serde

__all__ = [
    "UserRepo",
    "HandlerRepo", 
    "TableRepo",
    "TriggerRepo",
    "BatchRepo",
    "SharedStateRepo",
    "GenericRepo",
    "TenantCache",
    "KeyFactory",
    "serde",
] 