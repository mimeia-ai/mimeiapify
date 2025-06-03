# Redis Handler - Refactored Architecture

This package refactors the monolithic `RedisHandler` God class (754 lines) into focused, single-responsibility repositories following SOLID principles.

## 🏗️ Architecture Overview

```
┌─ TenantCache (base)     ← Tenant context, TTL, common patterns
│
├─ KeyFactory            ← Stateless key building rules  
├─ serde                 ← JSON/Enum/DateTime/BaseModel serialization
│
├─ UserRepo              ← User data management
├─ HandlerRepo           ← Handler state management
├─ TableRepo             ← Table/DataFrame operations
├─ TriggerRepo           ← Expiration trigger management
├─ BatchRepo             ← Batch processing & tenant tracking
├─ SharedStateRepo       ← Tool/agent scratch space management
└─ GenericRepo           ← Generic key-value operations
```

## 🚀 Quick Start

### Basic Usage

```python
from symphony_ai.redis.redis_handler import UserRepo, HandlerRepo, TableRepo, SharedStateRepo

# Initialize repositories with tenant context
users = UserRepo(tenant="mimeia", ttl_default=3600)
handlers = HandlerRepo(tenant="mimeia", ttl_default=1800)
tables = TableRepo(tenant="mimeia")
shared_state = SharedStateRepo(tenant="mimeia", user_id="user123")

# User operations
await users.upsert("user123", {"name": "Alice", "score": 100})
user_data = await users.get("user123")
await users.increment_field("user123", "score", 10)

# Handler state management
await handlers.set("chat_handler", "user123", {"step": 1, "context": "greeting"})
state = await handlers.get("chat_handler", "user123")
await handlers.upsert("chat_handler", "user123", {"step": 2})

# Table operations
await tables.set("users_table", "pk123", {"name": "Bob", "active": True})
row = await tables.get("users_table", "pk123")

# Shared state for tools/agents
await shared_state.set("conversation", {"step": 1, "context": "greeting"})
step = await shared_state.get_field("conversation", "step")
```

## 📋 Repository Responsibilities

### UserRepo - User Data Management
```python
users = UserRepo(tenant="your_tenant")

# CRUD operations
await users.upsert("user_id", {"name": "Alice", "active": True})
user = await users.get("user_id")
await users.update_field("user_id", "last_login", datetime.now())
await users.delete("user_id")

# Atomic operations
await users.increment_field("user_id", "login_count")
await users.append_to_list("user_id", "tags", "premium")

# Search
user = await users.find_by_field("email", "alice@example.com")
exists = await users.exists("user_id")
```

### HandlerRepo - Conversational State
```python
handlers = HandlerRepo(tenant="your_tenant")

# State management
await handlers.set("chat_handler", "user_id", {"step": 1, "data": {...}})
state = await handlers.get("chat_handler", "user_id")
await handlers.update_field("chat_handler", "user_id", "step", 2)

# Merge operations (preserves existing state)
final_state = await handlers.upsert("chat_handler", "user_id", {"step": 3})
```

### TableRepo - Generic Data Tables
```python
tables = TableRepo(tenant="your_tenant")

# Table row operations
await tables.set("products", "prod_123", {"name": "Widget", "price": 29.99})
product = await tables.get("products", "prod_123")
await tables.update_field("products", "prod_123", "price", 19.99)

# Cross-table cleanup
await tables.delete_all_by_pkid("user_123")  # Deletes from all tables
```

### SharedStateRepo - Tool/Agent Scratch Space
```python
shared_state = SharedStateRepo(tenant="your_tenant", user_id="user123")

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

### TriggerRepo - Expiration-based Actions
```python
triggers = TriggerRepo(tenant="your_tenant")

# Set expiration triggers (for delayed actions)
await triggers.set("send_reminder", "user_123", ttl_seconds=3600)  # 1 hour
await triggers.set("cleanup_temp", "session_456", ttl_seconds=300)   # 5 minutes

# Cleanup
await triggers.delete("send_reminder", "user_123")
await triggers.delete_all_by_identifier("user_123")
```

### BatchRepo - Queue Management
```python
batch = BatchRepo(tenant="your_tenant")

# Enqueue for processing
await batch.enqueue("email_service", "daily_reports", "send", {
    "user_id": "123", "template": "daily_summary"
})

# Process batches
items = await batch.get_chunk("email_service", "daily_reports", "send", 0, 99)
await batch.trim("email_service", "daily_reports", "send", 100, -1)

# Global coordination (class methods - no tenant)
pending_tenants = await BatchRepo.get_pending_tenants("email_service")
await BatchRepo.remove_from_pending("email_service", "mimeia")
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

### Hash Storage Example

```python
# Mixed data with BaseModel fields
user_data = {
    "id": "user123",
    "profile": UserProfile(name="Alice", active=True, score=100),
    "settings": UserSettings(notifications=False),
    "last_login": datetime.now(),
    "login_count": 42
}

await users.upsert("user123", user_data)

# Retrieve with selective typing
models = {"profile": UserProfile, "settings": UserSettings}
retrieved = await users.get("user123", models=models)
# retrieved["profile"] → UserProfile instance
# retrieved["settings"] → UserSettings instance  
# retrieved["last_login"] → string (no model specified)
# retrieved["login_count"] → int
```

## 🔄 Migration from Old RedisHandler

### Before (God Class)
```python
handler = RedisHandler(tenant_prefix="mimeia", default_ttl=3600)
await handler.create_user_record("user123", {"name": "Alice"})
await handler.set_handler_state("chat", "user123", {"step": 1})
await handler.set_table_data("products", "prod123", {"name": "Widget"})
```

### After (Focused Repositories)
```python
users = UserRepo(tenant="mimeia", ttl_default=3600)
handlers = HandlerRepo(tenant="mimeia", ttl_default=3600)
tables = TableRepo(tenant="mimeia", ttl_default=3600)

await users.upsert("user123", {"name": "Alice"})
await handlers.set("chat", "user123", {"step": 1})
await tables.set("products", "prod123", {"name": "Widget"})
```

### From RedisSharedState to SharedStateRepo
```python
# Before (old RedisSharedState)
shared_state = RedisSharedState(waid="user123", tenant_prefix="mimeia", config=config)
await shared_state.set_state_async("conversation", {"step": 1})
step = await shared_state.get_state_field_async("conversation", "step")

# After (new SharedStateRepo)
shared_state = SharedStateRepo(tenant="mimeia", user_id="user123")
await shared_state.set("conversation", {"step": 1})
step = await shared_state.get_field("conversation", "step")
```

## 🏭 Production Implementation

### 1. Dependency Injection with GlobalSymphony Integration

The new architecture integrates seamlessly with the `GlobalSymphony` class from `symphony_concurrency.globals`:

```python
from symphony_ai.redis.redis_handler import (
    UserRepo, HandlerRepo, TableRepo, SharedStateRepo, TriggerRepo, BatchRepo
)
from symphony_ai.symphony_concurrency.globals import GlobalSymphony
from dataclasses import dataclass
from typing import Optional
import asyncio

@dataclass 
class RedisServices:
    """Complete Redis service layer with all repositories"""
    users: UserRepo
    handlers: HandlerRepo
    tables: TableRepo
    triggers: TriggerRepo
    batch: BatchRepo
    
    def shared_state(self, user_id: str) -> SharedStateRepo:
        """Create user-specific shared state repo"""
        return SharedStateRepo(tenant=self.users.tenant, user_id=user_id)
    
    @classmethod
    def create(cls, tenant: str, ttl: int = 86400):
        return cls(
            users=UserRepo(tenant=tenant, ttl_default=ttl),
            handlers=HandlerRepo(tenant=tenant, ttl_default=ttl//2),  # Shorter TTL for handlers
            tables=TableRepo(tenant=tenant, ttl_default=ttl),
            triggers=TriggerRepo(tenant=tenant, ttl_default=ttl//24),  # 1 hour for triggers
            batch=BatchRepo(tenant=tenant, ttl_default=ttl)
        )

# FastAPI Lifespan with GlobalSymphony
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize GlobalSymphony with Redis
    from symphony_ai.symphony_concurrency.globals import GlobalSymphonyConfig
    
    config = GlobalSymphonyConfig(
        redis_url="redis://localhost:6379/0",
        workers_user=os.cpu_count() * 4,
        workers_tool=32,
        workers_agent=16,
        max_concurrent=128
    )
    
    # This automatically sets up Redis connection in GlobalSymphony
    await GlobalSymphony.create(config)
    
    # Redis services are now available throughout the app
    yield
    
    # Cleanup is handled automatically by GlobalSymphony

app = FastAPI(lifespan=lifespan)

# Create redis services once at startup
redis_services = RedisServices.create(tenant="production")
```

### 2. FastAPI Request-Level Dependency Injection

```python
# Tenant resolution middleware
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    # Extract tenant from webhook headers, JWT, subdomain, etc.
    tenant_id = extract_tenant_from_request(request)
    user_id = extract_user_from_request(request)
    
    # Create tenant-specific repositories
    request.state.redis = RedisServices.create(tenant_id)
    request.state.user_id = user_id
    
    response = await call_next(request)
    return response

# Dependency functions for FastAPI
def get_redis_services(request: Request) -> RedisServices:
    return request.state.redis

def get_user_id(request: Request) -> str:
    return request.state.user_id

def get_shared_state(request: Request) -> SharedStateRepo:
    redis_services = get_redis_services(request)
    user_id = get_user_id(request)
    return redis_services.shared_state(user_id)

# FastAPI endpoints with DI
@app.post("/users")
async def create_user(
    user_data: dict,
    redis: RedisServices = Depends(get_redis_services)
):
    await redis.users.upsert(user_data["id"], user_data)
    return {"status": "created"}

@app.get("/conversation/state")
async def get_conversation_state(
    shared_state: SharedStateRepo = Depends(get_shared_state)
):
    return await shared_state.get("conversation")

@app.post("/tools/execute")
async def execute_tool(
    tool_data: dict,
    shared_state: SharedStateRepo = Depends(get_shared_state),
    loop: asyncio.AbstractEventLoop = Depends(lambda: GlobalSymphony.get().loop)
):
    # For tools that need to bridge sync/async (like agency-swarm BaseTool)
    def sync_tool_execution():
        # Run async operations in the main loop from tool context
        coro = shared_state.set_field("tool_state", "last_execution", datetime.now())
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=5)
    
    # Execute in thread pool if needed
    result = await loop.run_in_executor(
        GlobalSymphony.get().pool_tool, 
        sync_tool_execution
    )
    return {"status": "executed"}
```

### 3. Agency-Swarm Tool Integration

For integrating with agency-swarm tools that expect synchronous methods:

```python
from agency_swarm.tools import BaseTool
from symphony_ai.symphony_concurrency.globals import GlobalSymphony
import asyncio

class AsyncBaseTool(BaseTool):
    """Enhanced BaseTool with async Redis support"""
    
    def __init__(self):
        super().__init__()
        self._redis_services: Optional[RedisServices] = None
        self._user_id: Optional[str] = None
    
    def setup_redis(self, tenant: str, user_id: str):
        """Setup Redis services for this tool instance"""
        self._redis_services = RedisServices.create(tenant)
        self._user_id = user_id
    
    @property
    def shared_state(self) -> SharedStateRepo:
        """Get user-specific shared state repo"""
        if not self._redis_services or not self._user_id:
            raise RuntimeError("Tool not configured with Redis. Call setup_redis() first.")
        return self._redis_services.shared_state(self._user_id)
    
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

# Example tool using the new pattern
class EmailValidatorTool(AsyncBaseTool):
    email: str = Field(..., description="Email to validate")
    
    def run(self) -> str:
        # Use shared state to track tool execution
        self.set_state_field("tool_history", "last_tool", "email_validator")
        
        # Validate email logic here
        is_valid = "@" in self.email
        
        # Store result in shared state
        self.set_state_field("validation_results", self.email, is_valid)
        
        return f"Email {self.email} is {'valid' if is_valid else 'invalid'}"

# Tool usage in agent context
def setup_tools_for_agent(tenant: str, user_id: str):
    tools = [EmailValidatorTool()]
    for tool in tools:
        tool.setup_redis(tenant, user_id)
    return tools
```

### 4. Multi-Tenant Service with Caching

```python
from typing import Dict
import threading

class TenantServiceCache:
    """Thread-safe tenant-specific repository cache"""
    
    def __init__(self):
        self._cache: Dict[str, RedisServices] = {}
        self._lock = threading.RLock()
    
    def get_services(self, tenant_id: str) -> RedisServices:
        with self._lock:
            if tenant_id not in self._cache:
                self._cache[tenant_id] = RedisServices.create(tenant_id)
            return self._cache[tenant_id]
    
    def evict_tenant(self, tenant_id: str):
        """Remove tenant from cache (useful for testing)"""
        with self._lock:
            self._cache.pop(tenant_id, None)

# Global tenant service
tenant_service = TenantServiceCache()

# Use in FastAPI
def get_tenant_redis(request: Request) -> RedisServices:
    tenant_id = extract_tenant_from_request(request)
    return tenant_service.get_services(tenant_id)
```

## 🔧 Task Queue Handling

The old `task_queue` mechanism has been **removed** in favor of direct `asyncio.run_coroutine_threadsafe()` usage with `GlobalSymphony.get().loop`. This eliminates:

- ❌ Memory leaks from unbounded queues
- ❌ Complex pending task management  
- ❌ Nested event loop issues with `asyncio.run()`
- ❌ Manual task lifecycle management

### Before (Complex Queue System)
```python
# Old approach - complex queue plumbing
task_id = str(uuid.uuid4())
GlobalAgentState.pending_tasks[task_id] = asyncio.Future()
await GlobalAgentState.task_queue.put((task_id, some_coroutine()))
result = await GlobalAgentState.pending_tasks[task_id]
```

### After (Direct Loop Integration)  
```python
# New approach - direct and simple
loop = GlobalSymphony.get().loop
future = asyncio.run_coroutine_threadsafe(some_coroutine(), loop)
result = future.result(timeout=5)
```

## 🔍 Key Features

- **✅ Single Responsibility**: Each repository handles one domain
- **✅ Type Safety**: Full Pydantic BaseModel support with boolean optimization
- **✅ Tenant Isolation**: Automatic key prefixing and scoping
- **✅ TTL Management**: Flexible per-operation and per-repository TTL control
- **✅ Atomic Operations**: Built on your existing `ops.py` atomic operations
- **✅ Backward Compatible**: No breaking changes to existing Redis operations
- **✅ Testing Friendly**: Easy mocking and dependency injection
- **✅ Performance**: Optimized serialization and minimal Redis calls
- **✅ GlobalSymphony Integration**: Seamless event loop and thread pool management
- **✅ Tool/Agent Support**: Dedicated SharedStateRepo for scratch space

## 📚 Best Practices

1. **Use specific repositories** over `GenericRepo` when possible
2. **Define BaseModel mappings** once and reuse across operations
3. **Set appropriate TTLs** per data type (users: long, handlers: short, triggers: very short)
4. **Use dependency injection** for testability and tenant isolation
5. **Implement tenant resolution** at the middleware level
6. **Monitor repository performance** separately for each domain
7. **Use SharedStateRepo** for tool/agent scratch space instead of ad-hoc keys
8. **Leverage GlobalSymphony** for thread pool and event loop management
9. **Avoid the old task queue pattern** - use direct `run_coroutine_threadsafe()`
10. **Cache repository instances** per tenant to avoid repeated initialization 