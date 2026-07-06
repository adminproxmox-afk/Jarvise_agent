from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProviderConfig:
    name: str
    model: str
    endpoint: str | None = None
    api_key: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderResult:
    text: str
    provider: str
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract interface for any model backend."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    @abstractmethod
    async def generate(self, prompt: str, *, system_prompt: str | None = None) -> ProviderResult:
        raise NotImplementedError
