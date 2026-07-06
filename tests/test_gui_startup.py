from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from gui.launcher import DesktopLauncher


def test_desktop_launcher_creates_result_objects() -> None:
    launcher = DesktopLauncher(".")
    result = launcher.start_backend()
    assert result.ok in {True, False}
    assert isinstance(result.message, str)


def test_desktop_launcher_prefers_override_python(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_PYTHON", "C:/Python/python.exe")
    launcher = DesktopLauncher(".")
    assert launcher._python_executable() == "C:/Python/python.exe"


def test_desktop_launcher_uses_venv_python_when_frozen(monkeypatch, tmp_path: Path) -> None:
    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    monkeypatch.delenv("JARVIS_PYTHON", raising=False)
    monkeypatch.setattr("gui.launcher.sys.frozen", True, raising=False)
    launcher = DesktopLauncher(str(tmp_path))
    assert launcher._python_executable() == str(venv_python)


def test_start_desktop_detects_project_root_from_frozen_executable(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("", encoding="utf-8")
    (project_root / "ui").mkdir()

    fake_executable = project_root / "build" / "jarvise_launcher.exe"
    fake_executable.parent.mkdir()
    fake_executable.write_text("", encoding="utf-8")

    monkeypatch.setenv("JARVIS_ROOT", "")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_executable), raising=False)

    module = _load_start_desktop_module()

    assert module.ROOT == project_root


def test_start_desktop_respects_root_override(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("", encoding="utf-8")
    (project_root / "ui").mkdir()

    monkeypatch.setenv("JARVIS_ROOT", str(project_root))
    module = _load_start_desktop_module()

    assert module.ROOT == project_root


def _load_start_desktop_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "start_desktop.py"
    spec = importlib.util.spec_from_file_location("start_desktop_for_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
