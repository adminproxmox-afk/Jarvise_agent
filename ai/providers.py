from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from config import Settings


@dataclass(slots=True)
class AiProviderResult:
    text: str
    provider: str
    model: str


class AiProvider:
    async def complete(self, messages: list[dict[str, str]]) -> AiProviderResult | None:
        raise NotImplementedError


class OpenAiChatProvider(AiProvider):
    def __init__(self, settings: Settings) -> None:
        self.model = str(settings.get("ai.openai_model", "gpt-4.1-mini"))
        self.timeout = float(settings.get("ai.timeout_seconds", 12))

    async def complete(self, messages: list[dict[str, str]]) -> AiProviderResult | None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            payload = response.json()
            text = payload["choices"][0]["message"].get("content", "").strip()
            return AiProviderResult(text=text, provider="openai", model=self.model)


class OllamaProvider(AiProvider):
    def __init__(self, settings: Settings) -> None:
        self.model = str(settings.get("ai.ollama_model", "llama3.1"))
        self.host = str(settings.get("ai.ollama_host", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))).rstrip("/")
        self.timeout = float(settings.get("ai.timeout_seconds", 18))

    async def complete(self, messages: list[dict[str, str]]) -> AiProviderResult | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.host}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
            )
            response.raise_for_status()
            payload = response.json()
            text = payload.get("message", {}).get("content", "").strip()
            return AiProviderResult(text=text, provider="ollama", model=self.model)


def create_provider(settings: Settings) -> AiProvider | None:
    provider = str(settings.get("ai.provider", "local")).lower()
    if provider == "openai":
        return OpenAiChatProvider(settings)
    if provider == "ollama":
        return OllamaProvider(settings)
    return None
