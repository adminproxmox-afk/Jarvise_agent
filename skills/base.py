from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SkillContext:
    request: str
    memory: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillResult:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class Skill(ABC):
    name: str = "skill"

    @abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError
