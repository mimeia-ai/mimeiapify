# Redis Module - Clean Architecture

This module provides Redis operations with clean separation of concerns, following SOLID principles. The Redis Handler package has been refactored from a monolithic 754-line God class into focused, single-responsibility repositories.

## 🏗️ Module Structure

```
redis/
├── __init__.py                    # Main module exports
├── context.py                     # ContextVar for thread-safe shared state
├── redis_client.py               # Redis connection management  
├── ops.py                         # Low-level atomic Redis operations
├── README.md                      # This file
└── redis_handler/                 # Repository layer
    ├── __init__.py               # Repository exports
    ├── utils/                     # Infrastructure & utilities
    │   ├── __init__.py           # Utils exports
    │   ├── key_factory.py        # Stateless key building rules
    │   ├── serde.py              # JSON/Enum/DateTime/BaseModel serialization
    │   └── tenant_cache.py       # Base class with common Redis patterns
    ├── user.py                   # User data management → RedisUser
    ├── shared_state.py           # Tool/agent scratch space → RedisSharedState
    ├── state_handler.py          # Handler state management → RedisStateHandler
    ├── table.py                  # Table/DataFrame operations → RedisTable
    ├── batch.py                  # Batch processing → RedisBatch
    ├── trigger.py                # Expiration triggers → RedisTrigger
    └── generic.py                # Generic key-value ops → RedisGeneric
```

## 🚀 Quick Start

### Basic Repository Usage

```python
from mimeiapify.symphony_ai.redis.redis_handler import (
    RedisUser, RedisStateHandler, RedisTable, RedisSharedState
)

# Initialize repositories with tenant and user context
user = RedisUser(tenant="mimeia", user_id="user123", ttl_default=3600)
handler = RedisStateHandler(tenant="mimeia", user_id="user123", ttl_default=1800)
tables = RedisTable(tenant="mimeia")  # No user_id needed for tables
shared_state = RedisSharedState(tenant="mimeia", user_id="user123")

# User operations - cleaner API without user_id repetition
await user.upsert({"name": "Alice", "score": 100})
user_data = await user.get()
await user.increment_field("score", 10)

# Handler state management - cleaner API
await handler.set("chat_handler", {"step": 1, "data": {...}})
state = await handler.get("chat_handler")
await handler.update_field("chat_handler", "step", 2)

# Merge operations (preserves existing state)
final_state = await handler.upsert("chat_handler", {"step": 3})

# Table operations - unchanged (no user context needed)
await tables.set("users_table", "pk123", {"name": "Bob", "active": True})
row = await tables.get("users_table", "pk123")

# Shared state for tools/agents - unchanged
await shared_state.set("conversation", {"step": 1, "context": "greeting"})
step = await shared_state.get_field("conversation", "step")
```

### Context-Aware Shared State (Thread-Safe)

The `context.py` module provides thread-safe access to shared state using Python's `ContextVar`:

```python
from mimeiapify.symphony_ai.redis.context import _current_ss, RedisSharedState
from mimeiapify.symphony_ai import GlobalSymphony
import asyncio

# In your FastAPI handler or async function
async def handle_user_request(tenant: str, user_id: str, message: str):
    # Create user-specific shared state
    ss = RedisSharedState(tenant=tenant, user_id=user_id)
    
    # Bind to current context (task-local)
    token = _current_ss.set(ss)
    try:
        # Any code running in this context (including tools in thread pools)
        # will see this specific shared state instance
        await process_user_message(message)
    finally:
        _current_ss.reset(token)  # Always cleanup

# Tools can access the context-bound shared state
from mimeiapify.symphony_ai.redis.context import _current_ss

class SomeAsyncTool:
    async def execute(self):
        # Gets the shared state bound to current request context
        shared_state = _current_ss.get()
        await shared_state.set_field("tool_state", "last_tool", "SomeAsyncTool")

# For synchronous tools (like agency-swarm BaseTool)
class SomeSyncTool:
    def run(self):
        shared_state = _current_ss.get()
        loop = GlobalSymphony.get().loop
        
        # Bridge to async world
        coro = shared_state.set_field("tool_state", "last_tool", "SomeSyncTool")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=5)
```

## 📋 Repository Responsibilities

### RedisUser - User Data Management
```python
user = RedisUser(tenant="your_tenant", user_id="user123")

# CRUD operations - no need to repeat user_id
await user.upsert({"name": "Alice", "active": True})
user_data = await user.get()
await user.update_field("last_login", datetime.now())
await user.delete()

# Atomic operations
await user.increment_field("login_count")
await user.append_to_list("tags", "premium")

# Search (still requires pattern matching across users)
pattern_user = RedisUser(tenant="your_tenant", user_id="*")
found_user = await pattern_user.find_by_field("email", "alice@example.com")

# Check existence
exists = await user.exists()
```

### RedisStateHandler - Conversational State
```python
handler = RedisStateHandler(tenant="your_tenant", user_id="user123")

# State management - cleaner API without user_id repetition
await handler.set("chat_handler", {"step": 1, "data": {...}})
state = await handler.get("chat_handler")
await handler.update_field("chat_handler", "step", 2)

# Merge operations (preserves existing state)
final_state = await handler.upsert("chat_handler", {"step": 3})
```

### RedisTable - Generic Data Tables
```python
tables = RedisTable(tenant="your_tenant")

# Table row operations
await tables.set("products", "prod_123", {"name": "Widget", "price": 29.99})
product = await tables.get("products", "prod_123")
await tables.update_field("products", "prod_123", "price", 19.99)

# Cross-table cleanup
await tables.delete_all_by_pkid("user_123")  # Deletes from all tables
```

### RedisSharedState - Tool/Agent Scratch Space
```python
shared_state = RedisSharedState(tenant="your_tenant", user_id="user123")

# Store conversation state for tools/agents
await shared_state.set("conversation", {
    "step": 1, 
    "context": "user_greeting",
    "collected_data": {"name": "Alice"}
})

# Update specific fields
await shared_state.set_field("conversation", "step", 2)
await shared_state.set_field("conversation", "last_tool", "email_validator")

# Retrieve state data
current_step = await shared_state.get_field("conversation", "step")
full_state = await shared_state.get("conversation")

# Manage multiple states per user
await shared_state.set("form_progress", {"page": 1, "completed_fields": []})
await shared_state.set("tool_cache", {"last_api_call": datetime.now()})

# Cleanup operations
states = await shared_state.list_states()  # ["conversation", "form_progress", "tool_cache"]
await shared_state.delete("form_progress")
await shared_state.clear_all_states()  # Delete all states for this user
```

### RedisTrigger - Expiration-based Actions
```python
triggers = RedisTrigger(tenant="your_tenant")

# Set expiration triggers (for delayed actions)
await triggers.set("send_reminder", "user_123", ttl_seconds=3600)  # 1 hour
await triggers.set("cleanup_temp", "session_456", ttl_seconds=300)   # 5 minutes

# Cleanup
await triggers.delete("send_reminder", "user_123")
await triggers.delete_all_by_identifier("user_123")
```

### RedisBatch - Queue Management
```python
batch = RedisBatch(tenant="your_tenant")

# Enqueue for processing
await batch.enqueue("email_service", "daily_reports", "send", {
    "user_id": "123", "template": "daily_summary"
})

# Process batches
items = await batch.get_chunk("email_service", "daily_reports", "send", 0, 99)
await batch.trim("email_service", "daily_reports", "send", 100, -1)

# Global coordination (class methods - no tenant)
pending_tenants = await RedisBatch.get_pending_tenants("email_service")
await RedisBatch.remove_from_pending("email_service", "mimeia")
```

## 🔧 Pydantic BaseModel Support

The system provides full support for Pydantic models with optimized boolean storage (`"1"`/`"0"` instead of `true`/`false`).

### Define Your Models

```python
from pydantic import BaseModel
from typing import List

class UserProfile(BaseModel):
    name: str
    active: bool
    score: int
    preferences: List[bool]

class UserSettings(BaseModel):
    notifications: bool
    theme: str = "dark"
    auto_save: bool = True
```

### Typed Operations

```python
# Store BaseModel directly
profile = UserProfile(name="Alice", active=True, score=100, preferences=[True, False])
await users.update_field("user123", "profile", profile)

# Retrieve with automatic typing
models = {
    "profile": UserProfile,
    "settings": UserSettings
}
user_data = await users.get("user123", models=models)
# user_data["profile"] is now a UserProfile instance
# user_data["profile"].active is bool, not string

# Search with typed results
found_user = await users.find_by_field("active", True, models=models)

# Handler state with context models
handler_models = {"context": ConversationContext}
state = await handlers.get("chat_handler", "user123", models=handler_models)
```

## 🏭 Production Implementation with GlobalSymphony

### 1. FastAPI Integration with Context-Aware Shared State

```python
from mimeiapify.symphony_ai.redis.context import _current_ss, RedisSharedState
from mimeiapify.symphony_ai import GlobalSymphony
from mimeiapify.symphony_ai.redis.redis_handler import RedisUser, RedisStateHandler
from fastapi import FastAPI, Request, Depends
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize GlobalSymphony with Redis
    from mimeiapify.symphony_ai import GlobalSymphonyConfig
    
    config = GlobalSymphonyConfig(
        redis_url="redis://localhost:6379/0",
        workers_user=os.cpu_count() * 4,
        workers_tool=32,
        workers_agent=16,
        max_concurrent=128
    )
    
    await GlobalSymphony.create(config)
    yield

app = FastAPI(lifespan=lifespan)

# Middleware for context binding
@app.middleware("http")
async def bind_shared_state_context(request: Request, call_next):
    tenant_id = extract_tenant_from_request(request)
    user_id = extract_user_from_request(request)
    
    if tenant_id and user_id:
        # Create and bind shared state to request context
        ss = RedisSharedState(tenant=tenant_id, user_id=user_id)
        token = _current_ss.set(ss)
        
        try:
            response = await call_next(request)
            return response
        finally:
            _current_ss.reset(token)
    else:
        return await call_next(request)

# FastAPI endpoints can now use context-aware tools
@app.post("/chat")
async def handle_chat(message: str, request: Request):
    # Any tools or agents called from here will automatically
    # have access to the correct shared state via _current_ss.get()
    
    # Direct access to shared state
    ss = _current_ss.get()
    await ss.set_field("conversation", "last_message", message)
    
    # Tools in thread pools will also see the same shared state
    result = await process_with_tools(message)
    return {"response": result}
```

### 2. Agency-Swarm Tool Integration with Context

```python
from agency_swarm.tools import BaseTool
from mimeiapify.symphony_ai.redis.context import _current_ss
from mimeiapify.symphony_ai import GlobalSymphony
import asyncio

class AsyncBaseTool(BaseTool):
    """Enhanced BaseTool with context-aware Redis support"""
    
    @property
    def shared_state(self) -> RedisSharedState:
        """Get context-bound shared state - safe across threads"""
        return _current_ss.get()
    
    def run_async(self, coro) -> Any:
        """Execute async operation from sync tool context"""
        loop = GlobalSymphony.get().loop
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    
    # Convenient sync wrappers for common operations
    def get_state(self, state_name: str) -> dict:
        return self.run_async(self.shared_state.get(state_name)) or {}
    
    def set_state(self, state_name: str, data: dict) -> bool:
        return self.run_async(self.shared_state.set(state_name, data))
    
    def get_state_field(self, state_name: str, field: str):
        return self.run_async(self.shared_state.get_field(state_name, field))
    
    def set_state_field(self, state_name: str, field: str, value) -> bool:
        return self.run_async(self.shared_state.set_field(state_name, field, value))

# Example tool using context-aware shared state
class EmailValidatorTool(AsyncBaseTool):
    email: str = Field(..., description="Email to validate")
    
    def run(self) -> str:
        # No need to manually inject shared state - it's context-aware!
        self.set_state_field("tool_history", "last_tool", "email_validator")
        
        # Validate email logic here
        is_valid = "@" in self.email
        
        # Store result in shared state
        self.set_state_field("validation_results", self.email, is_valid)
        
        return f"Email {self.email} is {'valid' if is_valid else 'invalid'}"
```

## 🔧 Migration from Old Architecture

### Key Changes
- **✅ Removed task queue complexity**: No more `GlobalAgentState.task_queue` or `pending_tasks`
- **✅ Added context-aware shared state**: Thread-safe access via `ContextVar`
- **✅ Organized utils**: Infrastructure moved to `redis_handler/utils/`
- **✅ Simplified imports**: Clean package structure with proper `__init__.py` files

### Before (Complex Queue System)
```python
# Old approach - complex queue plumbing
task_id = str(uuid.uuid4())
GlobalAgentState.pending_tasks[task_id] = asyncio.Future()
await GlobalAgentState.task_queue.put((task_id, some_coroutine()))
result = await GlobalAgentState.pending_tasks[task_id]

# Manual shared state injection per tool
BaseTool._shared_state = redis_shared_state  # Race condition!
```

### After (Direct Integration)  
```python
# New approach - direct and context-aware
loop = GlobalSymphony.get().loop
future = asyncio.run_coroutine_threadsafe(some_coroutine(), loop)
result = future.result(timeout=5)

# Context-aware shared state (thread-safe)
token = _current_ss.set(RedisSharedState(tenant="mimeia", user_id="user123"))
try:
    # All tools automatically get the right shared state
    result = await call_tools()
finally:
    _current_ss.reset(token)
```

## 🔍 Key Features

- **✅ Single Responsibility**: Each repository handles one domain
- **✅ Type Safety**: Full Pydantic BaseModel support with boolean optimization
- **✅ Tenant Isolation**: Automatic key prefixing and scoping
- **✅ TTL Management**: Flexible per-operation and per-repository TTL control
- **✅ Atomic Operations**: Built on Redis atomic operations
- **✅ Context-Aware**: Thread-safe shared state via `ContextVar`
- **✅ GlobalSymphony Integration**: Seamless event loop and thread pool management
- **✅ Clean Architecture**: Utils separated from business logic
- **✅ No Task Queue Overhead**: Direct async/sync bridging

## 📚 Best Practices

1. **Use context-aware shared state** instead of manual injection
2. **Leverage `_current_ss.get()`** in tools for automatic context binding
3. **Use specific repositories** over `RedisGeneric` when possible
4. **Define BaseModel mappings** once and reuse across operations
5. **Set appropriate TTLs** per data type (users: long, handlers: short, triggers: very short)
6. **Bind shared state at request level** using middleware
7. **Always reset context tokens** in `finally` blocks
8. **Use `GlobalSymphony.get().loop`** for async/sync bridging
9. **Import from utils** for infrastructure components
10. **Cache repository instances** per tenant to avoid repeated initialization

## 🎯 Import Patterns

```python
# Main Redis functionality
from mimeiapify.symphony_ai.redis import RedisClient, ops, context

# Repository layer
from mimeiapify.symphony_ai.redis.redis_handler import (
    RedisUser, RedisSharedState, RedisStateHandler, RedisTable,
    RedisBatch, RedisTrigger, RedisGeneric
)

# Infrastructure utilities
from mimeiapify.symphony_ai.redis.redis_handler.utils import (
    KeyFactory, dumps, loads, TenantCache
)

# Context-aware shared state
from mimeiapify.symphony_ai.redis.context import _current_ss, RedisSharedState

# GlobalSymphony integration
from mimeiapify.symphony_ai import GlobalSymphony, GlobalSymphonyConfig

# Utilities and logging
from mimeiapify.utils import logger, setup_logging
``` 