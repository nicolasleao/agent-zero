# Agent Zero CLI - Product Specification v1

> Version: 1.0  
> Date: 2026-02-06  
> Status: Draft  
> Related: [research.md](./research.md), [architecture.md](./architecture.md), [tasks.md](./tasks.md)

---

## 1. Vision

A lightweight terminal-based chat interface for Agent Zero — think "Claude Code" but for A0. Users can interact with a running Agent Zero instance directly from their terminal without opening a browser.

## 2. Goals (V1)

1. **Simple chat interface** — send messages, see streaming responses in real-time
2. **Connect to existing instance** — works with any running Agent Zero Docker container
3. **Zero-friction setup** — if no instance is found, guide the user through installation
4. **Chat management** — list previous chats, continue existing conversations
5. **Standalone package** — lives in `cli/` folder, independent from the web UI

## 3. Non-Goals (V1)

- File uploads / attachments
- Settings management
- Task scheduler interaction
- Project management
- Multi-model configuration
- Agent subordinate tree visualization
- MCP server management
- Notifications display

---

## 4. User Stories

### US-1: First Launch (No Instance Running)

**As a** new user  
**I want** the CLI to detect that no Agent Zero instance is running  
**So that** I can set one up without leaving the terminal

**Acceptance Criteria:**
- CLI reads `.cli-config.json` for the instance address (default: `localhost:5080`)
- CLI calls `GET /health` on the configured address
- If unreachable, CLI displays a clear message: "No Agent Zero instance found at localhost:5080"
- CLI asks: "Would you like to install Agent Zero? (Y/n)"
- If yes, CLI executes `install.sh` (bundled in the repo) in an interactive sub-process
- After installation completes, CLI retries the health check
- If healthy, CLI proceeds to the chat interface

### US-2: First Launch (Instance Running, No Auth)

**As a** user with a running Agent Zero instance (no auth configured)  
**I want** the CLI to connect automatically  
**So that** I can start chatting immediately

**Acceptance Criteria:**
- CLI calls `GET /health` → success
- CLI skips login (no auth configured)
- CLI obtains CSRF token via `GET /csrf_token`
- CLI establishes Socket.IO connection to `/state_sync` namespace
- CLI sends `state_request` to initialize state sync
- CLI displays the chat interface with an input prompt
- A new chat context is created automatically

### US-3: First Launch (Instance Running, Auth Required)

**As a** user with a running Agent Zero instance (auth configured)  
**I want** the CLI to prompt me for credentials  
**So that** I can authenticate and start chatting

**Acceptance Criteria:**
- CLI calls `GET /health` → success
- CLI attempts to access a protected endpoint → gets redirected to login
- CLI prompts for username and password (password input is masked)
- CLI sends `POST /login` with credentials
- On success, CLI stores session cookie and proceeds to chat
- On failure, CLI shows error and re-prompts (max 3 attempts)
- Credentials are NOT stored on disk (session cookie is ephemeral)

### US-4: Send a Message

**As a** user in the chat interface  
**I want** to type a message and see the agent's response stream in real-time  
**So that** I get immediate feedback as the agent works

**Acceptance Criteria:**
- User types a message in the input field and presses Enter
- CLI sends `POST /message_async` with `{text, context}`
- CLI displays a "thinking..." indicator
- As `state_push` events arrive with new log entries, CLI renders them in real-time
- Different log types are visually distinguished:
  - `response` → agent's final response (rendered as markdown)
  - `tool` → tool usage (shown as collapsible/dimmed)
  - `code_exe` → code execution output (shown in code block style)
  - `info` → informational messages (dimmed)
- When `log_progress_active` becomes `false`, the thinking indicator is removed
- Input field is re-enabled for the next message

### US-5: List and Continue Previous Chats

**As a** user  
**I want** to see my previous chats and continue any of them  
**So that** I can resume work from where I left off

**Acceptance Criteria:**
- User types `/chats` in the input field
- CLI displays a list of previous chats with:
  - Chat name (or first message preview)
  - Created date
  - Last message date
- User can select a chat (by number or arrow keys)
- CLI switches to the selected chat context
- CLI sends a new `state_request` with the selected context ID
- Previous messages/logs are displayed
- User can send new messages in the continued chat

### US-6: Exit the CLI

**As a** user  
**I want** to cleanly exit the CLI  
**So that** all connections are properly closed

**Acceptance Criteria:**
- User types `/exit` or presses `Ctrl+C`
- CLI disconnects Socket.IO connection
- CLI closes HTTP session
- CLI exits with code 0
- The Agent Zero instance continues running (CLI is just a client)

### US-7: Connection Status

**As a** user  
**I want** to see the connection status at all times  
**So that** I know if the CLI is connected to the Agent Zero instance

**Acceptance Criteria:**
- Header/status bar shows: connected (green) / disconnected (red) / reconnecting (yellow)
- If connection drops, CLI attempts to reconnect automatically
- If reconnection fails after 3 attempts, CLI shows error and offers to retry or exit
- When reconnected, CLI resumes state sync from where it left off

### US-8: New Chat

**As a** user  
**I want** to start a fresh chat  
**So that** I can begin a new conversation without previous context

**Acceptance Criteria:**
- User types `/new` in the input field
- CLI calls `POST /chat_create` to create a new context
- CLI switches to the new context
- Chat log is cleared
- Input is ready for the first message

---

## 5. Commands

| Command | Description |
|---------|------------|
| `/chats` | List previous chats and select one to continue |
| `/new` | Start a new chat |
| `/exit` | Exit the CLI |
| `/help` | Show available commands |

---

## 6. Configuration

### `.cli-config.json`

```json
{
  "instance_url": "http://localhost:5080",
  "theme": "dark"
}
```

- `instance_url`: URL of the running Agent Zero instance (default: `http://localhost:5080`)
- `theme`: Color theme (future use, default: `dark`)

**Load Order:**

1. `.cli-config.json` in the current working directory
2. `~/.agentzero/.cli-config.json`
3. Built-in defaults if no file is found

The repo includes a sample `.cli-config.json` in `cli/` as a template; it is not required at runtime.

---

## 7. UI Layout (Textual)

```
┌─────────────────────────────────────────────────┐
│  Agent Zero CLI v1.0          ● Connected       │  ← Header
├─────────────────────────────────────────────────┤
│                                                 │
│  You: How do I compress a PDF file?             │
│                                                 │
│  Agent Zero:                                    │
│  ┌─ Tool: code_execution_tool ──────────────┐   │
│  │ runtime: terminal                        │   │  ← Chat Log
│  │ code: apt-get install ghostscript        │   │     (RichLog)
│  └──────────────────────────────────────────┘   │
│                                                 │
│  Here's how to compress a PDF using            │
│  Ghostscript...                                 │
│                                                 │
│  ⣾ Agent is thinking...                         │  ← Progress
├─────────────────────────────────────────────────┤
│  > Type a message... (/help for commands)       │  ← Input
└─────────────────────────────────────────────────┘
│  Ctrl+C: Exit  |  /help: Commands               │  ← Footer
└─────────────────────────────────────────────────┘
```

---

## 8. Error Handling

| Scenario | Behavior |
|----------|----------|
| Instance unreachable on startup | Offer to run install.sh |
| Auth fails (wrong credentials) | Re-prompt up to 3 times, then exit |
| Connection drops mid-chat | Auto-reconnect with backoff, show status |
| CSRF token expired | Auto-refresh token, retry request |
| Message send fails | Show error, allow retry |
| Unknown `/command` | Show "Unknown command. Type /help for available commands." |

---

## 9. Success Metrics

- User can go from `bash install.sh` to chatting in under 2 minutes
- Streaming response latency is imperceptible vs web UI
- CLI works on Linux, macOS, and WSL2
- Zero configuration needed for default setup
