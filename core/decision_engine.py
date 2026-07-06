from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Decision:
    needs_memory: bool = False
    needs_internet: bool = False
    needs_skill: bool = False
    needs_planning: bool = False
    needs_llm: bool = True
    skill: str | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class DecisionEngine:
    """Classifies a user request into high-level execution needs without executing anything."""

    def decide(self, text: str) -> Decision:
        normalized = text.strip().lower()

        if any(keyword in normalized for keyword in ("пам'ять", "память", "remember", "запам'ятай", "запомни", "memory")):
            return Decision(needs_memory=True, reason="memory request", metadata={"text": text})

        if any(keyword in normalized for keyword in ("погода", "weather", "температура", "temperature", "прогноз", "forecast", "дощ", "rain", "сніг", "snow", "вітер", "wind")):
            return Decision(needs_internet=True, needs_skill=True, skill="internet", reason="weather query", metadata={"text": text})

        if any(keyword in normalized for keyword in ("новини", "новости", "news", "latest", "breaking", "останні новини", "свіжі новини", "свежие новости")):
            return Decision(needs_internet=True, needs_skill=True, skill="internet", reason="news query", metadata={"text": text})

        if "?" in normalized or any(normalized.startswith(word) for word in ("хто", "що", "яка", "якой", "де", "коли", "чому", "як", "who", "what", "where", "when", "why", "how")):
            if not any(keyword in normalized for keyword in ("проект", "project", "python", "code", "файл", "file", "папка", "folder", "github", "git", "телеграм", "telegram", "browser", "браузер", "music", "голос", "tts", "stt")):
                return Decision(needs_internet=True, needs_skill=True, skill="internet", reason="general question", metadata={"text": text})

        if any(keyword in normalized for keyword in ("інтернет", "internet", "web", "search", "google", "wiki", "документац", "documentation")):
            return Decision(needs_internet=True, needs_skill=True, skill="internet", reason="internet request", metadata={"text": text})

        if any(
            keyword in normalized
            for keyword in (
                "пошукай",
                "пошук",
                "знайди",
                "найди",
                "look up",
                "lookup",
                "search for",
                "what is",
                "who is",
                "how to",
                "що таке",
                "хто такий",
                "скільки",
            )
        ):
            return Decision(needs_internet=True, needs_skill=True, skill="internet", reason="search request", metadata={"text": text})

        if any(keyword in normalized for keyword in ("проект", "project", "python", "code", "файл", "file", "папка", "folder", "github", "git")):
            return Decision(needs_skill=True, needs_planning=True, skill="coding", reason="project or coding request", metadata={"text": text})

        if any(keyword in normalized for keyword in ("голос", "voice", "tts", "stt", "музику", "music", "play")):
            return Decision(needs_skill=True, skill="voice", reason="voice or music request", metadata={"text": text})

        if any(keyword in normalized for keyword in ("план", "plan", "створи", "create", "зроби", "make")):
            return Decision(needs_planning=True, needs_skill=True, skill="coding", reason="planning request", metadata={"text": text})

        return Decision(reason="general conversation", metadata={"text": text})
