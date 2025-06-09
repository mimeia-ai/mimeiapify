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

```python
from fastapi import FastAPI, Request
from mimeiapify.symphony_ai.redis.context import _current_ss
from mimeiapify.symphony_ai.redis.redis_handler.shared_state import RedisSharedState

app = FastAPI()

@app.middleware("http")
async def bind_shared_state(request: Request, call_next):
    # Extract tenant/user from request (headers, JWT, etc.)
    tenant = request.headers.get("X-Tenant-ID", "default")
    user_id = request.headers.get("X-User-ID", "anonymous")
    
    # Create scoped shared state
    ss = RedisSharedState(tenant=tenant, user_id=user_id)
    token = _current_ss.set(ss)
    
    try:
        response = await call_next(request)
        return response
    finally:
        _current_ss.reset(token)

@app.post("/agent/chat")
async def chat_endpoint(message: str):
    # Any AsyncBaseTool called here will have access to the bound RedisSharedState
    result = await some_agent.get_completion(message)
    return {"response": result}
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
