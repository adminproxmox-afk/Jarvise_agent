from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class AutoHotkeyRunner:
    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("AutoHotkey.exe") or shutil.which("AutoHotkey64.exe")

    @property
    def available(self) -> bool:
        return bool(self.executable)

    def run_script(self, script_path: str | Path) -> subprocess.Popen:
        if not self.executable:
            raise FileNotFoundError("AutoHotkey executable was not found in PATH.")
        path = Path(script_path)
        if not path.exists():
            raise FileNotFoundError(path)
        return subprocess.Popen([self.executable, str(path)])
