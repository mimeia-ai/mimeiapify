"""
Redis Handler Module

Repository classes for Redis operations with clean separation of concerns.
Each class handles a specific domain: users, shared state, tables, batches, etc.
"""

# Core infrastructure (utils)
from .utils import KeyFactory, dumps, loads, TenantCache

# Domain-specific repositories  
from .user import RedisUser
from .shared_state import RedisSharedState
from .state_handler import RedisStateHandler
from .table import RedisTable
from .batch import RedisBatch
from .trigger import RedisTrigger
from .generic import RedisGeneric

__all__ = [
    # Infrastructure
    "KeyFactory",
    "dumps", 
    "loads",
    "TenantCache",
    
    # Repositories
    "RedisUser",
    "RedisSharedState", 
    "RedisStateHandler",
    "RedisTable",
    "RedisBatch",
    "RedisTrigger",
    "RedisGeneric",
] 