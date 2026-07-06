from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ShortTermMemory:
    """Recent conversation turn buffer."""

    turns: list[dict[str, Any]] = field(default_factory=list)

    def add(self, role: str, content: str) -> None:
        self.turns.append({"role": role, "content": content})
        if len(self.turns) > 12:
            self.turns = self.turns[-12:]

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self.turns)
