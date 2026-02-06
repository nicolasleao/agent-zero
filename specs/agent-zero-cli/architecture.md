# Agent Zero CLI - Architecture Document

> Version: 1.0  
> Date: 2026-02-06  
> Status: Draft  
> Related: [research.md](./research.md), [spec.md](./spec.md), [tasks.md](./tasks.md)

---

## 1. Overview

The CLI is a **standalone Python package** that acts as a thin client to a running Agent Zero instance. It communicates exclusively through the existing HTTP REST API and Socket.IO WebSocket protocol — no changes to the Agent Zero backend are required.

```
┌──────────────────────┐         ┌──────────────────────────────┐
│   CLI (Textual App)  │         │  Agent Zero (Docker)         │
│                      │  HTTP   │                              │
│  ┌────────────────┐  │◄───────►│  Flask REST API              │
│  │  A0Client      │  │         │  /health, /login, /message.. │
│  │  (httpx +      │  │         │                              │
│  │   socketio)    │  │  WS     │  Socket.IO Server            │
│  └────────────────┘  │◄═══════►│  /state_sync namespace       │
│                      │         │                              │
│  ┌────────────────┐  │         └──────────────────────────────┘
│  │  Textual UI    │  │
│  │  (App, Widgets)│  │
│  └────────────────┘  │
│                      │
│  ┌────────────────┐  │
│  │  Config        │  │
│  │  (.cli-config) │  │
│  └────────────────┘  │
└──────────────────────┘
```

---

## 2. Directory Structure

```
cli/
├── .cli-config.json          # Default config (committed to repo)
├── pyproject.toml            # Package definition + dependencies
├── README.md                 # CLI-specific documentation
├── src/
│   └── agent_zero_cli/
│       ├── __init__.py
│       ├── __main__.py       # Entry point: python -m agent_zero_cli
│       ├── app.py            # Textual App class
│       ├── client.py         # A0Client: HTTP + Socket.IO communication
│       ├── config.py         # Config loading/saving
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── chat_log.py   # Chat message display widget
│       │   ├── input_bar.py  # Message input with command parsing
│       │   └── chat_list.py  # Chat list overlay for /chats
│       ├── screens/
│       │   ├── __init__.py
│       │   ├── chat.py       # Main chat screen
│       │   └── login.py      # Login screen (if auth required)
│       └── styles/
│           └── app.tcss      # Textual CSS styles
└── tests/
    ├── __init__.py
    ├── test_client.py
    └── test_config.py
```

---

## 3. Component Architecture

### 3.1 Config (`config.py`)

Responsible for loading and managing CLI configuration.

```python
@dataclass
class CLIConfig:
    instance_url: str = "http://localhost:5080"
    theme: str = "dark"
```

**Behavior:**
- On startup, look for `.cli-config.json` in the following order:
  1. Current working directory
  2. `~/.agentzero/.cli-config.json`
  3. Fall back to defaults
- Config is read-only at runtime (V1 — no config editing from CLI)
- The `instance_url` is the primary configuration value

### 3.2 A0Client (`client.py`)

The communication layer. Encapsulates all HTTP and Socket.IO interactions with the Agent Zero backend.

```python
class A0Client:
    """Client for communicating with a running Agent Zero instance."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.http: httpx.AsyncClient       # HTTP client with cookie jar
        self.sio: socketio.AsyncClient     # Socket.IO client
        self.csrf_token: str | None
        self.connected: bool
        self.authenticated: bool

        # Callbacks for UI updates
        self.on_state_push: Callable | None
        self.on_connect: Callable | None
        self.on_disconnect: Callable | None

    # --- Connection lifecycle ---
    async def check_health(self) -> bool
    async def login(self, username: str, password: str) -> bool
    async def needs_auth(self) -> bool
    async def connect_websocket(self) -> None
    async def disconnect(self) -> None

    # --- CSRF ---
    async def _fetch_csrf_token(self) -> str
    async def _ensure_csrf(self) -> None

    # --- Chat management ---
    async def create_chat(self) -> str  # returns context_id
    async def list_chats(self) -> list[dict]
    async def remove_chat(self, context_id: str) -> None

    # --- Messaging ---
    async def send_message(self, text: str, context_id: str) -> dict

    # --- State sync ---
    async def request_state(self, context_id: str | None, log_from: int = 0) -> dict
    def _handle_state_push(self, data: dict) -> None
```

**Key Design Decisions:**

1. **httpx for HTTP**: Async, supports cookie jars natively, clean API
2. **python-socketio AsyncClient for WebSocket**: Matches the server's Socket.IO protocol exactly
3. **Cookie-based auth**: The httpx client maintains a cookie jar. After `POST /login`, the session cookie is automatically included in subsequent requests
4. **CSRF handling**: Fetched once via `GET /csrf_token`, included as `X-CSRF-Token` header on all API calls and in Socket.IO `auth` payload
5. **Callback pattern**: The client exposes `on_state_push`, `on_connect`, `on_disconnect` callbacks that the Textual app hooks into

**Socket.IO Connection Flow:**

```
1. GET /health                          → verify instance is up
2. GET /csrf_token                      → get CSRF token + set cookie
3. sio.connect(url,                     → establish Socket.IO connection
     namespaces=["/state_sync"],
     auth={"csrf_token": token},
     headers={"Cookie": session_cookie + "; " + csrf_cookie,
              "Origin": instance_url,
              "Referer": instance_url + "/"})
4. sio.emit("state_request", payload,   → initialize state sync
     namespace="/state_sync")
5. Listen for "state_push" events       → receive real-time updates
```

**Socket.IO Cookie Forwarding:**

- Build a single `Cookie` header string from the httpx cookie jar (e.g., `"name=value; name2=value2"`).
- Pass the cookie header explicitly in `sio.connect(...)` to ensure authenticated namespace access.
- Include the CSRF cookie (`csrf_token_<runtime_id>=<token>`) in the same header; the server validates both cookie and auth payload.
- Send `Origin` (and `Referer` as a fallback) headers that match the instance host/port; otherwise the server rejects the handshake.

**Auth Detection:**

To determine if auth is required without hardcoding:
1. Call `GET /csrf_token`
2. If it returns 200, no auth needed (or already authenticated)
3. If it returns 302 to `/login`, auth is required → prompt for credentials
4. After `POST /login`, retry `GET /csrf_token`

**Observed Behavior (live instance):**

- `GET /csrf_token` returns `302` with `Location: /login` when auth is required.
- `GET /health` returns `200` even when auth is enabled.
- `GET /csrf_token` JSON uses `{"token": "..."}` for the CSRF value.
- WebSocket connect is rejected without a valid `Origin` header and `csrf_token_<runtime_id>` cookie.

### 3.3 Textual App (`app.py`)

The main application class that orchestrates the UI.

```python
class AgentZeroCLI(App):
    """Agent Zero CLI - Terminal Chat Interface"""

    CSS_PATH = "styles/app.tcss"
    TITLE = "Agent Zero CLI"
    BINDINGS = [
        Binding("ctrl+c", "quit", "Exit"),
    ]

    # Reactive state
    connected: reactive[bool] = reactive(False)
    current_context: reactive[str] = reactive("")
    agent_active: reactive[bool] = reactive(False)

    def __init__(self, config: CLIConfig):
        super().__init__()
        self.config = config
        self.client = A0Client(config.instance_url)
        self.log_cursor = 0  # tracks last seen log entry
```

**Startup Sequence:**

```
on_mount()
  ├── Load config
  ├── client.check_health()
  │   ├── Success → check auth
  │   └── Failure → offer install.sh
  ├── client.needs_auth()
  │   ├── True → push LoginScreen
  │   └── False → proceed
  ├── client.connect_websocket()
  ├── client.create_chat() → get context_id
  ├── client.request_state(context_id)
  └── Ready for input
```

### 3.4 Chat Screen (`screens/chat.py`)

The main chat interface screen.

```python
class ChatScreen(Screen):
    """Main chat interface."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield ChatLog()          # Scrollable message display
        yield InputBar()         # Message input with command parsing
        yield Footer()
```

### 3.5 ChatLog Widget (`widgets/chat_log.py`)

Displays the conversation using Textual's `RichLog` widget.

```python
class ChatLog(RichLog):
    """Displays chat messages and agent responses."""
```

**Log Entry Rendering:**

Each log entry from `state_push` is rendered based on its `type`:

| Log Type | Rendering |
|----------|----------|
| `response` | Rich markdown, full width, agent color |
| `tool` | Dimmed panel with tool name as header, collapsed by default |
| `code_exe` | Code block with syntax highlighting |
| `info` | Dimmed italic text |
| `warning` | Yellow text |
| `error` | Red text |
| User messages | Right-aligned or prefixed with "You:" |

**Streaming Behavior:**

The `state_push` events deliver incremental log updates:
1. Track `log_from` cursor (last processed log entry number)
2. On each `state_push`, extract `snapshot` from the event envelope (`payload.data.snapshot`) and read `snapshot.logs`
3. Render new entries incrementally into the `RichLog`
4. Update `log_from` cursor to `snapshot.log_version`
5. Show/hide spinner based on `snapshot.log_progress_active`

**UI Thread Safety:**

- Socket.IO callbacks may run outside Textual's main loop; use `call_from_thread()` or `post_message()` when updating widgets.

### 3.6 InputBar Widget (`widgets/input_bar.py`)

Handles user input and command parsing.

```python
class InputBar(Widget):
    """Message input with command parsing."""

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Type a message... (/help for commands)")
```

**Command Parsing:**

```python
def parse_input(text: str) -> tuple[str, str | None]:
    """Returns (command, args) or (None, None) for regular messages."""
    if text.startswith("/"):
        parts = text[1:].split(" ", 1)
        return parts[0], parts[1] if len(parts) > 1 else None
    return None, text  # regular message
```

| Command | Handler |
|---------|--------|
| `/chats` | Push ChatListScreen overlay |
| `/new` | Create new chat, switch context |
| `/exit` | Disconnect and quit |
| `/help` | Display help text in ChatLog |

### 3.7 ChatList Widget (`widgets/chat_list.py`)

Overlay screen for browsing and selecting previous chats.

```python
class ChatListScreen(ModalScreen):
    """Modal overlay showing previous chats."""

    def compose(self) -> ComposeResult:
        yield ListView()  # populated with chat items
```

**Data Source:**

The chat list comes from the `contexts` array in the last `state_push` snapshot. Each context contains:
- `id`: context ID
- `name`: chat name (or auto-generated)
- `created_at`: creation timestamp
- `last_message`: preview of last message

### 3.8 Login Screen (`screens/login.py`)

Shown when the Agent Zero instance requires authentication.

```python
class LoginScreen(Screen):
    """Login screen for authenticated instances."""

    def compose(self) -> ComposeResult:
        yield Static("Agent Zero - Login")
        yield Input(placeholder="Username", id="username")
        yield Input(placeholder="Password", password=True, id="password")
        yield Button("Login", id="login-btn")
```

---

## 4. Data Flow

### 4.1 Sending a Message

```
User types message → Enter
  │
  ├── InputBar.on_submit()
  │     ├── Disable input
  │     ├── Render user message in ChatLog
  │     └── app.client.send_message(text, context_id)
  │           └── POST /message_async {text, context}
  │                 Headers: X-CSRF-Token, Cookie
  │                 → Returns {message, context}
  │
  └── (async) state_push events arrive
        │
        ├── app._handle_state_push(snapshot)
        │     ├── Extract new logs (no > self.log_cursor)
        │     ├── For each new log entry:
        │     │     └── ChatLog.render_entry(entry)
        │     ├── Update self.log_cursor = snapshot.log_version
        │     ├── Update agent_active = snapshot.log_progress_active
        │     └── If not agent_active → re-enable input
        │
        └── (continues until log_progress_active = False)
```

### 4.2 Switching Chats

```
User types /chats → Enter
  │
  ├── Push ChatListScreen
  │     ├── Display contexts from last snapshot
  │     └── User selects a chat
  │
  ├── Pop ChatListScreen
  │     ├── Set current_context = selected.id
  │     ├── Clear ChatLog
  │     ├── Reset log_cursor = 0
  │     └── client.request_state(context_id, log_from=0)
  │           └── emit "state_request" on /state_sync
  │
  └── state_push arrives with full log for new context
        └── Render all log entries
```

---

## 5. State Management

The CLI maintains minimal local state:

```python
# App-level state
connected: bool              # Socket.IO connection status
current_context: str         # Active chat context ID
agent_active: bool           # Whether agent is processing
log_cursor: int              # Last processed log version
contexts: list[dict]         # Cached chat list from last snapshot
```

All authoritative state lives on the server. The CLI is a **thin client** that:
- Sends commands via REST API
- Receives state updates via Socket.IO
- Renders state into the terminal UI

---

## 6. Error Handling Strategy

### 6.1 Connection Errors

```python
async def _connection_monitor(self):
    """Handles reconnection with exponential backoff."""
    backoff = [1, 2, 4, 8, 16]  # seconds
    for attempt, delay in enumerate(backoff):
        try:
            await self.client.connect_websocket()
            self.connected = True
            return
        except Exception:
            self.connected = False
            await asyncio.sleep(delay)
    # All attempts failed
    self.notify("Connection lost. Use /exit to quit.", severity="error")
```

### 6.2 CSRF Token Refresh

```python
async def _api_call(self, method, url, **kwargs):
    """Wrapper that auto-refreshes CSRF on 403."""
    response = await self.http.request(method, url, **kwargs)
    if response.status_code == 403:
        await self._fetch_csrf_token()
        response = await self.http.request(method, url, **kwargs)
    return response
```

---

## 7. Dependencies

```toml
[project]
name = "agent-zero-cli"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "textual>=0.50.0",
    "python-socketio[asyncio_client]>=5.0.0",
    "httpx>=0.27.0",
]

[project.scripts]
agentzero = "agent_zero_cli.__main__:main"
```

---

## 8. What Does NOT Change

The CLI is a pure client. **No backend changes are required for V1:**

- ❌ No new API endpoints
- ❌ No new WebSocket handlers
- ❌ No changes to state_snapshot.py
- ❌ No changes to authentication
- ❌ No changes to chat persistence

The CLI uses the exact same APIs and protocols as the web UI.

---

## 9. Future Considerations (Post-V1)

| Feature | Architecture Impact |
|---------|-------------------|
| File attachments | Add multipart upload support to A0Client |
| Settings management | New screens + API calls to settings endpoints |
| Agent tree visualization | Parse log entries for subordinate agent activity |
| Notifications | Subscribe to notification events, render as toasts |
| Multiple instances | Config supports named profiles |
| Package distribution | Publish to PyPI as `agent-zero-cli` |
| Auto-update | Check GitHub releases on startup |
