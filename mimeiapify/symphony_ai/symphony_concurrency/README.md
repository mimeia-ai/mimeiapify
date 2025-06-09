Below is the **precise life-cycle** that wires a `ContextVar` to every
WebSocket message and lets `AsyncBaseTool` read "the right" shared state—even
when your tool code is running inside a `ThreadPoolExecutor`.

---

## 1️⃣  Library glue (done once)

```python
# symphony_concurrency/redis/context.py
from contextvars import ContextVar
from symphony_concurrency.redis.shared_state import SharedState

_current_ss: ContextVar[SharedState] = ContextVar("current_shared_state")
```

```python
# symphony_concurrency/async_base_tool.py
from agency_swarm.tools import BaseTool
from symphony_concurrency.redis.context import _current_ss
from symphony_concurrency.redis.shared_state import SharedState

class AsyncBaseTool(BaseTool):
    @property
    def _shared_state(self) -> SharedState:           # <── every tool calls this
        return _current_ss.get()                      # raises if not bound
```

**Nothing else in the tools needs to change.**
They simply call `self._shared_state` and expect it to exist.

---

## 2️⃣  Where the binding happens – **at the very top** of each request

### The FastAPI WebSocket loop

```python
from symphony_concurrency.redis.context import _current_ss
from symphony_concurrency.redis.shared_state import SharedState
from symphony_concurrency.globals import GlobalSymphony

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        msg = await ws.receive_json()
        tenant   = msg["tenant_id"]        # <- wherever you store it
        user_id  = msg["user_id"]
        payload  = msg["text"]

        # 1️⃣ build a fresh SharedState *object*
        ss = SharedState(tenant=tenant, user_id=user_id)

        # 2️⃣ bind it to THIS coroutine (and child tasks) only
        token = _current_ss.set(ss)
        try:
            # 3️⃣ do the blocking agent call in pool_user
            pool   = GlobalSymphony.get().pool_user
            result = await asyncio.wrap_future(
                pool.submit(lambda: agency.get_completion(payload))
            )
            await ws.send_json({"assistant": result})
        finally:
            # 4️⃣ restore previous value to avoid leaks
            _current_ss.reset(token)
```

Key points:

* **`_current_ss.set(ss)`** stores the object in the *context* of this
  WebSocket handler task.
  Every `await` keeps that association alive.

* **`pool.submit(...)`** captures the **current Context** (PEP 567 rule).
  Python serialises the dict `{_current_ss: ss}` and hands it to the worker
  thread.
  Inside the worker, `AsyncBaseTool._shared_state` therefore resolves to `ss`
  even though you're now in a different thread.

* After you send the reply, **`_current_ss.reset(token)`** removes the binding,
  so the next message (or another client) starts with a clean slate.

---

## 3️⃣  Visual timeline with two concurrent messages

```plaintext
Main event-loop (single thread)

┌─ WS-A coroutine ──────────────────────┐
│ _current_ss.set(SS_A)                 │
│ pool.submit(tool.run)  ─────────┐     │
│ await ... context switch …       │     │
└──────────────────────────────────┘     │
                                        │
┌─ WS-B coroutine ──────────────────────┐│
│ _current_ss.set(SS_B)                 ││
│ pool.submit(other_tool.run) ─────┐    ││
└──────────────────────────────────┘│    │
                                    │    │
ThreadPool worker-1 (for A)         │    │ ThreadPool worker-2 (for B)
context = { _current_ss: SS_A }     │    │ context = { _current_ss: SS_B }
tool.run → self._shared_state == SS_A│    │ tool.run → self._shared_state == SS_B
```

No race: each worker got the Context snapshot that was active at submission
time.

---

## 4️⃣  Implementing Tools with RedisSharedState

### AsyncBaseTool provides two approaches for Redis operations:

#### **Inside `async def _arun()` → Use `await self.ss.method()` directly**

Good news — inside `_arun()` you're **already running on the main event-loop**, so you can call the `RedisSharedState` **directly with `await`**.

```python
from mimeiapify.symphony_ai.symphony_concurrency.tools.async_tool import AsyncBaseTool
from pydantic import Field

class RememberTool(AsyncBaseTool):
    """Stores user preferences in Redis shared state."""
    colour: str = Field(..., description="User's favorite color")

    async def _arun(self) -> str:
        # Direct async calls - no sync wrappers needed
        await self.ss.update_field(
            key="profile",
            field="favourite_colour", 
            value=self.colour
        )
        
        # Read existing data
        profile = await self.ss.get("profile")
        existing_colors = profile.get("color_history", []) if profile else []
        existing_colors.append(self.colour)
        
        # Update with history
        await self.ss.update_field("profile", "color_history", existing_colors)
        
        return f"I'll remember your colour is {self.colour}"
```

#### **Outside async context → Use sync wrapper methods**

For synchronous `run()` methods or mixed sync/async code:

```python
class SyncRememberTool(AsyncBaseTool):
    colour: str = Field(...)

    def run(self) -> str:  # Override run() for pure sync approach
        # Use sync wrapper methods that bridge to async
        current_profile = self.get_state("profile") or {}
        current_profile["favourite_colour"] = self.colour
        
        self.upsert_state("profile", current_profile)
        return f"Updated profile with colour {self.colour}"
```

### **Complete CRUD Operations Reference:**

| Operation | Async (in `_arun()`) | Sync (in `run()`) | Returns |
|-----------|---------------------|-------------------|---------|
| **Create/Update** | `await self.ss.upsert(key, data)` | `self.upsert_state(key, data)` | `bool` |
| **Read all** | `await self.ss.get(key)` | `self.get_state(key)` | `dict \| None` |
| **Read field** | `await self.ss.get_field(key, field)` | `self.get_field(key, field)` | `Any` |
| **Update field** | `await self.ss.update_field(key, field, value)` | `self.update_field(key, field, value)` | `bool` |
| **Delete field** | `await self.ss.delete_field(key, field)` | `self.delete_field(key, field)` | `int` |
| **Delete state** | `await self.ss.delete(key)` | `self.delete_state(key)` | `int` |
| **Check exists** | `await self.ss.exists(key)` | `self.state_exists(key)` | `bool` |
| **List all** | `await self.ss.list_states()` | `self.list_states()` | `list[str]` |
| **Clear all** | `await self.ss.clear_all_states()` | `self.clear_all_states()` | `int` |

### **Mixed Async/Sync Example:**

```python
import httpx
import json
import gzip
from mimeiapify.symphony_ai.symphony_concurrency.globals import GlobalSymphony

class ComplexTool(AsyncBaseTool):
    payload: dict = Field(...)

    async def _arun(self) -> str:
        # 1. Async HTTP call
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.example.com/log", json=self.payload)
        
        # 2. Store response in Redis (async)
        await self.ss.upsert("last_api_response", {
            "status": response.status_code,
            "data": response.json(),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # 3. Heavy CPU work in thread pool
        sym = GlobalSymphony.get()
        compressed = await sym.loop.run_in_executor(
            sym.pool_tool, 
            self._compress_payload,  # sync method
            json.dumps(self.payload)
        )
        
        # 4. Store compressed result (async)
        await self.ss.update_field("cache", "compressed_size", len(compressed))
        
        return f"Processed payload: {len(compressed)} bytes compressed"
    
    def _compress_payload(self, json_str: str) -> bytes:
        """Sync CPU-intensive method running in thread pool"""
        # Inside thread pool - use sync wrappers if needed
        metadata = self.get_field("profile", "compression_settings") or {}
        level = metadata.get("level", 6)
        
        return gzip.compress(json_str.encode(), compresslevel=level)
```

### **Why it's safe:**

* `_arun()` is scheduled via `asyncio.run_coroutine_threadsafe(coro, loop)` in `AsyncBaseTool.run()`. The coroutine executes **on the same event-loop** as your FastAPI app.
* The `_current_ss` `ContextVar` flows naturally across `await`s, so `self.ss` keeps pointing to the right per-request instance.
* Sync wrappers (`self.update_field()`, etc.) hop back to the loop and block the current thread until the awaitable finishes.

---

## 5️⃣  FastAPI Middleware Integration

### HTTP Middleware for Shared State

```python
from fastapi import FastAPI, Request
from mimeiapify.symphony_ai.redis.context import _current_ss
from mimeiapify.symphony_ai.redis.redis_handler.shared_state import RedisSharedState

app = FastAPI()

def parse_tenant_user(request: Request) -> tuple[str, str]:
    """
    Extract tenant and user_id from request.
    
    Customize this function based on your authentication strategy:
    - JWT tokens in Authorization header
    - Custom headers (X-Tenant-ID, X-User-ID)
    - URL path parameters
    - Query parameters
    """
    # Option 1: Custom headers
    tenant = request.headers.get("X-Tenant-ID", "default")
    user_id = request.headers.get("X-User-ID", "anonymous")
    
    # Option 2: From JWT token (example)
    # auth_header = request.headers.get("Authorization", "")
    # if auth_header.startswith("Bearer "):
    #     token = auth_header[7:]
    #     payload = decode_jwt(token)
    #     tenant = payload.get("tenant", "default")
    #     user_id = payload.get("user_id", "anonymous")
    
    # Option 3: From path parameters
    # tenant = request.path_params.get("tenant", "default")
    # user_id = request.path_params.get("user_id", "anonymous")
    
    return tenant, user_id

@app.middleware("http")
async def bind_shared_state(request: Request, call_next):
    """
    Bind RedisSharedState to request context for all HTTP endpoints.
    
    This makes `self.ss` available in any AsyncBaseTool called during the request.
    """
    tenant, user_id = parse_tenant_user(request)
    ss = RedisSharedState(tenant=tenant, user_id=user_id)
    token = _current_ss.set(ss)
    
    try:
        response = await call_next(request)
        return response
    finally:
        _current_ss.reset(token)

# Example HTTP endpoint
@app.post("/agent/chat")
async def chat_endpoint(message: str, request: Request):
    """HTTP endpoint with automatic shared state binding."""
    # Extract context (already bound by middleware)
    tenant, user_id = parse_tenant_user(request)
    
    # Create agency with thread persistence
    agency = build_agency_with_threads(tenant, user_id)
    
    # Any AsyncBaseTool called here has access to self.ss
    response = await agency.get_response(message)
    return {"message": response}
```

### WebSocket Integration with UserThreads

```python
from fastapi import WebSocket, WebSocketDisconnect
from mimeiapify.symphony_ai.symphony_concurrency.tools.user_threads import UserThreads
from mimeiapify.symphony_ai.symphony_concurrency.globals import GlobalSymphony
from agency_swarm import Agency

@app.websocket("/ws/{tenant}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, tenant: str, user_id: str):
    """
    WebSocket endpoint with both shared state and thread persistence.
    
    URL pattern: /ws/mimeia/user123
    """
    await websocket.accept()
    
    # Create shared state and user threads
    ss = RedisSharedState(tenant=tenant, user_id=user_id)
    ut = UserThreads(tenant=tenant, user_id=user_id)
    
    # Bind shared state to WebSocket context
    token = _current_ss.set(ss)
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            message = data.get("message", "")
            
            # Create agency with thread persistence
            agency = Agency(
                agents=[main_agent, ceo_agent, coder_agent],
                threads_callbacks={
                    "load": ut.sync_load_threads,
                    "save": ut.sync_save_threads,
                },
                max_prompt_tokens=4000,
                max_completion_tokens=4000,
            )
            
            # Process message (runs in thread pool, has access to shared state)
            sym = GlobalSymphony.get()
            response = await asyncio.wrap_future(
                sym.pool_user.submit(lambda: agency.get_completion(message))
            )
            
            # Send response
            await websocket.send_json({
                "response": response,
                "user_id": user_id,
                "tenant": tenant
            })
            
    except WebSocketDisconnect:
        print(f"User {user_id} disconnected")
    finally:
        _current_ss.reset(token)

# Alternative: WebSocket with message-based tenant/user extraction
@app.websocket("/ws")
async def websocket_endpoint_dynamic(websocket: WebSocket):
    """
    WebSocket endpoint where tenant/user_id come in each message.
    
    Message format: {"tenant": "mimeia", "user_id": "user123", "message": "Hello"}
    """
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_json()
            tenant = data.get("tenant", "default")
            user_id = data.get("user_id", "anonymous") 
            message = data.get("message", "")
            
            # Create scoped state for this message
            ss = RedisSharedState(tenant=tenant, user_id=user_id)
            ut = UserThreads(tenant=tenant, user_id=user_id)
            
            token = _current_ss.set(ss)
            try:
                # Build agency with thread persistence
                agency = build_agency_with_threads(tenant, user_id, ut)
                
                # Process message
                sym = GlobalSymphony.get()
                response = await asyncio.wrap_future(
                    sym.pool_user.submit(lambda: agency.get_completion(message))
                )
                
                await websocket.send_json({"response": response})
                
            finally:
                _current_ss.reset(token)
                
    except WebSocketDisconnect:
        print("WebSocket disconnected")
```

### Helper Functions

```python
def build_agency_with_threads(tenant: str, user_id: str, ut: UserThreads = None) -> Agency:
    """
    Factory function to create Agency with thread persistence.
    
    Parameters
    ----------
    tenant : str
        Tenant identifier
    user_id : str
        User identifier  
    ut : UserThreads, optional
        UserThreads instance, creates new one if None
        
    Returns
    -------
    Agency
        Configured agency with thread callbacks
    """
    if ut is None:
        ut = UserThreads(tenant=tenant, user_id=user_id)
    
    return Agency(
        agents=[main_agent, ceo_agent, coder_agent],
        threads_callbacks={
            "load": ut.sync_load_threads,
            "save": ut.sync_save_threads,
        },
        max_prompt_tokens=4000,
        max_completion_tokens=4000,
    )

async def reset_user_conversation(tenant: str, user_id: str) -> bool:
    """
    Utility to reset user's conversation state.
    
    Clears both thread persistence and shared state.
    """
    try:
        ut = UserThreads(tenant=tenant, user_id=user_id)
        ss = RedisSharedState(tenant=tenant, user_id=user_id)
        
        # Clear threads and shared state
        await ut.delete_threads()
        await ss.clear_all_states()
        
        return True
    except Exception as e:
        logger.error(f"Failed to reset conversation for {tenant}/{user_id}: {e}")
        return False

# Example endpoint to reset conversation
@app.post("/users/{tenant}/{user_id}/reset")
async def reset_conversation(tenant: str, user_id: str):
    """Reset user's conversation history and shared state."""
    success = await reset_user_conversation(tenant, user_id)
    return {"success": success, "message": "Conversation reset" if success else "Reset failed"}
```

### Authentication Integration Examples

```python
# JWT-based authentication
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer

security = HTTPBearer()

def parse_jwt_context(token: str = Depends(security)) -> tuple[str, str]:
    """Extract tenant/user from JWT token."""
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=["HS256"])
        tenant = payload.get("tenant", "default")
        user_id = payload.get("sub")  # standard JWT subject field
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
            
        return tenant, user_id
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/agent/chat")
async def authenticated_chat(
    message: str, 
    context: tuple[str, str] = Depends(parse_jwt_context)
):
    """Endpoint with JWT authentication."""
    tenant, user_id = context
    
    # Shared state is automatically bound via middleware
    agency = build_agency_with_threads(tenant, user_id)
    response = await agency.get_response(message)
    
    return {"message": response}

# API Key-based authentication  
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Extract tenant/user from API key."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return JSONResponse({"error": "API key required"}, status_code=401)
    
    # Look up tenant/user from API key
    tenant, user_id = await lookup_api_key(api_key)
    if not tenant:
        return JSONResponse({"error": "Invalid API key"}, status_code=401)
    
    # Bind shared state
    ss = RedisSharedState(tenant=tenant, user_id=user_id)
    token = _current_ss.set(ss)
    
    try:
        response = await call_next(request)
        return response
    finally:
        _current_ss.reset(token)
```

### Key Benefits of This Integration

| Feature | Benefit |
|---------|---------|
| **Automatic context binding** | Every AsyncBaseTool has access to `self.ss` without manual setup |
| **Thread persistence** | Conversations continue across requests/reconnections |
| **Tenant isolation** | Complete data separation between organizations |
| **WebSocket support** | Real-time chat with full state management |
| **Flexible auth** | Works with JWT, API keys, headers, path params |
| **Error resilience** | Graceful degradation if Redis is unavailable |
| **Performance optimized** | Only writes when data actually changes |

### FastAPI Lifespan Integration

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from mimeiapify.symphony_ai.symphony_concurrency.globals import GlobalSymphony, GlobalSymphonyConfig

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Proper startup and shutdown lifecycle management."""
    # Startup
    config = GlobalSymphonyConfig(
        redis_url="redis://localhost:6379",
        workers_tool=64,
        workers_agent=16,
        redis_enable_key_events=True
    )
    await GlobalSymphony.create(config)
    print("🚀 GlobalSymphony initialized")
    
    yield  # Application runs here
    
    # Shutdown
    await GlobalSymphony.shutdown()
    print("🛑 GlobalSymphony shutdown complete")

app = FastAPI(lifespan=lifespan)

# Your endpoints here...
@app.post("/agent/chat")
async def chat_endpoint(message: str, request: Request):
    # GlobalSymphony is available throughout app lifecycle
    agency = build_agency_with_threads(tenant, user_id)
    response = await agency.get_response(message)
    return {"message": response}
```

---

## 6️⃣  Frequently-asked questions

| Question                                                    | Answer                                                                                                                   |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Do I still need `BaseTool._shared_state = …`?**           | No. Delete all global assignments.                                                                                       |
| **What if a Tool is called *before* I set the ContextVar?** | `AsyncBaseTool.ss` raises `LookupError`. Initialize a dummy default once at app start if you want a fallback. |
| **Does `ContextVar` work across `await` inside the tool?**  | Yes. Every `await` preserves the same Context until the coroutine finishes.                                              |
| **What about `ProcessPoolExecutor`?**                       | Context propagation works only for threads, not processes. For a ProcessPool you must pass the data explicitly.          |
| **When should I use async vs sync Redis methods?**          | Use `await self.ss.method()` in `_arun()`. Use `self.method_name()` wrappers in sync code or `run()` overrides.        |

---

### TL;DR

* Bind `RedisSharedState` → `_current_ss.set()` **per request/WebSocket message**
* The binding follows every `await` and is captured when you hop into a thread
* `AsyncBaseTool` provides both async (`await self.ss.*`) and sync (`self.*_state()`) APIs
* **Inside `_arun()`**: use async methods directly
* **Outside async context**: use sync wrapper methods
* All operations are tenant-scoped, thread-safe, and use sophisticated Redis serialization
