from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LongTermMemory:
    """Persistent facts and preferences that matter over time."""

    facts: dict[str, Any] = field(default_factory=dict)

    def remember(self, key: str, value: Any) -> None:
        self.facts[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.facts.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        return dict(self.facts)
