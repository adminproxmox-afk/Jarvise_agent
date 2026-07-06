from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProjectMemory:
    """Tracks active projects and their metadata."""

    projects: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(self, name: str, metadata: dict[str, Any] | None = None) -> None:
        self.projects[name] = {**(metadata or {})}

    def get(self, name: str, default: Any = None) -> Any:
        return self.projects.get(name, default)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return dict(self.projects)
