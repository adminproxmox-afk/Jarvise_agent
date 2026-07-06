from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil

from config import Settings
from core.events import EventBus

try:
    import winreg
except ImportError:  # pragma: no cover - only available on Windows
    winreg = None


@dataclass(slots=True)
class LaunchResult:
    app_id: str
    name: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class WorkspaceLauncher:
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus

    async def launch_workspace(self, mode: str = "coding") -> list[dict[str, str]]:
        apps = sorted(
            self.settings.get("workspace.apps", []),
            key=lambda item: int(item.get("startup_order", 1000)),
        )
        await self.event_bus.publish("workspace.launch_started", {"mode": mode, "apps": len(apps)}, source="automation")
        results: list[dict[str, str]] = []
        for app in apps:
            result = await self._launch_app_config(app)
            results.append(result.to_dict())
            await self.event_bus.publish("workspace.app_result", result.to_dict(), source="automation")
            await asyncio.sleep(float(app.get("wait_seconds", 0.2)))
        await self.event_bus.publish("workspace.launch_completed", {"mode": mode, "results": results}, source="automation")
        return results

    async def launch_app(self, app_id: str, *, force: bool = False) -> dict[str, str]:
        app = self._find_app(app_id)
        if not app:
            result = LaunchResult(app_id, app_id, "not_configured", "No app with this id in config.")
        else:
            result = await self._launch_app_config(app, force=force)
        await self.event_bus.publish("workspace.app_result", result.to_dict(), source="automation")
        return result.to_dict()

    async def close_distractions(self) -> list[dict[str, str]]:
        targets = set(self.settings.get("focus.close_processes", []))
        closed: list[dict[str, str]] = []
        for proc in psutil.process_iter(["name", "pid"]):
            name = proc.info.get("name")
            if name in targets:
                try:
                    proc.terminate()
                    closed.append({"name": str(name), "status": "terminated"})
                except psutil.Error as exc:
                    closed.append({"name": str(name), "status": "failed", "detail": str(exc)})
        await self.event_bus.publish("workspace.distractions_closed", {"items": closed}, source="automation")
        return closed

    async def _launch_app_config(self, app: dict[str, Any], *, force: bool = False) -> LaunchResult:
        app_id = str(app.get("id", app.get("name", "unknown")))
        name = str(app.get("name", app_id))
        if not app.get("enabled", True) and not force:
            return LaunchResult(app_id, name, "disabled")

        if app.get("skip_if_running", False) and self._is_running(app.get("process_names", [])):
            return LaunchResult(app_id, name, "already_running")

        try:
            await asyncio.to_thread(self._launch_blocking, app)
            return LaunchResult(app_id, name, "launched")
        except FileNotFoundError as exc:
            return LaunchResult(app_id, name, "missing", str(exc))
        except Exception as exc:
            return LaunchResult(app_id, name, "failed", str(exc))

    def _launch_blocking(self, app: dict[str, Any]) -> None:
        app_type = str(app.get("type", "process"))
        command = self._resolve_command(app)
        cwd = self._resolve_cwd(app.get("cwd"))
        args = self._resolve_args(app)

        if app_type == "url":
            webbrowser.open(command)
            return
        if app_type == "uri":
            if hasattr(os, "startfile"):
                os.startfile(command)  # type: ignore[attr-defined]
            else:
                webbrowser.open(command)
            return
        if app_type == "terminal":
            self._launch_terminal(command, cwd)
            return
        if app_type == "shell":
            subprocess.Popen(command, cwd=cwd, shell=True)
            return

        subprocess.Popen([command, *args], cwd=cwd)

    def _resolve_command(self, app: dict[str, Any]) -> str:
        for candidate in app.get("path_candidates", []) or []:
            candidate_path = Path(os.path.expandvars(str(candidate)))
            if candidate_path.exists():
                return str(candidate_path)

        command = str(app.get("command", ""))
        if not command:
            raise FileNotFoundError("Empty command.")

        if Path(command).exists():
            return command

        resolved = shutil.which(command)
        if resolved:
            return resolved
        registry_path = self._resolve_app_path(command)
        if registry_path:
            return registry_path
        return command

    def _resolve_args(self, app: dict[str, Any]) -> list[str]:
        if app.get("args_from") == "chrome_tabs":
            return [str(tab) for tab in self.settings.get("workspace.chrome_tabs", [])]
        return [str(arg) for arg in app.get("args", []) or []]

    def _resolve_cwd(self, raw_cwd: str | None) -> str | None:
        if not raw_cwd:
            return None
        path = Path(os.path.expandvars(raw_cwd))
        if not path.is_absolute():
            path = self.settings.root_dir / path
        return str(path)

    def _launch_terminal(self, command: str, cwd: str | None) -> None:
        if os.name != "nt":
            subprocess.Popen(command, cwd=cwd, shell=True)
            return

        wt = shutil.which("wt")
        if wt:
            args = [wt]
            if cwd:
                args.extend(["-d", cwd])
            args.extend(["powershell", "-NoExit", "-Command", command])
            subprocess.Popen(args)
            return
        subprocess.Popen(["powershell", "-NoExit", "-Command", command], cwd=cwd)

    @staticmethod
    def _resolve_app_path(command: str) -> str | None:
        if os.name != "nt" or winreg is None:
            return None
        names = [command]
        if not command.lower().endswith(".exe"):
            names.append(f"{command}.exe")
        for name in names:
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root, fr"Software\Microsoft\Windows\CurrentVersion\App Paths\{name}") as key:
                        value, _ = winreg.QueryValueEx(key, None)
                        if value and Path(str(value)).exists():
                            return str(value)
                except OSError:
                    continue
        return None

    @staticmethod
    def _is_running(process_names: list[str]) -> bool:
        names = {name.lower() for name in process_names}
        if not names:
            return False
        for proc in psutil.process_iter(["name"]):
            name = proc.info.get("name")
            if name and name.lower() in names:
                return True
        return False

    def _find_app(self, app_id: str) -> dict[str, Any] | None:
        for app in self.settings.get("workspace.apps", []):
            if app.get("id") == app_id:
                return app
        return None
