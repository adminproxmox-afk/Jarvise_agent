from __future__ import annotations

from pathlib import Path

from ai.brain import JarvisBrain
from config import Settings
from tools.registry import ToolRegistry


class DummyEventBus:
    async def publish(self, *args, **kwargs) -> None:
        return None


def test_location_hints_map_common_windows_locations() -> None:
    assert JarvisBrain._apply_location_hint("reports", "create folder on desktop") == "%USERPROFILE%/Desktop/reports"
    assert JarvisBrain._apply_location_hint("reports", "create folder in documents") == "%USERPROFILE%/Documents/reports"
    assert JarvisBrain._apply_location_hint("reports", "create folder in downloads") == "%USERPROFILE%/Downloads/reports"


def test_full_control_relative_paths_use_home_not_workspace(monkeypatch, tmp_path: Path) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr("tools.registry.Path.home", lambda: home_dir)

    settings = Settings(
        raw={
            "security": {"mode": "full_control"},
            "tools": {"allowed_roots": ["."]},
        },
        root_dir=tmp_path,
    )
    registry = ToolRegistry(settings, DummyEventBus())

    resolved = registry._resolve_allowed_path("reports")

    assert resolved == (home_dir / "reports").resolve()
    assert resolved != (tmp_path / "reports").resolve()
