from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from providers.base import LLMProvider, ProviderConfig, ProviderResult


class OllamaProvider(LLMProvider):
    """A simple Ollama-compatible provider useful for local open-source models."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        effective = config or ProviderConfig(name="ollama", model="llama3", endpoint="http://127.0.0.1:11434")
        super().__init__(effective)

    async def generate(self, prompt: str, *, system_prompt: str | None = None) -> ProviderResult:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "system": system_prompt or "You are a helpful assistant.",
        }
        url = f"{self.config.endpoint.rstrip('/')}/api/generate"

        def _request() -> dict[str, object]:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))

        try:
            data = await asyncio.to_thread(_request)
            text = str(data.get("response", ""))
            return ProviderResult(text=text, provider=self.name, model=self.model, metadata={"raw": data})
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return ProviderResult(text=f"Provider unavailable: {exc}", provider=self.name, model=self.model, metadata={"error": str(exc)})
