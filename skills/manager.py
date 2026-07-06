from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Skill:
    name: str
    description: str = ""
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


class SkillManager:
    """Selects a skill based on the user request without executing it."""

    def __init__(self) -> None:
        self._skills = [
            Skill("coding", "Handles project creation, coding tasks, and developer workflows"),
            Skill("internet", "Handles search, documentation, web lookups"),
            Skill("voice", "Handles voice, music, and speech-related requests"),
            Skill("files", "Handles file and folder operations"),
        ]

    def select_skill(self, request: str) -> Skill | None:
        normalized = request.strip().lower()
        if any(keyword in normalized for keyword in ("project", "python", "code", "код", "проект")):
            return next(skill for skill in self._skills if skill.name == "coding")
        if any(keyword in normalized for keyword in ("internet", "search", "wiki", "документац", "інтернет")):
            return next(skill for skill in self._skills if skill.name == "internet")
        if any(keyword in normalized for keyword in ("voice", "music", "голос", "музику", "музыку")):
            return next(skill for skill in self._skills if skill.name == "voice")
        if any(keyword in normalized for keyword in ("file", "folder", "файл", "папка")):
            return next(skill for skill in self._skills if skill.name == "files")
        return None
