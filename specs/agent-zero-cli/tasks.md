# Agent Zero CLI - Implementation Tasks

> Version: 1.0  
> Date: 2026-02-06  
> Status: Draft  
> Related: [research.md](./research.md), [spec.md](./spec.md), [architecture.md](./architecture.md)

---

## Task Overview

Tasks are organized in **phases** that should be implemented sequentially. Within each phase, tasks can be parallelized where noted. Each task includes estimated effort, dependencies, and acceptance criteria.

```
Phase 1: Project Scaffolding          [Tasks 1-3]    ~2h
Phase 2: Backend Client                [Tasks 4-8]    ~4h
Phase 3: Core UI                       [Tasks 9-13]   ~5h
Phase 4: Chat Features                 [Tasks 14-17]  ~4h
Phase 5: Polish & Edge Cases           [Tasks 18-21]  ~3h
                                       ─────────────
                                       Total: ~18h
```

---

## Phase 1: Project Scaffolding

### Task 1: Initialize CLI package structure

**Effort:** 30 min  
**Dependencies:** None  
**Ref:** [architecture.md §2 - Directory Structure](./architecture.md#2-directory-structure)

**Description:**  
Create the `cli/` directory at the repo root (same level as `webui/`) with the full package structure.

**Steps:**
1. Create directory tree:
   ```
   cli/
   ├── src/
   │   └── agent_zero_cli/
   │       ├── __init__.py
   │       ├── __main__.py
   │       ├── app.py
   │       ├── client.py
   │       ├── config.py
   │       ├── widgets/
   │       │   └── __init__.py
   │       ├── screens/
   │       │   └── __init__.py
   │       └── styles/
   │           └── app.tcss
   └── tests/
       └── __init__.py
   ```
2. Create `__init__.py` with `__version__ = "0.1.0"`
3. Create `__main__.py` with minimal entry point:
   ```python
   def main():
       from agent_zero_cli.app import AgentZeroCLI
       app = AgentZeroCLI()
       app.run()

   if __name__ == "__main__":
       main()
   ```

**Acceptance Criteria:**
- [ ] `cli/` directory exists with all subdirectories
- [ ] All `__init__.py` files present
- [ ] `__main__.py` has entry point stub

---

### Task 2: Create pyproject.toml

**Effort:** 15 min  
**Dependencies:** Task 1  
**Ref:** [architecture.md §7 - Dependencies](./architecture.md#7-dependencies)

**Description:**  
Define the package metadata and dependencies.

**Steps:**
1. Create `cli/pyproject.toml`:
   ```toml
   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"

   [project]
   name = "agent-zero-cli"
   version = "0.1.0"
   description = "Terminal chat interface for Agent Zero"
   requires-python = ">=3.10"
   dependencies = [
       "textual>=0.50.0",
       "python-socketio[asyncio_client]>=5.0.0",
       "httpx>=0.27.0",
   ]

   [project.scripts]
   agentzero = "agent_zero_cli.__main__:main"

   [tool.hatch.build.targets.wheel]
   packages = ["src/agent_zero_cli"]
   ```
2. Create `cli/README.md` with basic usage instructions

**Acceptance Criteria:**
- [ ] `pyproject.toml` is valid and parseable
- [ ] `pip install -e cli/` succeeds
- [ ] `agentzero` command is available after install (even if it crashes — just needs to be registered)

---

### Task 3: Create default config file

**Effort:** 15 min  
**Dependencies:** Task 1  
**Ref:** [spec.md §6 - Configuration](./spec.md#6-configuration), [architecture.md §3.1 - Config](./architecture.md#31-config-configpy)

**Description:**  
Create the default `.cli-config.json` and the config loader.

**Steps:**
1. Create `cli/.cli-config.json`:
   ```json
   {
     "instance_url": "http://localhost:5080",
     "theme": "dark"
   }
   ```
2. Implement `cli/src/agent_zero_cli/config.py`:
   ```python
   import json
   from dataclasses import dataclass, asdict
   from pathlib import Path

   @dataclass
   class CLIConfig:
       instance_url: str = "http://localhost:5080"
       theme: str = "dark"

   def load_config() -> CLIConfig:
       """Load config from .cli-config.json, searching CWD then ~/.agentzero/"""
       search_paths = [
           Path.cwd() / ".cli-config.json",
           Path.home() / ".agentzero" / ".cli-config.json",
       ]
       for path in search_paths:
           if path.exists():
               with open(path) as f:
                   data = json.load(f)
               return CLIConfig(**{k: v for k, v in data.items() if k in CLIConfig.__dataclass_fields__})
       return CLIConfig()
   ```

**Acceptance Criteria:**
- [ ] `.cli-config.json` exists with defaults
- [ ] `load_config()` returns defaults when no file found
- [ ] `load_config()` reads from CWD first, then `~/.agentzero/`
- [ ] Unknown keys in JSON are ignored (forward compatibility)

---

## Phase 2: Backend Client

### Task 4: Implement health check

**Effort:** 30 min  
**Dependencies:** Task 2 (httpx installed)  
**Ref:** [research.md §1.6 - REST API Endpoints](./research.md#16-rest-api-endpoints)

**Description:**  
Implement the `A0Client` class with health check capability.

**Steps:**
1. Create `cli/src/agent_zero_cli/client.py` with `A0Client` class
2. Initialize `httpx.AsyncClient` with cookie jar
3. Implement `check_health()` method:
   - `GET {base_url}/health`
   - Returns `True` if status 200, `False` otherwise
   - Timeout: 5 seconds
   - Catch `httpx.ConnectError`, `httpx.TimeoutException`

**Acceptance Criteria:**
- [ ] `A0Client(base_url)` initializes without errors
- [ ] `check_health()` returns `True` for running instance
- [ ] `check_health()` returns `False` for unreachable instance (no exception thrown)
- [ ] 5-second timeout prevents hanging

---

### Task 5: Implement authentication

**Effort:** 45 min  
**Dependencies:** Task 4  
**Ref:** [research.md §1.7 - Authentication Flow](./research.md#17-authentication-flow), [architecture.md §3.2 - A0Client](./architecture.md#32-a0client-clientpy)

**Description:**  
Add auth detection and login to `A0Client`.

**Steps:**
1. Implement `needs_auth() -> bool`:
   - `GET {base_url}/csrf_token`
   - If 200 → no auth needed (or already authed), return `False`
   - If 401/302 → auth required, return `True`
2. Implement `login(username, password) -> bool`:
   - `POST {base_url}/login` with form data `{username, password}`
   - Return `True` if session cookie is set (response 200/302 to `/`)
   - Return `False` on auth failure
3. Implement `_fetch_csrf_token() -> str`:
   - `GET {base_url}/csrf_token`
   - Store token in `self.csrf_token`
   - Return token string
4. Implement `_get_headers() -> dict`:
   - Returns `{"X-CSRF-Token": self.csrf_token}` when token is available

**Acceptance Criteria:**
- [ ] `needs_auth()` correctly detects auth-required instances
- [ ] `needs_auth()` returns `False` for no-auth instances
- [ ] `login()` succeeds with correct credentials
- [ ] `login()` returns `False` with wrong credentials
- [ ] CSRF token is stored and included in subsequent requests
- [ ] Cookie jar persists session across requests

---

### Task 6: Implement Socket.IO connection

**Effort:** 1 hour  
**Dependencies:** Task 5  
**Ref:** [research.md §1.3 - State Sync Protocol](./research.md#13-state-sync-protocol-primary-integration-point), [architecture.md §3.2 - Socket.IO Connection Flow](./architecture.md#32-a0client-clientpy)

**Description:**  
Add Socket.IO connection with state sync to `A0Client`.

**Steps:**
1. Initialize `socketio.AsyncClient` in `A0Client.__init__`
2. Implement `connect_websocket()`:
   - Ensure CSRF token is available (call `_fetch_csrf_token()` if needed)
   - Extract cookies from httpx cookie jar for Socket.IO headers
   - Connect: `await sio.connect(base_url, namespaces=["/state_sync"], auth={"csrf_token": token}, headers={"Cookie": cookie_string})`
   - Register event handlers:
     - `@sio.on("state_push", namespace="/state_sync")` → calls `self.on_state_push` callback
     - `@sio.on("connect", namespace="/state_sync")` → calls `self.on_connect` callback
     - `@sio.on("disconnect", namespace="/state_sync")` → calls `self.on_disconnect` callback
3. Implement `request_state(context_id, log_from=0)`:
   - Emit `state_request` event on `/state_sync` namespace with callback
   - Payload: `{"context": context_id, "log_from": log_from, "notifications_from": 0, "timezone": "UTC"}`
   - Return the response (contains `runtime_epoch`, `seq_base`)
4. Implement `disconnect()`:
   - `await sio.disconnect()`
   - Close httpx client

**Acceptance Criteria:**
- [ ] Socket.IO connects successfully to a running instance
- [ ] `state_request` returns `runtime_epoch` and `seq_base`
- [ ] `state_push` events trigger the `on_state_push` callback
- [ ] Connection/disconnection callbacks fire correctly
- [ ] Cookies are properly forwarded from httpx to Socket.IO
- [ ] `disconnect()` cleanly closes both Socket.IO and HTTP connections

---

### Task 7: Implement chat management

**Effort:** 30 min  
**Dependencies:** Task 5  
**Ref:** [research.md §1.6 - REST API Endpoints](./research.md#16-rest-api-endpoints)

**Description:**  
Add chat CRUD operations to `A0Client`.

**Steps:**
1. Implement `create_chat() -> str`:
   - `POST {base_url}/chat_create` with `{}` body
   - Headers: CSRF token
   - Return `response["ctxid"]`
2. Implement `list_chats() -> list[dict]`:
   - This comes from the `contexts` array in `state_push` snapshots
   - Store latest contexts list in `self.contexts` when processing state_push
   - Return `self.contexts`
3. Implement `remove_chat(context_id) -> None`:
   - `POST {base_url}/chat_remove` with `{"context": context_id}`

**Acceptance Criteria:**
- [ ] `create_chat()` returns a valid context ID string
- [ ] `list_chats()` returns list of chat context dicts
- [ ] `remove_chat()` successfully removes a chat
- [ ] All methods include CSRF token in headers

---

### Task 8: Implement message sending

**Effort:** 30 min  
**Dependencies:** Task 6  
**Ref:** [research.md §1.8 - Message Flow](./research.md#18-message-flow-for-cli-chat)

**Description:**  
Add async message sending to `A0Client`.

**Steps:**
1. Implement `send_message(text, context_id) -> dict`:
   - `POST {base_url}/message_async` with `{"text": text, "context": context_id}`
   - Headers: CSRF token
   - Return response dict `{"message": "...", "context": "..."}`
2. Add CSRF auto-refresh wrapper:
   - If any API call returns 403, call `_fetch_csrf_token()` and retry once

**Acceptance Criteria:**
- [ ] `send_message()` sends message and returns without waiting for agent response
- [ ] Agent response arrives via `state_push` events (verified in Task 6)
- [ ] CSRF 403 triggers automatic token refresh and retry

---

## Phase 3: Core UI

### Task 9: Create minimal Textual app shell

**Effort:** 45 min  
**Dependencies:** Tasks 1-3  
**Ref:** [architecture.md §3.3 - Textual App](./architecture.md#33-textual-app-apppy), [spec.md §7 - UI Layout](./spec.md#7-ui-layout-textual)

**Description:**  
Create the basic Textual app with header, chat area, input, and footer.

**Steps:**
1. Implement `cli/src/agent_zero_cli/app.py`:
   ```python
   from textual.app import App, ComposeResult
   from textual.binding import Binding
   from textual.widgets import Header, Footer, RichLog, Input
   from textual.reactive import reactive

   class AgentZeroCLI(App):
       CSS_PATH = "styles/app.tcss"
       TITLE = "Agent Zero CLI"
       BINDINGS = [
           Binding("ctrl+c", "quit", "Exit", show=True),
       ]

       connected = reactive(False)
       agent_active = reactive(False)

       def compose(self) -> ComposeResult:
           yield Header()
           yield RichLog(id="chat-log", wrap=True, highlight=True, markup=True)
           yield Input(placeholder="Type a message... (/help for commands)", id="message-input")
           yield Footer()
   ```
2. Create `cli/src/agent_zero_cli/styles/app.tcss`:
   ```css
   #chat-log {
       height: 1fr;
       border: solid $primary;
       padding: 1;
   }

   #message-input {
       dock: bottom;
       margin-top: 1;
   }
   ```
3. Update `__main__.py` to load config and pass to app

**Acceptance Criteria:**
- [ ] `python -m agent_zero_cli` launches a Textual app
- [ ] Header shows "Agent Zero CLI"
- [ ] Chat log area is visible and scrollable
- [ ] Input field is at the bottom and focusable
- [ ] Footer shows Ctrl+C binding
- [ ] Ctrl+C exits cleanly

---

### Task 10: Implement startup connection flow

**Effort:** 1 hour  
**Dependencies:** Tasks 4-6, 9  
**Ref:** [spec.md US-1, US-2, US-3](./spec.md#4-user-stories), [architecture.md §3.3 - Startup Sequence](./architecture.md#33-textual-app-apppy)

**Description:**  
Wire up the app startup to connect to the Agent Zero instance.

**Steps:**
1. In `app.py`, implement `on_mount()` as an async worker:
   ```python
   async def on_mount(self):
       self.run_worker(self._startup(), exclusive=True)

   async def _startup(self):
       config = load_config()
       self.client = A0Client(config.instance_url)
       log = self.query_one("#chat-log", RichLog)

       # Health check
       log.write("[dim]Connecting to Agent Zero...[/dim]")
       if not await self.client.check_health():
           log.write("[red]No Agent Zero instance found at {url}[/red]")
           log.write("[dim]Run install.sh to set up Agent Zero[/dim]")
           return

       # Auth check
       if await self.client.needs_auth():
           # Push login screen (Task 12)
           pass

       # Connect WebSocket
       self.client.on_state_push = self._handle_state_push
       self.client.on_connect = lambda: setattr(self, "connected", True)
       self.client.on_disconnect = lambda: setattr(self, "connected", False)
       await self.client.connect_websocket()

       # Create initial chat
       self.current_context = await self.client.create_chat()
       await self.client.request_state(self.current_context)

       log.write("[green]Connected to Agent Zero ✔[/green]")
   ```
2. Handle the "no instance" case:
   - Display message in chat log
   - Ask user if they want to run install.sh (use Textual's `self.app.push_screen()` or simple prompt)

**Acceptance Criteria:**
- [ ] App connects to running instance on startup
- [ ] "Connected" message appears in chat log
- [ ] If instance is down, clear error message is shown
- [ ] If auth is needed, login flow is triggered (can be stub for now)
- [ ] WebSocket state_push events start arriving after connection

---

### Task 11: Implement install.sh fallback

**Effort:** 30 min  
**Dependencies:** Task 10  
**Ref:** [spec.md US-1](./spec.md#us-1-first-launch-no-instance-running)

**Description:**  
When no instance is found, offer to run the install script.

**Steps:**
1. When health check fails, display prompt in the chat log
2. Listen for user input "y" or "n" in the input field
3. If "y":
   - Suspend the Textual app temporarily (`self.app.suspend()`)
   - Run `install.sh` as a subprocess in the foreground (interactive — needs terminal access for user prompts)
   - After install.sh completes, resume the Textual app
   - Retry health check
4. If "n", show message and allow manual config

**Implementation Note:**  
Textual's `App.suspend()` context manager allows temporarily giving control back to the terminal for interactive subprocesses.

**Acceptance Criteria:**
- [ ] User is prompted when no instance is found
- [ ] Answering "y" runs install.sh interactively
- [ ] After install.sh completes, CLI retries connection
- [ ] Answering "n" shows helpful message

---

### Task 12: Implement login screen

**Effort:** 45 min  
**Dependencies:** Task 5, 9  
**Ref:** [spec.md US-3](./spec.md#us-3-first-launch-instance-running-auth-required), [architecture.md §3.8 - Login Screen](./architecture.md#38-login-screen-screensloginpy)

**Description:**  
Create a login screen for authenticated instances.

**Steps:**
1. Create `cli/src/agent_zero_cli/screens/login.py`:
   ```python
   from textual.screen import Screen
   from textual.widgets import Static, Input, Button
   from textual.containers import Vertical, Center

   class LoginScreen(Screen):
       def compose(self) -> ComposeResult:
           with Center():
               with Vertical(id="login-box"):
                   yield Static("Agent Zero - Login", id="login-title")
                   yield Input(placeholder="Username", id="username")
                   yield Input(placeholder="Password", password=True, id="password")
                   yield Button("Login", id="login-btn", variant="primary")
                   yield Static("", id="login-error")
   ```
2. Handle login button press:
   - Get username/password from inputs
   - Call `client.login(username, password)`
   - On success: dismiss screen, continue startup
   - On failure: show error, allow retry (max 3 attempts)
3. Add styles for login screen in `app.tcss`

**Acceptance Criteria:**
- [ ] Login screen appears when auth is required
- [ ] Username and password fields work (password is masked)
- [ ] Successful login dismisses screen and continues to chat
- [ ] Failed login shows error message
- [ ] 3 failed attempts exits the app with message

---

### Task 13: Implement connection status indicator

**Effort:** 30 min  
**Dependencies:** Task 10  
**Ref:** [spec.md US-7](./spec.md#us-7-connection-status)

**Description:**  
Show connection status in the header/subtitle.

**Steps:**
1. Use Textual's `Header` widget with reactive subtitle:
   ```python
   def watch_connected(self, connected: bool) -> None:
       if connected:
           self.sub_title = "● Connected"
       else:
           self.sub_title = "○ Disconnected"

   def watch_agent_active(self, active: bool) -> None:
       if active:
           self.sub_title = "⣾ Agent thinking..."
   ```
2. Update `connected` reactive when Socket.IO connects/disconnects
3. Update `agent_active` reactive from `state_push` `log_progress_active` field

**Acceptance Criteria:**
- [ ] Header shows "● Connected" when connected (green)
- [ ] Header shows "○ Disconnected" when disconnected (red)
- [ ] Header shows activity indicator when agent is processing
- [ ] Status updates in real-time

---

## Phase 4: Chat Features

### Task 14: Implement message sending from UI

**Effort:** 45 min  
**Dependencies:** Tasks 8, 9  
**Ref:** [spec.md US-4](./spec.md#us-4-send-a-message), [architecture.md §4.1 - Sending a Message](./architecture.md#41-sending-a-message)

**Description:**  
Wire up the input field to send messages.

**Steps:**
1. Handle `Input.Submitted` event in the app:
   ```python
   async def on_input_submitted(self, event: Input.Submitted) -> None:
       text = event.value.strip()
       if not text:
           return

       input_widget = self.query_one("#message-input", Input)
       input_widget.value = ""  # clear input

       # Check for commands
       if text.startswith("/"):
           await self._handle_command(text)
           return

       # Send message
       log = self.query_one("#chat-log", RichLog)
       log.write(f"[bold cyan]You:[/bold cyan] {text}")
       input_widget.disabled = True

       try:
           await self.client.send_message(text, self.current_context)
       except Exception as e:
           log.write(f"[red]Error sending message: {e}[/red]")
           input_widget.disabled = False
   ```
2. Input is disabled while agent is processing
3. Input is re-enabled when `log_progress_active` becomes `False`

**Acceptance Criteria:**
- [ ] Typing a message and pressing Enter sends it
- [ ] User message appears in chat log immediately
- [ ] Input field is cleared after sending
- [ ] Input is disabled while agent processes
- [ ] Input is re-enabled when agent finishes
- [ ] Send errors are displayed in chat log

---

### Task 15: Implement streaming response display

**Effort:** 1 hour  
**Dependencies:** Tasks 6, 14  
**Ref:** [research.md §1.5 - Log Items](./research.md#15-log-items), [architecture.md §3.5 - ChatLog Widget](./architecture.md#35-chatlog-widget-widgetschat_logpy)

**Description:**  
Render agent responses from `state_push` log entries in real-time.

**Steps:**
1. Implement `_handle_state_push(data)` in the app:
   ```python
   def _handle_state_push(self, data: dict) -> None:
       snapshot = data.get("snapshot", data)  # handle envelope
       logs = snapshot.get("logs", [])
       log_widget = self.query_one("#chat-log", RichLog)

       for entry in logs:
           if entry["no"] <= self.log_cursor:
               continue
           self._render_log_entry(log_widget, entry)
           self.log_cursor = entry["no"]

       # Update cursor for next request
       self.log_cursor = snapshot.get("log_version", self.log_cursor)

       # Update agent activity status
       self.agent_active = snapshot.get("log_progress_active", False)
       if not self.agent_active:
           self.query_one("#message-input", Input).disabled = False

       # Cache contexts for /chats command
       self.contexts = snapshot.get("contexts", [])
   ```
2. Implement `_render_log_entry(log_widget, entry)` with type-based rendering:
   ```python
   def _render_log_entry(self, log: RichLog, entry: dict) -> None:
       entry_type = entry.get("type", "")
       heading = entry.get("heading", "")
       content = entry.get("content", "")

       if entry_type == "response":
           log.write(f"[bold green]Agent Zero:[/bold green]")
           log.write(Markdown(content))  # or plain text
       elif entry_type in ("tool", "code_exe"):
           log.write(f"[dim]── {heading} ──[/dim]")
           if content:
               log.write(f"[dim]{content}[/dim]")
       elif entry_type in ("warning",):
           log.write(f"[yellow]{heading}: {content}[/yellow]")
       elif entry_type in ("error",):
           log.write(f"[red]{heading}: {content}[/red]")
       else:
           if heading or content:
               log.write(f"[dim]{heading}: {content}[/dim]")
   ```
3. Use `self.call_from_thread()` if state_push callback runs in Socket.IO thread

**Acceptance Criteria:**
- [ ] Agent responses appear in real-time as state_push events arrive
- [ ] Response type entries are rendered with agent styling
- [ ] Tool/code entries are rendered dimmed
- [ ] Error entries are rendered in red
- [ ] Chat log auto-scrolls to bottom on new entries
- [ ] No duplicate entries (cursor tracking works)

---

### Task 16: Implement /chats command

**Effort:** 1 hour  
**Dependencies:** Tasks 7, 15  
**Ref:** [spec.md US-5](./spec.md#us-5-list-and-continue-previous-chats), [architecture.md §3.7 - ChatList Widget](./architecture.md#37-chatlist-widget-widgetschat_listpy)

**Description:**  
Implement the `/chats` command to list and switch between chats.

**Steps:**
1. Create `cli/src/agent_zero_cli/screens/chat_list.py`:
   ```python
   from textual.screen import ModalScreen
   from textual.widgets import ListView, ListItem, Static

   class ChatListScreen(ModalScreen[str | None]):
       """Modal showing previous chats. Returns selected context ID or None."""

       BINDINGS = [("escape", "cancel", "Cancel")]

       def __init__(self, contexts: list[dict]):
           super().__init__()
           self.contexts = contexts

       def compose(self) -> ComposeResult:
           yield Static("Select a chat (Esc to cancel):")
           lv = ListView()
           for i, ctx in enumerate(self.contexts):
               name = ctx.get("name", f"Chat {i+1}")
               last_msg = ctx.get("last_message", "")[:50]
               lv.append(ListItem(Static(f"{i+1}. {name} — {last_msg}")))
           yield lv
   ```
2. Handle selection → dismiss with context ID
3. In app, handle `/chats` command:
   ```python
   async def _cmd_chats(self):
       result = await self.push_screen_wait(ChatListScreen(self.contexts))
       if result:
           self.current_context = result
           self.log_cursor = 0
           log = self.query_one("#chat-log", RichLog)
           log.clear()
           await self.client.request_state(result, log_from=0)
   ```

**Acceptance Criteria:**
- [ ] `/chats` opens a modal overlay with chat list
- [ ] Chats show name and last message preview
- [ ] Selecting a chat switches context
- [ ] Chat log is cleared and repopulated with selected chat's history
- [ ] Escape closes the modal without switching
- [ ] Empty chat list shows "No previous chats" message

---

### Task 17: Implement /new, /exit, /help commands

**Effort:** 30 min  
**Dependencies:** Task 14  
**Ref:** [spec.md §5 - Commands](./spec.md#5-commands), [spec.md US-6, US-8](./spec.md#4-user-stories)

**Description:**  
Implement the remaining slash commands.

**Steps:**
1. Implement command dispatcher:
   ```python
   async def _handle_command(self, text: str) -> None:
       cmd = text.split()[0].lower()
       commands = {
           "/chats": self._cmd_chats,
           "/new": self._cmd_new,
           "/exit": self._cmd_exit,
           "/help": self._cmd_help,
       }
       handler = commands.get(cmd)
       if handler:
           await handler()
       else:
           log = self.query_one("#chat-log", RichLog)
           log.write(f"[yellow]Unknown command: {cmd}. Type /help for available commands.[/yellow]")
   ```
2. Implement `/new`:
   - Create new chat via `client.create_chat()`
   - Switch context, clear log, request state
3. Implement `/exit`:
   - Disconnect client
   - `self.exit()`
4. Implement `/help`:
   - Display command table in chat log

**Acceptance Criteria:**
- [ ] `/new` creates a fresh chat and clears the log
- [ ] `/exit` cleanly disconnects and exits
- [ ] `/help` shows all available commands with descriptions
- [ ] Unknown commands show helpful error message

---

## Phase 5: Polish & Edge Cases

### Task 18: Implement reconnection logic

**Effort:** 45 min  
**Dependencies:** Task 10  
**Ref:** [spec.md US-7](./spec.md#us-7-connection-status), [architecture.md §6.1 - Connection Errors](./architecture.md#61-connection-errors)

**Description:**  
Handle connection drops and automatic reconnection.

**Steps:**
1. In the `on_disconnect` callback:
   - Set `self.connected = False`
   - Start reconnection worker
2. Implement reconnection with exponential backoff:
   - Attempts: 1s, 2s, 4s, 8s, 16s
   - On each attempt: try `client.connect_websocket()`
   - On success: re-request state for current context
   - On all failures: show error, offer `/exit`
3. Show reconnection status in header

**Acceptance Criteria:**
- [ ] Connection drop triggers automatic reconnection
- [ ] Backoff increases between attempts
- [ ] Successful reconnection resumes state sync
- [ ] Header shows reconnection status
- [ ] After max retries, user is informed

---

### Task 19: Style and theme the UI

**Effort:** 45 min  
**Dependencies:** Task 9  
**Ref:** [spec.md §7 - UI Layout](./spec.md#7-ui-layout-textual)

**Description:**  
Polish the visual appearance of the CLI.

**Steps:**
1. Expand `app.tcss` with comprehensive styles:
   - Chat log: proper padding, border, background
   - Input: visible focus state, placeholder styling
   - Login screen: centered card layout
   - Chat list modal: bordered overlay with selection highlighting
2. Add color scheme for different log entry types
3. Ensure minimum terminal size handling (show message if too small)
4. Test in common terminals: iTerm2, Terminal.app, Windows Terminal, GNOME Terminal

**Acceptance Criteria:**
- [ ] UI looks clean and professional in default terminal
- [ ] Colors are readable on both dark and light terminal backgrounds
- [ ] Focus states are visible
- [ ] Minimum 80x24 terminal size is handled gracefully

---

### Task 20: Add error handling and edge cases

**Effort:** 45 min  
**Dependencies:** All previous tasks  
**Ref:** [spec.md §8 - Error Handling](./spec.md#8-error-handling)

**Description:**  
Harden the app against common failure modes.

**Steps:**
1. Wrap all API calls in try/except with user-friendly error messages
2. Handle CSRF token expiry (auto-refresh on 403)
3. Handle session expiry (re-prompt login)
4. Handle empty/malformed state_push payloads gracefully
5. Handle keyboard interrupt (Ctrl+C) cleanly — disconnect before exit
6. Handle terminal resize events
7. Add timeout to all HTTP requests (10s default)

**Acceptance Criteria:**
- [ ] No unhandled exceptions crash the app
- [ ] All errors show user-friendly messages in chat log
- [ ] CSRF/session expiry is handled transparently
- [ ] Ctrl+C always exits cleanly
- [ ] Malformed server responses don't crash the app

---

### Task 21: Write README and usage docs

**Effort:** 30 min  
**Dependencies:** All previous tasks  

**Description:**  
Document the CLI for users.

**Steps:**
1. Create `cli/README.md` with:
   - What it is (one paragraph)
   - Installation: `pip install -e cli/` or `pip install agent-zero-cli`
   - Quick start: `agentzero` command
   - Configuration: `.cli-config.json` format
   - Commands: table of all `/commands`
   - Screenshots/recordings (optional)
   - Troubleshooting: common issues
2. Add inline help text that `/help` displays

**Acceptance Criteria:**
- [ ] README covers installation, usage, configuration, and commands
- [ ] A new user can go from zero to chatting by following the README
- [ ] `/help` output matches README command documentation

---

## Task Dependency Graph

```
Phase 1 (Scaffolding)
  T1 ──► T2 ──► T3

Phase 2 (Client)          Phase 3 (UI)
  T4 ──► T5 ──► T6          T9 (parallel with Phase 2)
           │     │            │
           ▼     │            ▼
          T7     │          T10 ◄── T4,T5,T6
           │     │            │
           ▼     ▼            ├──► T11
          T8                  ├──► T12 ◄── T5
                              └──► T13

Phase 4 (Features)
  T14 ◄── T8, T9
    │
    ▼
  T15 ◄── T6
    │
    ├──► T16 ◄── T7
    └──► T17

Phase 5 (Polish)
  T18 ◄── T10
  T19 ◄── T9
  T20 ◄── all
  T21 ◄── all
```

---

## Definition of Done (V1)

- [ ] All 21 tasks completed
- [ ] `pip install -e cli/` works
- [ ] `agentzero` command launches the CLI
- [ ] Can connect to a running Agent Zero instance
- [ ] Can send messages and see streaming responses
- [ ] Can list and switch between chats
- [ ] Can create new chats
- [ ] Handles auth-required instances
- [ ] Handles no-instance-found gracefully
- [ ] Clean exit on Ctrl+C and /exit
- [ ] README documents all features
