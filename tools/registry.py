from __future__ import annotations

import asyncio
import inspect
import os
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from config import Settings
from core.events import EventBus
from core.security import AccessMode, SecurityPolicy
from plugins.manager import PluginManager


class TelegramSender(Protocol):
    def status(self) -> dict[str, Any]:
        ...

    async def send_message(self, text: str) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class ToolDescriptor:
    name: str
    title: str
    category: str
    enabled: bool
    access: str
    description: str
    actions: list[str]


class ToolRegistry:
    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        *,
        telegram: TelegramSender | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.telegram = telegram
        self.plugins = PluginManager(settings.root_dir / "plugins")
        self.security = SecurityPolicy(
            AccessMode(str(settings.get("security.mode", settings.get("tools.access_mode", "developer"))))
        )
        self._tools = [
            ToolDescriptor(
                "filesystem",
                "Filesystem",
                "system",
                True,
                "developer",
                "Read, write and organize files inside allowed roots",
                ["list", "read", "write", "mkdir", "delete"],
            ),
            ToolDescriptor("terminal", "Terminal", "system", True, "developer", "Run PowerShell/Bash/CMD commands", ["run"]),
            ToolDescriptor("browser", "Browser", "automation", True, "developer", "Open URLs in the default browser", ["open"]),
            ToolDescriptor("docker", "Docker", "devops", True, "developer", "Control Docker and compose workloads", ["status", "run", "compose"]),
            ToolDescriptor("git", "Git", "devops", True, "developer", "Inspect and publish repository state", ["status", "pull", "commit", "push"]),
            ToolDescriptor("telegram", "Telegram", "integration", True, "developer", "Send notifications and receive commands", ["status", "send"]),
            ToolDescriptor("vscode", "VS Code", "desktop", True, "developer", "Open workspaces and files in VS Code", ["open"]),
            ToolDescriptor("custom_plugins", "Custom Plugins", "extension", True, "developer", "Load external JARVIS plugins", ["list", "execute"]),
        ]

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "title": tool.title,
                "category": tool.category,
                "enabled": tool.enabled,
                "access": tool.access,
                "description": tool.description,
                "actions": tool.actions,
            }
            for tool in self._tools
        ]

    async def execute(self, tool: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        decision = self.security.decide(tool, action, str(payload.get("command", "")))
        if not decision.allowed:
            await self.event_bus.publish(
                "security.blocked",
                {"tool": tool, "action": action, "reason": decision.reason},
                source="security",
                level="warning",
            )
            return {"ok": False, "blocked": True, "reason": decision.reason}
        if decision.requires_confirmation and not payload.get("confirmed"):
            await self.event_bus.publish(
                "security.confirmation_required",
                {"tool": tool, "action": action, "reason": decision.reason},
                source="security",
                level="warning",
            )
            return {
                "ok": False,
                "blocked": True,
                "requires_confirmation": True,
                "reason": decision.reason,
            }

        if tool == "filesystem" and action == "list":
            return await self._list_files(payload)
        if tool == "filesystem" and action == "read":
            return await self._read_file(payload)
        if tool == "filesystem" and action == "write":
            return await self._write_file(payload)
        if tool == "filesystem" and action == "mkdir":
            return await self._make_directory(payload)
        if tool == "filesystem" and action == "delete":
            return await self._delete_path(payload)
        if tool == "terminal" and action == "run":
            return await self._run_terminal(payload)
        if tool == "browser" and action == "open":
            return await self._open_browser(payload)
        if tool == "git" and action == "status":
            return await self._run_exec(["git", "status", "--short"], cwd=payload.get("cwd"))
        if tool == "git" and action == "pull":
            return await self._run_exec(["git", "pull", "--ff-only"], cwd=payload.get("cwd"), timeout=120)
        if tool == "git" and action == "commit":
            return await self._git_commit(payload)
        if tool == "git" and action == "push":
            return await self._run_exec(["git", "push"], cwd=payload.get("cwd"), timeout=120)
        if tool == "docker" and action == "status":
            return await self._run_exec(["docker", "ps"], cwd=payload.get("cwd"))
        if tool == "docker" and action == "run":
            return await self._docker_run(payload)
        if tool == "docker" and action == "compose":
            return await self._docker_compose(payload)
        if tool == "telegram" and action == "status":
            return {"ok": True, "status": self.telegram.status() if self.telegram else {"enabled": False}}
        if tool == "telegram" and action == "send":
            return await self._telegram_send(payload)
        if tool == "vscode" and action == "open":
            return await self._open_vscode(payload)
        if tool == "custom_plugins" and action == "list":
            return await self._list_plugins()
        if tool == "custom_plugins" and action == "execute":
            return await self._execute_plugin(payload)
        return {"ok": False, "reason": "tool_action_not_implemented", "tool": tool, "action": action}

    async def _list_files(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            path = self._resolve_allowed_path(payload.get("path") or ".")
        except PermissionError as exc:
            return {"ok": False, "reason": "path_not_allowed", "detail": str(exc)}
        if not path.exists() or not path.is_dir():
            return {"ok": False, "reason": "directory_not_found", "path": str(path)}
        entries = [
            {"name": child.name, "path": str(child), "type": "directory" if child.is_dir() else "file"}
            for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))[:200]
        ]
        return {"ok": True, "path": str(path), "entries": entries}

    async def _read_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            path = self._resolve_allowed_path(payload.get("path") or "")
        except PermissionError as exc:
            return {"ok": False, "reason": "path_not_allowed", "detail": str(exc)}
        if not path.exists() or not path.is_file():
            return {"ok": False, "reason": "file_not_found", "path": str(path)}
        max_bytes = int(payload.get("max_bytes", 200_000))
        data = await asyncio.to_thread(path.read_bytes)
        truncated = len(data) > max_bytes
        content = data[:max_bytes].decode(str(payload.get("encoding", "utf-8")), errors="replace")
        return {"ok": True, "path": str(path), "content": content, "truncated": truncated, "bytes": len(data)}

    async def _write_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            path = self._resolve_allowed_path(payload.get("path") or "")
        except PermissionError as exc:
            return {"ok": False, "reason": "path_not_allowed", "detail": str(exc)}
        content = str(payload.get("content", ""))
        append = bool(payload.get("append", False))
        if payload.get("create_parents", True):
            await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        encoding = str(payload.get("encoding", "utf-8"))
        if append:
            await asyncio.to_thread(self._append_text, path, content, encoding)
        else:
            await asyncio.to_thread(path.write_text, content, encoding=encoding)
        await self.event_bus.publish(
            "tool.filesystem_written",
            {"path": str(path), "bytes": len(content.encode(encoding, errors="replace")), "append": append},
            source="tools",
        )
        return {"ok": True, "path": str(path), "mode": "append" if append else "write"}

    async def _make_directory(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            path = self._resolve_allowed_path(payload.get("path") or "")
        except PermissionError as exc:
            return {"ok": False, "reason": "path_not_allowed", "detail": str(exc)}
        await asyncio.to_thread(path.mkdir, parents=bool(payload.get("parents", True)), exist_ok=bool(payload.get("exist_ok", True)))
        return {"ok": True, "path": str(path)}

    async def _delete_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            path = self._resolve_allowed_path(payload.get("path") or "")
        except PermissionError as exc:
            return {"ok": False, "reason": "path_not_allowed", "detail": str(exc)}
        if not path.exists():
            return {"ok": False, "reason": "path_not_found", "path": str(path)}
        if path.is_dir():
            if not payload.get("recursive"):
                return {"ok": False, "reason": "recursive_required_for_directory", "path": str(path)}
            await asyncio.to_thread(shutil.rmtree, path)
        else:
            await asyncio.to_thread(path.unlink)
        await self.event_bus.publish("tool.filesystem_deleted", {"path": str(path)}, source="tools", level="warning")
        return {"ok": True, "path": str(path)}

    async def _run_terminal(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = str(payload.get("command", "")).strip()
        if not command:
            return {"ok": False, "reason": "missing_command"}
        cwd = self._resolve_cwd(payload.get("cwd"))
        timeout = float(payload.get("timeout", 60))
        await self.event_bus.publish("tool.started", {"tool": "terminal", "command": command}, source="tools")
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                cwd=str(cwd),
                shell=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            result = {
                "ok": False,
                "returncode": None,
                "stdout": self._decode_output(exc.stdout),
                "stderr": self._decode_output(exc.stderr) or "Command timed out.",
                "timeout": True,
            }
            await self.event_bus.publish("tool.completed", {"tool": "terminal", **result}, source="tools", level="warning")
            return result
        result = {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": self._decode_output(completed.stdout)[-6000:],
            "stderr": self._decode_output(completed.stderr)[-6000:],
        }
        await self.event_bus.publish("tool.completed", {"tool": "terminal", **result}, source="tools")
        return result

    async def _open_browser(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = str(payload.get("url") or payload.get("target") or "").strip()
        if not url:
            return {"ok": False, "reason": "missing_url"}
        opened = await asyncio.to_thread(webbrowser.open, url)
        await self.event_bus.publish("tool.browser_opened", {"url": url, "opened": opened}, source="tools")
        return {"ok": bool(opened), "url": url}

    async def _git_commit(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = str(payload.get("message") or "").strip()
        if not message:
            return {"ok": False, "reason": "missing_commit_message"}
        raw_paths = payload.get("paths") or ["."]
        paths = [str(item) for item in (raw_paths if isinstance(raw_paths, list) else [raw_paths])]
        add_result = await self._run_exec(["git", "add", "--", *paths], cwd=payload.get("cwd"), timeout=60)
        if not add_result.get("ok"):
            return {"ok": False, "stage": add_result}
        commit_result = await self._run_exec(["git", "commit", "-m", message], cwd=payload.get("cwd"), timeout=120)
        return {"ok": bool(commit_result.get("ok")), "stage": add_result, "commit": commit_result}

    async def _docker_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        args = payload.get("args")
        if isinstance(args, list) and args:
            return await self._run_exec(["docker", *[str(item) for item in args]], cwd=payload.get("cwd"), timeout=int(payload.get("timeout", 300)))
        command = str(payload.get("command") or "").strip()
        if command:
            return await self._run_terminal({"command": command, "cwd": payload.get("cwd"), "timeout": payload.get("timeout", 300)})
        return {"ok": False, "reason": "missing_docker_args"}

    async def _docker_compose(self, payload: dict[str, Any]) -> dict[str, Any]:
        args = payload.get("args") or ["ps"]
        if not isinstance(args, list):
            return {"ok": False, "reason": "args_must_be_list"}
        return await self._run_exec(["docker", "compose", *[str(item) for item in args]], cwd=payload.get("cwd"), timeout=int(payload.get("timeout", 300)))

    async def _telegram_send(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        if not text:
            return {"ok": False, "reason": "missing_text"}
        if not self.telegram:
            return {"ok": False, "reason": "telegram_service_unavailable"}
        return await self.telegram.send_message(text)

    async def _open_vscode(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = self._resolve_allowed_path(payload.get("path") or ".")
        code = shutil.which("code") or shutil.which("code.cmd")
        if not code:
            return {"ok": False, "reason": "vscode_cli_not_found"}
        return await self._run_exec([code, str(target)], cwd=payload.get("cwd"), timeout=10)

    async def _list_plugins(self) -> dict[str, Any]:
        plugins = [
            {"name": path.parent.name, "path": str(path)}
            for path in self.plugins.discover()
        ]
        return {"ok": True, "plugins": plugins}

    async def _execute_plugin(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            return {"ok": False, "reason": "missing_plugin_name"}
        loaded = self.plugins.load_all()
        plugin = next((item.instance for item in loaded if item.name == name), None)
        if plugin is None:
            return {"ok": False, "reason": "plugin_not_found", "name": name}
        execute = getattr(plugin, "execute", None)
        if not callable(execute):
            return {"ok": False, "reason": "plugin_has_no_execute", "name": name}
        result = execute(payload.get("payload", {}))
        if inspect.isawaitable(result):
            result = await result
        return {"ok": True, "plugin": name, "result": result}

    async def _run_exec(
        self,
        args: list[str],
        *,
        cwd: object | None = None,
        timeout: int | float = 60,
    ) -> dict[str, Any]:
        resolved_cwd = self._resolve_cwd(cwd)
        display = " ".join(args)
        await self.event_bus.publish("tool.started", {"tool": "process", "command": display}, source="tools")
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                args,
                cwd=str(resolved_cwd),
                capture_output=True,
                timeout=float(timeout),
            )
        except FileNotFoundError as exc:
            return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}
        except subprocess.TimeoutExpired as exc:
            result = {
                "ok": False,
                "returncode": None,
                "stdout": self._decode_output(exc.stdout),
                "stderr": self._decode_output(exc.stderr) or "Command timed out.",
                "timeout": True,
            }
            await self.event_bus.publish("tool.completed", {"tool": "process", **result}, source="tools", level="warning")
            return result
        result = {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": self._decode_output(completed.stdout)[-6000:],
            "stderr": self._decode_output(completed.stderr)[-6000:],
        }
        await self.event_bus.publish("tool.completed", {"tool": "process", **result}, source="tools")
        return result

    def _resolve_cwd(self, value: object | None) -> Path:
        try:
            return self._resolve_allowed_path(value or ".")
        except PermissionError:
            return self.settings.root_dir

    def _resolve_allowed_path(self, raw: object) -> Path:
        if raw is None or str(raw).strip() == "":
            raise PermissionError("Empty path.")
        path = Path(os.path.expanduser(os.path.expandvars(str(raw))))
        if not path.is_absolute():
            if self.security.mode == AccessMode.FULL_CONTROL:
                path = Path.home() / path
            else:
                path = self.settings.root_dir / path
        resolved = path.resolve(strict=False)
        if self.security.mode == AccessMode.FULL_CONTROL:
            return resolved
        allowed_roots = self._allowed_roots()
        if any(self._is_relative_to(resolved, root) for root in allowed_roots):
            return resolved
        roots = ", ".join(str(root) for root in allowed_roots)
        raise PermissionError(f"{resolved} is outside allowed roots: {roots}")

    def _allowed_roots(self) -> list[Path]:
        configured = self.settings.get("tools.allowed_roots", ["."])
        raw_roots = configured if isinstance(configured, list) else [configured]
        roots: list[Path] = []
        for raw in raw_roots:
            path = Path(str(raw))
            if not path.is_absolute():
                path = self.settings.root_dir / path
            roots.append(path.resolve(strict=False))
        return roots or [self.settings.root_dir.resolve(strict=False)]

    @staticmethod
    def _append_text(path: Path, content: str, encoding: str) -> None:
        with path.open("a", encoding=encoding) as handle:
            handle.write(content)

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _decode_output(value: bytes | str | None) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value[-6000:]
        return value.decode(errors="replace")[-6000:]
