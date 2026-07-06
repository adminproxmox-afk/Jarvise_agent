from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from config import Settings


FREE_COSTS = {"free_tier", "local"}


@dataclass(slots=True)
class AIMessage:
    role: str
    content: str


@dataclass(slots=True)
class AIResponse:
    text: str
    provider: str
    model: str
    task_type: str
    routed_by: str = "auto"
    raw: dict[str, Any] | None = None


class AIProvider(Protocol):
    name: str
    display_name: str
    model: str
    cost: str

    @property
    def configured(self) -> bool:
        ...

    async def chat(
        self,
        messages: list[AIMessage],
        *,
        task_type: str,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AIResponse | None:
        ...

    async def healthcheck(self) -> dict[str, Any]:
        ...

    async def list_models(self) -> list[dict[str, Any]]:
        ...


def _model_option(
    *,
    provider: str,
    model_id: str,
    display_name: str | None = None,
    source: str = "configured",
    free: bool = True,
    supports_chat: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    option: dict[str, Any] = {
        "id": model_id,
        "display_name": display_name or model_id,
        "provider": provider,
        "source": source,
        "free": free,
        "supports_chat": supports_chat,
    }
    option.update({key: value for key, value in extra.items() if value is not None})
    return option


def _dedupe_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for model in models:
        model_id = str(model.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        deduped.append({**model, "id": model_id})
    return deduped


def _extract_model_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            ids.append(item.strip())
        elif isinstance(item, dict) and str(item.get("id") or "").strip():
            ids.append(str(item["id"]).strip())
    return ids


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        display_name: str,
        model: str,
        base_url: str,
        api_key_env: str | None,
        timeout: float,
        cost: str,
        model_options: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.display_name = display_name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.cost = cost
        self.model_options = _dedupe_ids([model, *(model_options or [])])
        self.extra_headers = extra_headers or {}

    @property
    def configured(self) -> bool:
        return self.api_key_env is None or bool(os.getenv(self.api_key_env))

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key_env:
            headers["Authorization"] = f"Bearer {os.getenv(self.api_key_env, '')}"
        return headers

    async def chat(
        self,
        messages: list[AIMessage],
        *,
        task_type: str,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AIResponse | None:
        if not self.configured:
            return None

        payload = {
            "model": model or self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        text = data["choices"][0]["message"].get("content", "").strip()
        if not text:
            return None
        return AIResponse(
            text=text,
            provider=self.name,
            model=str(payload["model"]),
            task_type=task_type,
            raw={"id": data.get("id"), "usage": data.get("usage")},
        )

    async def healthcheck(self) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "status": "missing_credentials"}
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 5.0)) as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
            return {"ok": response.status_code < 500, "status": response.status_code}
        except Exception as exc:
            return {"ok": False, "status": "unreachable", "detail": str(exc)}

    async def list_models(self) -> list[dict[str, Any]]:
        fallback = self._fallback_models()
        if not self.configured:
            return fallback
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 10.0)) as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
            response.raise_for_status()
            data = response.json()
        except Exception:
            return fallback

        parsed: list[dict[str, Any]] = []
        for item in data.get("data", []):
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                continue
            parsed.append(
                _model_option(
                    provider=self.name,
                    model_id=model_id,
                    source="remote",
                    free=self._is_free_model(model_id),
                )
            )
        return _dedupe_models([*fallback, *parsed])

    def _fallback_models(self) -> list[dict[str, Any]]:
        return [
            _model_option(
                provider=self.name,
                model_id=model_id,
                free=self._is_free_model(model_id),
            )
            for model_id in self.model_options
        ]

    def _is_free_model(self, model_id: str) -> bool:
        return self.cost in FREE_COSTS or model_id.endswith(":free")


class ClaudeProvider:
    name = "claude"
    display_name = "Claude"
    cost = "paid"

    def __init__(self, settings: Settings) -> None:
        self.model = str(settings.get("ai.models.claude", "claude-3-5-sonnet-latest"))
        self.timeout = float(settings.get("ai.timeout_seconds", 12))

    @property
    def configured(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"))

    async def chat(
        self,
        messages: list[AIMessage],
        *,
        task_type: str,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AIResponse | None:
        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        if not api_key:
            return None

        system = "\n\n".join(item.content for item in messages if item.role == "system")
        chat_messages = [
            {"role": item.role if item.role in {"user", "assistant"} else "user", "content": item.content}
            for item in messages
            if item.role != "system"
        ]
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": 2048,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        text = "".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text").strip()
        if not text:
            return None
        return AIResponse(text=text, provider=self.name, model=str(payload["model"]), task_type=task_type)

    async def healthcheck(self) -> dict[str, Any]:
        return {"ok": self.configured, "status": "configured" if self.configured else "missing_credentials"}

    async def list_models(self) -> list[dict[str, Any]]:
        return [_model_option(provider=self.name, model_id=self.model, free=False)]


class GeminiProvider:
    name = "gemini"
    display_name = "Gemini"
    cost = "free_tier"

    def __init__(self, settings: Settings) -> None:
        self.model = str(settings.get("ai.models.gemini", "gemini-2.0-flash"))
        self.timeout = float(settings.get("ai.timeout_seconds", 12))
        self.model_options = _dedupe_ids([self.model, *_extract_model_ids(settings.get("ai.available_models.gemini", []))])

    @property
    def configured(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

    async def chat(
        self,
        messages: list[AIMessage],
        *,
        task_type: str,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AIResponse | None:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return None

        system = "\n\n".join(item.content for item in messages if item.role == "system")
        contents = []
        for item in messages:
            if item.role == "system":
                continue
            role = "model" if item.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": item.content}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        selected_model = _clean_model_id(self.name, model or self.model)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent",
                params={"key": api_key},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            return None
        return AIResponse(text=text, provider=self.name, model=selected_model, task_type=task_type)

    async def healthcheck(self) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "status": "missing_credentials"}
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 5.0)) as client:
                response = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"), "pageSize": 1},
                )
            return {"ok": response.status_code < 500, "status": response.status_code}
        except Exception as exc:
            return {"ok": False, "status": "unreachable", "detail": str(exc)}

    async def list_models(self) -> list[dict[str, Any]]:
        fallback = [
            _model_option(provider=self.name, model_id=model_id, free=True)
            for model_id in self.model_options
        ]
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return fallback

        models: list[dict[str, Any]] = []
        page_token: str | None = None
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 10.0)) as client:
                while True:
                    params = {"key": api_key, "pageSize": 100}
                    if page_token:
                        params["pageToken"] = page_token
                    response = await client.get(
                        "https://generativelanguage.googleapis.com/v1beta/models",
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()
                    for item in data.get("models", []):
                        methods = {str(method) for method in item.get("supportedGenerationMethods", [])}
                        if methods and "generateContent" not in methods:
                            continue
                        model_id = _clean_model_id(self.name, str(item.get("name") or ""))
                        if not model_id:
                            continue
                        models.append(
                            _model_option(
                                provider=self.name,
                                model_id=model_id,
                                display_name=str(item.get("displayName") or model_id),
                                source="remote",
                                free=True,
                                input_token_limit=item.get("inputTokenLimit"),
                                output_token_limit=item.get("outputTokenLimit"),
                            )
                        )
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
        except Exception:
            return fallback
        return _dedupe_models([*fallback, *models])


class OllamaChatProvider:
    name = "ollama"
    display_name = "Ollama"
    cost = "local"

    def __init__(self, settings: Settings) -> None:
        self.model = str(settings.get("ai.models.ollama", settings.get("ai.ollama_model", "llama3.1")))
        self.host = str(settings.get("ai.ollama_host", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))).rstrip("/")
        self.timeout = float(settings.get("ai.timeout_seconds", 18))

    @property
    def configured(self) -> bool:
        return True

    async def chat(
        self,
        messages: list[AIMessage],
        *,
        task_type: str,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AIResponse | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.host}/api/chat",
                json={
                    "model": model or self.model,
                    "messages": [{"role": item.role, "content": item.content} for item in messages],
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            response.raise_for_status()
            data = response.json()
        text = data.get("message", {}).get("content", "").strip()
        if not text:
            return None
        return AIResponse(text=text, provider=self.name, model=model or self.model, task_type=task_type)

    async def healthcheck(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(f"{self.host}/api/tags")
            return {"ok": response.status_code == 200, "status": response.status_code}
        except Exception as exc:
            return {"ok": False, "status": "unreachable", "detail": str(exc)}

    async def list_models(self) -> list[dict[str, Any]]:
        fallback = [_model_option(provider=self.name, model_id=self.model, free=True)]
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(f"{self.host}/api/tags")
            response.raise_for_status()
            data = response.json()
        except Exception:
            return fallback

        models = [
            _model_option(provider=self.name, model_id=str(item.get("name") or ""), source="remote", free=True)
            for item in data.get("models", [])
            if str(item.get("name") or "").strip()
        ]
        return _dedupe_models([*fallback, *models])


class AIGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timeout = float(settings.get("ai.timeout_seconds", 12))
        self.free_only = bool(settings.get("ai.free_only", True))
        self.free_providers = set(
            str(item).lower()
            for item in settings.get("ai.free_providers", ["gemini", "groq", "ollama", "lmstudio", "local_llm"])
        )
        self.model_cache_seconds = float(settings.get("ai.model_cache_seconds", 300))
        self.selection_path = self._selection_path()
        self.providers: dict[str, AIProvider] = self._build_providers()
        self._models_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._selected_provider, self._selected_model = self._load_model_selection()

    def _build_providers(self) -> dict[str, AIProvider]:
        models = {
            "openai": str(self.settings.get("ai.models.openai", self.settings.get("ai.openai_model", "gpt-4.1-mini"))),
            "deepseek": str(self.settings.get("ai.models.deepseek", "deepseek-chat")),
            "groq": str(self.settings.get("ai.models.groq", "llama-3.3-70b-versatile")),
            "openrouter": str(self.settings.get("ai.models.openrouter", "google/gemini-2.0-flash-exp:free")),
            "lmstudio": str(self.settings.get("ai.models.lmstudio", "local-model")),
            "local_llm": str(self.settings.get("ai.models.local_llm", "local-model")),
        }
        return {
            "openai": OpenAICompatibleProvider(
                name="openai",
                display_name="OpenAI",
                model=models["openai"],
                base_url=str(self.settings.get("ai.base_urls.openai", "https://api.openai.com/v1")),
                api_key_env="OPENAI_API_KEY",
                timeout=self.timeout,
                cost="paid",
                model_options=_extract_model_ids(self.settings.get("ai.available_models.openai", [])),
            ),
            "deepseek": OpenAICompatibleProvider(
                name="deepseek",
                display_name="DeepSeek",
                model=models["deepseek"],
                base_url=str(self.settings.get("ai.base_urls.deepseek", "https://api.deepseek.com/v1")),
                api_key_env="DEEPSEEK_API_KEY",
                timeout=self.timeout,
                cost="paid",
                model_options=_extract_model_ids(self.settings.get("ai.available_models.deepseek", [])),
            ),
            "groq": OpenAICompatibleProvider(
                name="groq",
                display_name="Groq",
                model=models["groq"],
                base_url=str(self.settings.get("ai.base_urls.groq", "https://api.groq.com/openai/v1")),
                api_key_env="GROQ_API_KEY",
                timeout=self.timeout,
                cost="free_tier",
                model_options=_extract_model_ids(self.settings.get("ai.available_models.groq", [])),
            ),
            "openrouter": OpenAICompatibleProvider(
                name="openrouter",
                display_name="OpenRouter",
                model=models["openrouter"],
                base_url=str(self.settings.get("ai.base_urls.openrouter", "https://openrouter.ai/api/v1")),
                api_key_env="OPENROUTER_API_KEY",
                timeout=self.timeout,
                cost="mixed",
                model_options=_extract_model_ids(self.settings.get("ai.available_models.openrouter", [])),
                extra_headers={"HTTP-Referer": "http://127.0.0.1:5173", "X-Title": "JARVIS"},
            ),
            "claude": ClaudeProvider(self.settings),
            "gemini": GeminiProvider(self.settings),
            "ollama": OllamaChatProvider(self.settings),
            "lmstudio": OpenAICompatibleProvider(
                name="lmstudio",
                display_name="LM Studio",
                model=models["lmstudio"],
                base_url=str(self.settings.get("ai.base_urls.lmstudio", "http://127.0.0.1:1234/v1")),
                api_key_env=None,
                timeout=self.timeout,
                cost="local",
                model_options=_extract_model_ids(self.settings.get("ai.available_models.lmstudio", [])),
            ),
            "local_llm": OpenAICompatibleProvider(
                name="local_llm",
                display_name="Local LLM",
                model=models["local_llm"],
                base_url=str(self.settings.get("ai.base_urls.local_llm", "http://127.0.0.1:8080/v1")),
                api_key_env=None,
                timeout=self.timeout,
                cost="local",
                model_options=_extract_model_ids(self.settings.get("ai.available_models.local_llm", [])),
            ),
        }

    def classify_task(self, text: str) -> str:
        normalized = text.lower().replace("ё", "е")
        checks: list[tuple[str, tuple[str, ...]]] = [
            ("coding", ("код", "code", "react", "fastapi", "python", "typescript", "bug", "тест", "рефактор", "проект")),
            ("search", ("найди", "поиск", "search", "документац", "исслед", "research", "собери данные")),
            ("analysis", ("проанализ", "анализ", "review", "аудит", "deep analysis", "разбери")),
            ("local", ("локально", "ollama", "без интернета", "local", "на компьютере")),
            ("planning", ("план", "спланируй", "roadmap", "архитектур", "разбей", "стратег")),
        ]
        for task_type, keywords in checks:
            if any(keyword in normalized for keyword in keywords):
                return task_type
        return "chat"

    def route_for_task(self, task_type: str) -> str:
        selection = self.current_selection()
        if selection:
            return selection["provider"]
        routing = self.routing_table()
        return routing.get(task_type, routing.get("chat", "gemini"))

    def routing_table(self) -> dict[str, str]:
        configured = self.settings.get("ai.routing", {})
        defaults = {
            "coding": "gemini",
            "planning": "gemini",
            "search": "gemini",
            "local": "ollama",
            "analysis": "gemini",
            "chat": str(self.settings.get("ai.provider", "gemini")),
        }
        if isinstance(configured, dict):
            defaults.update({str(key): str(value) for key, value in configured.items()})
        if self.current_selection():
            provider = self.current_selection()["provider"]
            defaults = {key: provider for key in defaults}
        return defaults

    async def chat(
        self,
        messages: list[AIMessage],
        *,
        task_type: str | None = None,
        preferred_provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AIResponse | None:
        task = task_type or self.classify_task(" ".join(item.content for item in messages if item.role == "user"))
        selection = self.current_selection()
        uses_global_selection = bool(selection and preferred_provider is None and model is None)

        if uses_global_selection and selection:
            primary = selection["provider"]
            primary_model = selection["model"]
            provider_order = [primary]
        else:
            primary = (preferred_provider or self.route_for_task(task)).lower()
            primary_model = model
            provider_order = [primary, *[name for name in self.providers if name != primary]]

        for name in provider_order:
            provider = self.providers.get(name)
            if provider is None or not provider.configured:
                continue
            call_model = primary_model if name == primary else None
            if not self._provider_allowed(provider, call_model or provider.model):
                continue
            try:
                response = await provider.chat(messages, task_type=task, model=call_model, temperature=temperature)
            except Exception:
                continue
            if response:
                response.routed_by = "selected" if uses_global_selection else ("preferred" if name == primary else "fallback")
                return response
        return None

    async def describe(self) -> dict[str, Any]:
        routing = self.routing_table()
        selection = self.current_selection()
        providers: list[dict[str, Any]] = []
        for provider in self.providers.values():
            models = await self.list_provider_models(provider.name)
            providers.append(
                {
                    "name": provider.name,
                    "display_name": provider.display_name,
                    "model": provider.model,
                    "configured": provider.configured,
                    "cost": provider.cost,
                    "free": self._provider_allowed(provider, provider.model),
                    "selected": bool(selection and selection["provider"] == provider.name),
                    "available_models": models,
                    "routed_tasks": [
                        task for task, route_provider in routing.items() if route_provider == provider.name
                    ],
                }
            )
        return {
            "routing": routing,
            "free_only": self.free_only,
            "selection": selection,
            "providers": providers,
        }

    async def list_provider_models(self, name: str, *, refresh: bool = False) -> list[dict[str, Any]]:
        provider = self.providers.get(name.lower())
        if provider is None:
            return []
        cached = self._models_cache.get(provider.name)
        now = time.monotonic()
        if cached and not refresh and now - cached[0] <= self.model_cache_seconds:
            return cached[1]
        models = await provider.list_models()
        if self.free_only:
            models = [model for model in models if self._model_allowed(provider, str(model.get("id") or ""))]
        models = _dedupe_models(models)
        self._models_cache[provider.name] = (now, models)
        return models

    async def test_provider(self, name: str) -> dict[str, Any]:
        provider = self.providers.get(name.lower())
        if provider is None:
            return {"ok": False, "status": "unknown_provider"}
        result = await provider.healthcheck()
        models = await self.list_provider_models(provider.name, refresh=True)
        return {
            "provider": provider.name,
            "display_name": provider.display_name,
            "model": provider.model,
            "cost": provider.cost,
            "free": self._provider_allowed(provider, provider.model),
            "available_models": models[:80],
            **result,
        }

    def current_selection(self) -> dict[str, str] | None:
        if not self._selected_provider or not self._selected_model:
            return None
        return {"provider": self._selected_provider, "model": self._selected_model}

    def select_model(self, provider_name: str, model: str) -> dict[str, Any]:
        provider_key = str(provider_name or "").strip().lower()
        provider = self.providers.get(provider_key)
        if provider is None:
            return {"ok": False, "reason": "unknown_provider", "provider": provider_name}
        model_id = _clean_model_id(provider.name, str(model or "").strip())
        if not model_id:
            return {"ok": False, "reason": "missing_model"}
        if not self._provider_allowed(provider, model_id):
            return {
                "ok": False,
                "reason": "paid_model_blocked_by_free_only",
                "provider": provider.name,
                "model": model_id,
            }
        self._selected_provider = provider.name
        self._selected_model = model_id
        self._save_model_selection()
        return {
            "ok": True,
            "selection": self.current_selection(),
            "configured": provider.configured,
            "free_only": self.free_only,
        }

    def clear_model_selection(self) -> dict[str, Any]:
        self._selected_provider = None
        self._selected_model = None
        try:
            if self.selection_path.exists():
                self.selection_path.unlink()
        except OSError:
            pass
        return {"ok": True, "selection": None, "free_only": self.free_only}

    def _provider_allowed(self, provider: AIProvider, model: str | None = None) -> bool:
        if not self.free_only:
            return True
        return provider.name in self.free_providers or self._model_allowed(provider, model or provider.model)

    def _model_allowed(self, provider: AIProvider, model: str) -> bool:
        return provider.cost in FREE_COSTS or provider.name in self.free_providers or model.endswith(":free")

    def _selection_path(self) -> Path:
        configured = Path(str(self.settings.get("ai.model_selection_path", "memory/model_selection.json")))
        return configured if configured.is_absolute() else self.settings.root_dir / configured

    def _load_model_selection(self) -> tuple[str | None, str | None]:
        try:
            data = json.loads(self.selection_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, None
        provider = str(data.get("provider") or "").strip().lower()
        model = str(data.get("model") or "").strip()
        if provider not in self.providers or not model:
            return None, None
        return provider, _clean_model_id(provider, model)

    def _save_model_selection(self) -> None:
        selection = self.current_selection()
        if not selection:
            return
        self.selection_path.parent.mkdir(parents=True, exist_ok=True)
        self.selection_path.write_text(json.dumps(selection, indent=2), encoding="utf-8")


def _clean_model_id(provider: str, model: str) -> str:
    clean = model.strip()
    if provider == "gemini" and clean.startswith("models/"):
        return clean.split("/", 1)[1]
    return clean


def _dedupe_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
