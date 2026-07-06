from __future__ import annotations

import os
import sys
from pathlib import Path

def _detect_root() -> Path:
    override = os.getenv("JARVIS_ROOT", "").strip()
    if override:
        candidate = Path(override).expanduser().resolve()
        if (candidate / "main.py").exists() and (candidate / "ui").is_dir():
            return candidate

    if getattr(sys, "frozen", False):
        candidates = [
            Path(sys.executable).resolve().parent.parent,
            Path(sys.executable).resolve().parent,
            Path.cwd(),
        ]
    else:
        candidates = [
            Path(__file__).resolve().parents[1],
            Path.cwd(),
        ]

    for candidate in candidates:
        if (candidate / "main.py").exists() and (candidate / "ui").is_dir():
            return candidate

    return Path.cwd().resolve()


ROOT = _detect_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.launcher import DesktopLauncher


if __name__ == "__main__":
    launcher = DesktopLauncher(str(ROOT))
    backend = launcher.start_backend()
    ui = launcher.start_ui()
    print({"backend": {"ok": backend.ok, "message": backend.message, "details": backend.details}, "ui": {"ok": ui.ok, "message": ui.message, "details": ui.details}})
