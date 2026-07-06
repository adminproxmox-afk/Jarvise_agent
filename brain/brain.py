from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from providers.base import LLMProvider, ProviderResult


@dataclass(slots=True)
class BrainResponse:
    text: str
    provider: str
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Brain:
    """Thin model-facing brain that only depends on an LLM provider."""

    def __init__(self, provider: LLMProvider | None = None, *, system_prompt: str = "") -> None:
        self.provider = provider
        self.system_prompt = system_prompt

    async def generate(self, prompt: str, *, system_prompt: str | None = None) -> BrainResponse:
        if self.provider is None:
            raise RuntimeError("No LLM provider configured for the brain.")

        result: ProviderResult = await self.provider.generate(prompt, system_prompt=system_prompt or self.system_prompt)
        return BrainResponse(
            text=result.text,
            provider=result.provider,
            model=result.model,
            metadata=result.metadata,
        )

    async def respond(self, prompt: str, *, context: str | None = None) -> BrainResponse:
        user_prompt = prompt if context is None else f"{context}\n\nUser request: {prompt}"
        return await self.generate(user_prompt)
