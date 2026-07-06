from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LaunchResult:
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class DesktopLauncher:
    """Small launcher service for desktop startup without needing PowerShell."""

    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = root_dir or os.getcwd()

    def start_backend(self) -> LaunchResult:
        python_executable = self._python_executable()
        if not python_executable:
            return LaunchResult(
                ok=False,
                message="No Python interpreter found for backend startup",
                details={"cwd": self.root_dir},
            )
        try:
            subprocess.Popen(
                [python_executable, "main.py"],
                cwd=self.root_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
            )
            return LaunchResult(
                ok=True,
                message="Backend launched",
                details={"cwd": self.root_dir, "python": python_executable},
            )
        except Exception as exc:  # pragma: no cover - defensive path
            return LaunchResult(ok=False, message=str(exc), details={"cwd": self.root_dir})

    def _python_executable(self) -> str | None:
        override = os.getenv("JARVIS_PYTHON", "").strip()
        if override:
            return override

        if getattr(sys, "frozen", False):
            venv_python = Path(self.root_dir) / ".venv" / "Scripts" / "python.exe"
            if venv_python.exists():
                return str(venv_python)

            py_launcher = shutil.which("py")
            if py_launcher:
                return py_launcher

            return None

        return sys.executable

    def start_ui(self) -> LaunchResult:
        if os.name != "nt":
            return LaunchResult(ok=False, message="Desktop UI launch is currently Windows-specific")
        ui_dir = os.path.join(self.root_dir, "ui")
        if not os.path.isdir(ui_dir):
            return LaunchResult(ok=False, message="UI directory not found", details={"cwd": ui_dir})
        npm_cmd = shutil.which("npm")
        if not npm_cmd:
            return LaunchResult(ok=False, message="npm is not available on PATH", details={"cwd": ui_dir})
        try:
            subprocess.Popen(
                [npm_cmd, "run", "dev"],
                cwd=ui_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
            )
            return LaunchResult(ok=True, message="UI launcher started", details={"cwd": ui_dir})
        except Exception as exc:  # pragma: no cover - defensive path
            return LaunchResult(ok=False, message=str(exc), details={"cwd": ui_dir})
