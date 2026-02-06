# Agent Zero CLI - Research Findings

> Research conducted: 2026-02-06  
> Scope: Agent Zero codebase analysis + Textual framework evaluation

---

## 1. Agent Zero Backend Communication Protocol

### 1.1 Transport Layer

Agent Zero uses **Socket.IO** (not raw WebSockets) via `python-socketio.AsyncServer` running inside an ASGI stack served by Uvicorn. The Flask web app is mounted via `WSGIMiddleware`, and Socket.IO shares the same process.

- **Library**: `python-socketio` (server) / `socket.io-client` (browser)
- **ASGI stack**: Uvicorn → Starlette → Socket.IO ASGI app wrapping Flask WSGI
- **Default port**: 80 inside container, mapped to user-chosen port (default 5080)

### 1.2 Namespaces

Socket.IO namespaces are auto-discovered from `python/websocket_handlers/`:

| Namespace | Handler | Purpose |
|-----------|---------|--------|
| `/` | `_default.py` → `RootDefaultHandler` | Diagnostics only (echo). No auth, no CSRF. |
| `/state_sync` | `state_sync_handler.py` → `StateSyncHandler` | Real-time state push (replaces legacy `/poll`). Auth + CSRF required. |
| `/dev_websocket_test` | `dev_websocket_test_handler.py` | Development testing harness. |
| `/hello` | `hello_handler.py` | Example handler. |

### 1.3 State Sync Protocol (Primary Integration Point)

The state sync protocol is the **primary mechanism** for receiving real-time updates:

1. **Handshake**: Client sends `state_request` event with payload:
   ```json
   {
     "context": "<ctxid or null>",
     "log_from": 0,
     "notifications_from": 0,
     "timezone": "UTC"
   }
   ```
2. **Response**: Server returns `{runtime_epoch, seq_base}`
3. **Push**: Server emits `state_push` events containing `{runtime_epoch, seq, snapshot}` where `snapshot` is a `SnapshotV1`
4. **Coalescing**: Backend `StateMonitor` coalesces dirty signals per SID (25ms debounce window)

**Observed Behavior (live instance):**

- `/state_sync` namespace rejects polling transport; websocket transport is expected.
- `state_push` payload is wrapped as `{handlerId, eventId, correlationId, ts, data}` where `data.snapshot` holds the `SnapshotV1`.
- `state_request` ack is wrapped as `{correlationId, results: [{ok, data: {runtime_epoch, seq_base}}]}`.

### 1.4 SnapshotV1 Schema

The snapshot pushed via `state_push` contains:

```python
class SnapshotV1(TypedDict):
    deselect_chat: bool          # True if requested context no longer exists
    context: str                 # Active context ID (empty if none)
    contexts: list[dict]         # All chat contexts [{id, name, created_at, last_message, ...}]
    tasks: list[dict]            # Scheduler tasks
    logs: list[dict]             # Log items since log_from
    log_guid: str                # Current log GUID (changes on reset)
    log_version: int             # Current log version (for cursor advancement)
    log_progress: str | int      # Progress text (0 when no context)
    log_progress_active: bool    # Whether agent is actively processing
    paused: bool                 # Whether context is paused
    notifications: list[dict]    # Notifications since notifications_from
    notifications_guid: str
    notifications_version: int
```

### 1.5 Log Items

Each log entry in `logs` array:

```python
{
    "no": int,           # Sequential number
    "type": str,         # e.g., "response", "tool", "code_exe", "info", etc.
    "heading": str,      # Short heading
    "content": str,      # Full content (markdown)
    "kvps": dict | None, # Key-value pairs for structured data
    "timestamp": float,  # Unix timestamp
    "agentno": int,      # Agent number (0 = main, 1+ = subordinates)
    "id": str            # Unique log item ID
}
```

### 1.6 REST API Endpoints

All endpoints are POST unless noted. Most require auth + CSRF.

| Endpoint | Auth | CSRF | Purpose |
|----------|------|------|---------|
| `GET /health` | ❌ | ❌ | Health check, returns `{gitinfo, error}` |
| `POST /login` | ❌ | ❌ | Session login with form data `{username, password}` |
| `GET /csrf_token` | ✅ | ❌ | Get CSRF token for API calls |
| `POST /message` | ✅ | ✅ | Send message (synchronous - waits for full response) |
| `POST /message_async` | ✅ | ✅ | Send message (async - returns immediately, response via state_push) |
| `POST /chat_create` | ✅ | ✅ | Create new chat context `{current_context?, new_context?}` → `{ok, ctxid}` |
| `POST /chat_remove` | ✅ | ✅ | Remove chat `{context}` |
| `POST /chat_reset` | ✅ | ✅ | Reset chat `{context}` |
| `POST /chat_load` | ✅ | ✅ | Load chats from JSON `{chats: [...]}` → `{ctxids}` |
| `POST /chat_export` | ✅ | ✅ | Export chat as JSON |

### 1.7 Authentication Flow

1. **Check if auth is configured**: If `AUTH_LOGIN` env var is not set, all requests pass through without auth
2. **Login**: `POST /login` with form data `{username, password}` → sets `session["authentication"]` cookie
3. **CSRF**: `GET /csrf_token` → returns token, also sets `csrf_token_{runtime_id}` cookie
4. **API calls**: Include `X-CSRF-Token` header with the CSRF token
5. **Socket.IO**: Pass `{csrf_token}` in the `auth` payload during connection handshake

**Observed Behavior (live instance):**

- `GET /csrf_token` returns JSON with `{"token": "...", "runtime_id": "..."}`
- `GET /csrf_token` returns `302` to `/login` when auth is required
- Socket.IO connect requires both `auth.csrf_token` and a `csrf_token_<runtime_id>` cookie, plus a valid `Origin` header.

### 1.8 Message Flow (for CLI chat)

The recommended flow for the CLI:

1. Send message via `POST /message_async` with `{text, context}` → returns `{message: "Message received.", context: ctxid}`
2. Receive streaming updates via Socket.IO `state_push` events on `/state_sync` namespace
3. Parse `logs` array from snapshot to display agent responses in real-time
4. Track `log_progress_active` to know when the agent is done processing

### 1.9 Chat Persistence

- Chats stored in `usr/chats/<ctxid>/chat.json`
- Message files in `usr/chats/<ctxid>/messages/`
- Context data includes: id, name, created_at, type, last_message, agents, log, data, output_data
- Contexts listed via `AgentContext.all()` → filtered in snapshot builder

---

## 2. Textual Framework Evaluation

### 2.1 Overview

[Textual](https://textual.textualize.io/) is a Python TUI framework by Textualize (creators of Rich). It provides:

- **CSS-like styling** for terminal UIs
- **Widget system** with built-in components (Input, RichLog, Header, Footer, ListView, etc.)
- **Async-first** architecture (built on asyncio)
- **Event system** for handling user input and widget interactions
- **Reactive attributes** for state management

### 2.2 Key Components for CLI Chat

| Textual Widget | Use Case |
|---------------|----------|
| `App` | Main application container |
| `Input` | User message input field |
| `RichLog` | Scrollable log display for chat messages (supports Rich markup/markdown) |
| `Header` | App title bar |
| `Footer` | Keybinding hints |
| `ListView` / `ListItem` | Chat list for `/chats` command |
| `Static` | Status indicators (connection, agent activity) |

### 2.3 Async Compatibility

Textual runs on asyncio, which is ideal for our use case:
- Socket.IO client (`python-socketio[asyncio_client]`) is async-native
- HTTP requests via `httpx` (async) or `aiohttp`
- Can use `self.call_later()` or `asyncio.create_task()` for background work
- Workers API (`self.run_worker()`) for background tasks that update the UI

### 2.4 Relevant Textual Patterns

- **Command Palette**: Built-in command system, but for V1 we'll use simple `/command` parsing in the input field
- **Screens**: Can push/pop screens (useful for chat list overlay)
- **Notifications**: Built-in toast notifications
- **Bindings**: Key bindings for shortcuts (Ctrl+C to exit, etc.)

---

## 3. Python Socket.IO Client

### 3.1 Library

`python-socketio[asyncio_client]` provides `socketio.AsyncClient` for connecting to Socket.IO servers.

### 3.2 Key Considerations

- Must pass session cookies for auth (obtained from `/login` endpoint)
- Must pass CSRF token in `auth` payload for `/state_sync` namespace
- Namespace connection: `await sio.connect(url, namespaces=["/state_sync"])`
- Event handling: `@sio.on("state_push", namespace="/state_sync")`
- The client needs to handle reconnection gracefully

### 3.3 HTTP Client

For REST API calls, `httpx` is recommended:
- Async support
- Cookie jar for session management
- Clean API for JSON requests with custom headers

---

## 4. Existing CLI Patterns (Inspiration)

### 4.1 Claude Code (Anthropic)
- Full-screen TUI with chat interface
- Streaming responses with real-time display
- `/commands` for special actions
- Status bar showing connection and model info

### 4.2 Key UX Patterns to Adopt
- Clear visual separation between user input and agent response
- Streaming text display (character/chunk level)
- Activity indicator while agent is processing
- Command prefix (`/`) for non-chat actions
- Clean exit handling

---

## 5. Dependencies Summary

| Package | Purpose | Version |
|---------|---------|--------|
| `textual` | TUI framework | Latest (>=0.50) |
| `python-socketio[asyncio_client]` | Socket.IO client | Match server version |
| `httpx` | Async HTTP client | Latest |
| `rich` | Rich text rendering (bundled with Textual) | Bundled |

---

## 6. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Socket.IO version mismatch | Connection failures | Pin client version to match server |
| CSRF token expiry | API calls fail | Re-fetch token on 403 response |
| Session cookie expiry | Auth failures | Re-login automatically |
| Large log payloads | Slow rendering | Use `log_from` cursor to only fetch new entries |
| Terminal size constraints | Poor UX on small terminals | Responsive layout with minimum size check |
| No running instance | CLI unusable | Auto-detect and offer to run install.sh |
