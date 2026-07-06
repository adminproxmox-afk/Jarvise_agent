from __future__ import annotations

from api.app import create_app
from pathlib import Path


def test_expected_architecture_layout_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = [
        root / "brain",
        root / "providers",
        root / "memory",
        root / "planner",
        root / "character",
        root / "skills",
        root / "voice",
        root / "internet",
        root / "automation",
        root / "plugins",
        root / "api",
        root / "ui",
        root / "config",
    ]

    for path in expected:
        assert path.exists(), f"Expected architecture directory missing: {path}"


def test_modular_orchestrator_route_is_exposed() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/modular/command" in paths
