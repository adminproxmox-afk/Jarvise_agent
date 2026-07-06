from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class KnowledgeMemory:
    """Knowledge base for reusable facts and notes."""

    entries: dict[str, Any] = field(default_factory=dict)

    def add(self, key: str, value: Any) -> None:
        self.entries[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.entries.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        return dict(self.entries)
