from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProfileMemory:
    """User profile data such as name, preferences, and goals."""

    data: dict[str, Any] = field(default_factory=dict)

    def update(self, **values: Any) -> None:
        self.data.update(values)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        return dict(self.data)
