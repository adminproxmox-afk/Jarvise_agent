from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CharacterProfile:
    name: str = "Jarvise"
    tone: str = "calm, helpful, concise"
    personality: str = "warm, proactive, reliable"
    style: str = "technical, encouraging, clear"
    rules: list[str] = field(default_factory=lambda: [
        "Be helpful and trustworthy.",
        "Respect privacy and user intent.",
        "Prefer local tools when available.",
        "Keep answers concise but useful.",
    ])
    habits: list[str] = field(default_factory=lambda: [
        "Remember important facts over time.",
        "Offer short next steps when a task is complex.",
    ])


class CharacterEngine:
    """Independent personality layer that influences all responses without depending on the model."""

    def __init__(self, profile: CharacterProfile | None = None) -> None:
        self.profile = profile or CharacterProfile()

    def build_system_prompt(self) -> str:
        return (
            f"You are {self.profile.name}. "
            f"Tone: {self.profile.tone}. "
            f"Personality: {self.profile.personality}. "
            f"Style: {self.profile.style}. "
            f"Rules: {'; '.join(self.profile.rules)}. "
            f"Habits: {'; '.join(self.profile.habits)}."
        )

    def influence(self, text: str, *, context: dict[str, Any] | None = None) -> str:
        if not text:
            return text
        prefix = ""
        if context and context.get("needs_planning"):
            prefix = "I’ll outline the next steps clearly. "
        return f"{prefix}{text}"
