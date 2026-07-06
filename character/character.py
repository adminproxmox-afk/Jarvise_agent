from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CharacterProfile:
    name: str = "Jarvise"
    style: str = "helpful, concise, calm"
    personality: str = "warm, proactive, reliable"
    rules: list[str] = field(default_factory=lambda: ["Be helpful.", "Respect user privacy.", "Prefer local tools when available."])
    goals: list[str] = field(default_factory=lambda: ["Assist the user efficiently.", "Learn preferences over time."])


class Character:
    """Personality layer independent from the LLM provider."""

    def __init__(self, profile: CharacterProfile | None = None) -> None:
        self.profile = profile or CharacterProfile()

    def build_system_prompt(self) -> str:
        return (
            f"You are {self.profile.name}. "
            f"Style: {self.profile.style}. "
            f"Personality: {self.profile.personality}. "
            f"Rules: {'; '.join(self.profile.rules)}. "
            f"Goals: {'; '.join(self.profile.goals)}."
        )

    def adapt_response(self, response: str, *, context: dict[str, Any] | None = None) -> str:
        if not response:
            return response
        if context and context.get("needs_summary"):
            return f"Short summary: {response}"
        return response
