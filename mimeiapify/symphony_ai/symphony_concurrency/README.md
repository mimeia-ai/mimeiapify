Below is the **precise life-cycle** that wires a `ContextVar` to every
WebSocket message and lets `AsyncBaseTool` read “the right” shared state—even
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
  even though you’re now in a different thread.

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

## 4️⃣  Frequently-asked questions

| Question                                                    | Answer                                                                                                                   |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Do I still need `BaseTool._shared_state = …`?**           | No. Delete all global assignments.                                                                                       |
| **What if a Tool is called *before* I set the ContextVar?** | `AsyncBaseTool._shared_state` raises `LookupError`. Initialise a dummy default once at app start if you want a fallback. |
| **Does `ContextVar` work across `await` inside the tool?**  | Yes. Every `await` preserves the same Context until the coroutine finishes.                                              |
| **What about `ProcessPoolExecutor`?**                       | Context propagation works only for threads, not processes. For a ProcessPool you must pass the data explicitly.          |

---

### TL;DR

* Bind `SharedState` → `_current_ss.set()` **per WebSocket message** (or per HTTP request).
* The binding follows every `await` and is captured when you hop into a thread.
* `AsyncBaseTool` simply reads the ContextVar—no global mutation, no races.
