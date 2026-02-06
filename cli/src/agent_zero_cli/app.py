from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, RichLog

from agent_zero_cli.client import A0Client
from agent_zero_cli.config import CLIConfig, load_config
from agent_zero_cli.screens.login import LoginScreen


class AgentZeroCLI(App):
    """Agent Zero CLI - Terminal Chat Interface."""

    CSS_PATH = "styles/app.tcss"
    TITLE = "Agent Zero CLI"
    BINDINGS = [
        Binding("ctrl+c", "quit", "Exit", show=True),
    ]

    connected = reactive(False)
    agent_active = reactive(False)

    def __init__(self, config: CLIConfig | None = None) -> None:
        super().__init__()
        self.config = config or load_config()
        self.client = A0Client(self.config.instance_url)
        self.current_context: str | None = None
        self.log_cursor = 0
        self.log_guid: str | None = None
        self._install_prompt_future: asyncio.Future[bool] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat-log", wrap=True, highlight=True, markup=True)
        yield Input(placeholder="Type a message... (/help for commands)", id="message-input")
        yield Footer()

    async def on_mount(self) -> None:
        input_widget = self.query_one("#message-input", Input)
        input_widget.disabled = True
        input_widget.focus()
        self._refresh_subtitle()
        self.run_worker(self._startup(), exclusive=True, name="startup")

    def watch_connected(self, connected: bool) -> None:
        self._refresh_subtitle()

    def watch_agent_active(self, agent_active: bool) -> None:
        self._refresh_subtitle()

    def _refresh_subtitle(self) -> None:
        if self.agent_active:
            self.sub_title = "Agent thinking..."
        elif self.connected:
            self.sub_title = "Connected"
        else:
            self.sub_title = "Disconnected"

    async def _startup(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        input_widget = self.query_one("#message-input", Input)

        log.write("[dim]Connecting to Agent Zero...[/dim]")
        if not await self.client.check_health():
            log.write(f"[red]No Agent Zero instance found at {self.config.instance_url}[/red]")
            should_install = await self._prompt_install(log, input_widget)
            if should_install:
                await self._run_install(log)
                if not await self.client.check_health():
                    log.write("[red]Agent Zero is still unreachable after install.[/red]")
                    input_widget.disabled = True
                    return
            else:
                log.write("[dim]Update .cli-config.json or start Agent Zero manually.[/dim]")
                input_widget.disabled = True
                return

        if await self.client.needs_auth():
            login_ok = await self.push_screen_wait(LoginScreen(self.client))
            if not login_ok:
                log.write("[red]Authentication failed. Exiting.[/red]")
                self.exit(return_code=1)
                return

        self.client.on_state_push = self._handle_state_push
        self.client.on_connect = lambda: self.call_from_thread(self._set_connected, True)
        self.client.on_disconnect = lambda: self.call_from_thread(self._set_connected, False)

        await self.client.connect_websocket()
        self.current_context = await self.client.create_chat()
        await self.client.request_state(self.current_context)
        log.write("[green]Connected to Agent Zero.[/green]")
        input_widget.disabled = False

    async def _prompt_install(self, log: RichLog, input_widget: Input) -> bool:
        log.write("[dim]Would you like to install Agent Zero? (y/n)[/dim]")
        loop = asyncio.get_running_loop()
        self._install_prompt_future = loop.create_future()
        input_widget.disabled = False
        input_widget.focus()
        result = await self._install_prompt_future
        self._install_prompt_future = None
        return result

    async def _run_install(self, log: RichLog) -> None:
        log.write("[dim]Launching install.sh...[/dim]")
        install_path = self._install_script_path()
        with self.suspend():
            subprocess.run(["/bin/bash", str(install_path)], check=False)
        log.write("[dim]Install finished. Retrying connection...[/dim]")

    def _install_script_path(self) -> Path:
        return Path(__file__).resolve().parents[3] / "install.sh"

    def _set_connected(self, value: bool) -> None:
        self.connected = value

    def _handle_state_push(self, data: dict[str, Any]) -> None:
        self.call_from_thread(self._handle_state_push_ui, data)

    def _handle_state_push_ui(self, data: dict[str, Any]) -> None:
        payload = data.get("data", data)
        snapshot = payload.get("snapshot", payload)
        log_guid = snapshot.get("log_guid")
        if log_guid and log_guid != self.log_guid:
            self.log_guid = log_guid
            self.log_cursor = 0
        log_version = snapshot.get("log_version")
        if isinstance(log_version, int):
            self.log_cursor = log_version
        self.agent_active = bool(snapshot.get("log_progress_active", False))
        input_widget = self.query_one("#message-input", Input)
        input_widget.disabled = self.agent_active

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip().lower()
        event.input.value = ""
        if self._install_prompt_future and not self._install_prompt_future.done():
            if text in {"y", "yes"}:
                self._install_prompt_future.set_result(True)
            elif text in {"n", "no"}:
                self._install_prompt_future.set_result(False)
            else:
                log = self.query_one("#chat-log", RichLog)
                log.write("[yellow]Please answer y or n.[/yellow]")
            return
