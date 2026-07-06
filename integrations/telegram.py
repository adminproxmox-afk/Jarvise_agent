from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from config import Settings
from core.events import EventBus, JarvisEvent


CommandHandler = Callable[[str], Awaitable[dict[str, Any]]]
StatusProvider = Callable[[], Awaitable[dict[str, Any]]]
TaskProvider = Callable[[int], Awaitable[dict[str, Any] | None]]
TaskListProvider = Callable[[], Awaitable[list[dict[str, Any]]]]
MemorySearchProvider = Callable[[str, int], Awaitable[list[dict[str, Any]]]]
MemoryListProvider = Callable[[str | None, int], Awaitable[list[dict[str, Any]]]]
ModeProvider = Callable[[str], Awaitable[dict[str, Any]]]
ActionProvider = Callable[[], Awaitable[dict[str, Any]]]


class TelegramService:
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.token = self._clean_secret(settings.get("telegram.bot_token", ""))
        self.chat_id = self._clean_secret(settings.get("telegram.chat_id", ""))
        self.enabled = bool(settings.get("telegram.enabled", False) and self.token and self.chat_id)
        self.report_interval = float(settings.get("telegram.progress_report_interval_seconds", 300))
        self._poll_task: asyncio.Task[None] | None = None
        self._notify_task: asyncio.Task[None] | None = None
        self._last_progress_report: dict[int, float] = {}

    @property
    def api_base(self) -> str:
        return f"https://api.telegram.org/bot{self.token}"

    @staticmethod
    def _clean_secret(value: object) -> str:
        text = str(value or "").strip()
        if text.startswith("${") or (text.startswith("%") and text.endswith("%")):
            return ""
        return text

    async def start(
        self,
        *,
        command_handler: CommandHandler,
        status_provider: StatusProvider,
        task_provider: TaskProvider,
        tasks_provider: TaskListProvider | None = None,
        models_provider: StatusProvider | None = None,
        memory_search_provider: MemorySearchProvider | None = None,
        memory_list_provider: MemoryListProvider | None = None,
        mode_provider: ModeProvider | None = None,
        music_status_provider: StatusProvider | None = None,
        music_play_provider: ActionProvider | None = None,
        music_pause_provider: ActionProvider | None = None,
        music_resume_provider: ActionProvider | None = None,
        music_stop_provider: ActionProvider | None = None,
        activate_provider: ActionProvider | None = None,
    ) -> None:
        if not self.enabled:
            await self.event_bus.publish("telegram.disabled", self.status(), source="telegram")
            return
        self._poll_task = asyncio.create_task(
            self._poll_loop(
                command_handler,
                status_provider,
                task_provider,
                tasks_provider,
                models_provider,
                memory_search_provider,
                memory_list_provider,
                mode_provider,
                music_status_provider,
                music_play_provider,
                music_pause_provider,
                music_resume_provider,
                music_stop_provider,
                activate_provider,
            ),
            name="jarvis.telegram.poll",
        )
        self._notify_task = asyncio.create_task(self._notification_loop(), name="jarvis.telegram.notify")
        await self.event_bus.publish("telegram.started", self.status(), source="telegram")

    async def stop(self) -> None:
        for task in (self._poll_task, self._notify_task):
            if task:
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._poll_task, self._notify_task) if task),
            return_exceptions=True,
        )
        self._poll_task = None
        self._notify_task = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": bool(self.token and self.chat_id),
            "chat_id": self.chat_id[-4:].rjust(len(self.chat_id), "*") if self.chat_id else "",
            "progress_report_interval_seconds": self.report_interval,
        }

    async def send_message(self, text: str) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "telegram_disabled"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.api_base}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
            )
            response.raise_for_status()
            return response.json()

    async def test(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "telegram_disabled_or_unconfigured", "status": self.status()}
        try:
            return await self.send_message("JARVIS Telegram link online.")
        except Exception as exc:
            return {"ok": False, "reason": "send_failed", "detail": str(exc)}

    async def _poll_loop(
        self,
        command_handler: CommandHandler,
        status_provider: StatusProvider,
        task_provider: TaskProvider,
        tasks_provider: TaskListProvider | None,
        models_provider: StatusProvider | None,
        memory_search_provider: MemorySearchProvider | None,
        memory_list_provider: MemoryListProvider | None,
        mode_provider: ModeProvider | None,
        music_status_provider: StatusProvider | None,
        music_play_provider: ActionProvider | None,
        music_pause_provider: ActionProvider | None,
        music_resume_provider: ActionProvider | None,
        music_stop_provider: ActionProvider | None,
        activate_provider: ActionProvider | None,
    ) -> None:
        offset = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=35) as client:
                    response = await client.get(
                        f"{self.api_base}/getUpdates",
                        params={"timeout": 25, "offset": offset, "allowed_updates": ["message"]},
                    )
                    response.raise_for_status()
                    data = response.json()
                for update in data.get("result", []):
                    offset = max(offset, int(update["update_id"]) + 1)
                    await self._handle_update(
                        update,
                        command_handler,
                        status_provider,
                        task_provider,
                        tasks_provider,
                        models_provider,
                        memory_search_provider,
                        memory_list_provider,
                        mode_provider,
                        music_status_provider,
                        music_play_provider,
                        music_pause_provider,
                        music_resume_provider,
                        music_stop_provider,
                        activate_provider,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self.event_bus.publish(
                    "telegram.poll_failed",
                    {"detail": str(exc)},
                    source="telegram",
                    level="error",
                )
                await asyncio.sleep(8)

    async def _handle_update(
        self,
        update: dict[str, Any],
        command_handler: CommandHandler,
        status_provider: StatusProvider,
        task_provider: TaskProvider,
        tasks_provider: TaskListProvider | None,
        models_provider: StatusProvider | None,
        memory_search_provider: MemorySearchProvider | None,
        memory_list_provider: MemoryListProvider | None,
        mode_provider: ModeProvider | None,
        music_status_provider: StatusProvider | None,
        music_play_provider: ActionProvider | None,
        music_pause_provider: ActionProvider | None,
        music_resume_provider: ActionProvider | None,
        music_stop_provider: ActionProvider | None,
        activate_provider: ActionProvider | None,
    ) -> None:
        message = update.get("message") or {}
        chat = str((message.get("chat") or {}).get("id", ""))
        if chat != self.chat_id:
            await self.event_bus.publish("telegram.ignored", {"chat_id": chat}, source="telegram", level="warning")
            return
        text = str(message.get("text", "")).strip()
        if not text:
            return

        if text in {"/start", "/help", "/commands"}:
            await self.send_message(self._help_text())
            return

        if text == "/ping":
            await self.send_message("pong")
            return

        if text == "/status":
            status = await status_provider()
            await self.send_message(
                f"JARVIS: {'active' if status.get('active') else 'standby'}\n"
                f"Music: {(status.get('music') or {}).get('mode', 'unknown')}"
            )
            return

        if text == "/models":
            if models_provider is None:
                await self.send_message("Models overview is unavailable.")
                return
            await self.send_message(self._format_models(await models_provider()))
            return

        if text == "/tasks":
            if tasks_provider is None:
                await self.send_message("Task list is unavailable.")
                return
            await self.send_message(self._format_task_list(await tasks_provider()))
            return

        if text.startswith("/task"):
            parts = text.split()
            if len(parts) < 2 or not parts[1].isdigit():
                await self.send_message("Usage: /task 12")
                return
            task = await task_provider(int(parts[1]))
            if not task:
                await self.send_message("Task not found.")
                return
            await self.send_message(self._format_task(task))
            return

        if text.startswith("/memory"):
            query = text[len("/memory") :].strip()
            if query:
                if memory_search_provider is None:
                    await self.send_message("Memory search is unavailable.")
                    return
                items = await memory_search_provider(query, 10)
                await self.send_message(self._format_memory_list(items, header=f"Memory search: {query}"))
                return
            if memory_list_provider is None:
                await self.send_message("Memory listing is unavailable.")
                return
            items = await memory_list_provider(None, 10)
            await self.send_message(self._format_memory_list(items, header="Recent memory"))
            return

        if text.startswith("/mode"):
            mode = text[len("/mode") :].strip()
            if not mode:
                await self.send_message("Usage: /mode focus")
                return
            if mode_provider is None:
                result = await command_handler(f"увімкни режим {mode}")
                await self.send_message(self._format_command_result(result))
                return
            result = await mode_provider(mode)
            await self.send_message(self._format_generic_result(result, fallback=f"Mode switched: {mode}"))
            return

        if text.startswith("/activate"):
            if activate_provider is None:
                result = await command_handler("активуйся")
                await self.send_message(self._format_command_result(result))
                return
            result = await activate_provider()
            await self.send_message(self._format_generic_result(result, fallback="Activation started."))
            return

        if text.startswith("/music"):
            await self._handle_music_command(
                text,
                music_status_provider=music_status_provider,
                music_play_provider=music_play_provider,
                music_pause_provider=music_pause_provider,
                music_resume_provider=music_resume_provider,
                music_stop_provider=music_stop_provider,
            )
            return

        if text.startswith("/weather"):
            location = text[len("/weather") :].strip()
            if not location:
                await self.send_message("Usage: /weather Vinnytsia")
                return
            result = await command_handler(f"яка щас погода в {location}")
            response = str(result.get("response") or result.get("answer") or "Command received.")
            sources = result.get("result", {}).get("sources") if isinstance(result.get("result"), dict) else result.get("sources")
            if isinstance(sources, list) and sources:
                source_lines = []
                for item in sources[:3]:
                    if isinstance(item, dict):
                        title = str(item.get("title") or item.get("url") or "").strip()
                        url = str(item.get("url") or "").strip()
                        if title and url:
                            source_lines.append(f"- {title}: {url}")
                if source_lines:
                    response = f"{response}\n\nДжерела:\n" + "\n".join(source_lines)
            await self.send_message(response)
            return

        if text.startswith("/search") or text.startswith("/ask") or text.startswith("/news") or text.startswith("/open") or text.startswith("/run"):
            query = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not query:
                await self.send_message(self._usage_for(text))
                return
            natural_language = self._natural_language_query(text, query)
            result = await command_handler(natural_language)
            await self.send_message(self._format_command_result(result))
            return

        result = await command_handler(text)
        await self.send_message(self._format_command_result(result))

    async def _notification_loop(self) -> None:
        queue = await self.event_bus.subscribe(replay=False)
        try:
            while True:
                event = await queue.get()
                if event.type in {"task.completed", "task.failed", "task.canceled"}:
                    await self._send_task_event(event)
                elif event.type == "task.progress":
                    await self._send_progress_event(event)
        finally:
            await self.event_bus.unsubscribe(queue)

    async def _send_task_event(self, event: JarvisEvent) -> None:
        task = event.payload
        status = str(task.get("status", event.type.split(".")[-1])).upper()
        await self.send_message(
            f"Task #{task.get('id')} {status}\n"
            f"{task.get('title')}\n"
            f"Progress: {task.get('progress')}%\n"
            f"Agent: {task.get('agent')}"
        )

    async def _send_progress_event(self, event: JarvisEvent) -> None:
        task_id = int(event.payload.get("id") or 0)
        if task_id <= 0:
            return
        now = time.monotonic()
        if now - self._last_progress_report.get(task_id, 0.0) < self.report_interval:
            return
        self._last_progress_report[task_id] = now
        await self.send_message(self._format_task(event.payload))

    @staticmethod
    def _format_task(task: dict[str, Any]) -> str:
        return (
            f"Task #{task.get('id')}\n"
            f"Status: {task.get('status')}\n"
            f"Progress: {task.get('progress')}%\n"
            f"Current Step: {task.get('current_step') or 'done'}"
        )

    async def _handle_music_command(
        self,
        text: str,
        *,
        music_status_provider: StatusProvider | None,
        music_play_provider: ActionProvider | None,
        music_pause_provider: ActionProvider | None,
        music_resume_provider: ActionProvider | None,
        music_stop_provider: ActionProvider | None,
    ) -> None:
        parts = text.split(maxsplit=1)
        action = parts[1].strip().lower() if len(parts) > 1 else "status"
        if action in {"", "status"}:
            if music_status_provider is None:
                await self.send_message("Music status is unavailable.")
                return
            await self.send_message(self._format_music_status(await music_status_provider()))
            return
        providers = {
            "play": music_play_provider,
            "pause": music_pause_provider,
            "resume": music_resume_provider,
            "stop": music_stop_provider,
        }
        provider = providers.get(action)
        if provider is None:
            await self.send_message("Usage: /music status|play|pause|resume|stop")
            return
        result = await provider()
        await self.send_message(self._format_generic_result(result, fallback=f"Music {action} requested."))

    @staticmethod
    def _format_command_result(result: dict[str, Any]) -> str:
        response = str(result.get("response") or result.get("answer") or result.get("status") or "Command received.").strip()
        sources = result.get("result", {}).get("sources") if isinstance(result.get("result"), dict) else result.get("sources")
        snippets = result.get("result", {}).get("snippets") if isinstance(result.get("result"), dict) else result.get("snippets")
        if isinstance(sources, list) and sources:
            source_lines = []
            for item in sources[:3]:
                if isinstance(item, dict):
                    title = str(item.get("title") or item.get("url") or "").strip()
                    url = str(item.get("url") or "").strip()
                    if title and url:
                        source_lines.append(f"- {title}: {url}")
            if source_lines:
                response = f"{response}\n\nSources:\n" + "\n".join(source_lines)
        if isinstance(snippets, list) and snippets:
            snippet_lines = []
            for item in snippets[:3]:
                if isinstance(item, dict):
                    title = str(item.get("title") or "").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    if title or snippet:
                        snippet_lines.append(f"- {title or 'snippet'}: {snippet[:220]}")
            if snippet_lines:
                response = f"{response}\n\nSnippets:\n" + "\n".join(snippet_lines)
        return response[:3900]

    @staticmethod
    def _format_generic_result(result: dict[str, Any], *, fallback: str) -> str:
        if isinstance(result, dict):
            for key in ("response", "answer", "status", "message", "detail"):
                value = str(result.get(key) or "").strip()
                if value:
                    return value[:3900]
        return fallback

    @staticmethod
    def _format_models(data: dict[str, Any]) -> str:
        if not isinstance(data, dict):
            return "Models overview unavailable."
        lines = ["Models:"]
        for key in ("active", "selected", "provider", "model"):
            value = data.get(key)
            if isinstance(value, dict):
                inner = ", ".join(f"{k}={v}" for k, v in value.items() if v)
                if inner:
                    lines.append(f"- {key}: {inner}")
            elif value:
                lines.append(f"- {key}: {value}")
        for key in ("providers", "models", "available", "available_models"):
            value = data.get(key)
            if isinstance(value, list) and value:
                lines.append(f"- {key}: {', '.join(str(item) for item in value[:8])}")
            elif isinstance(value, dict) and value:
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, list) and subvalue:
                        lines.append(f"- {subkey}: {', '.join(str(item) for item in subvalue[:6])}")
        if len(lines) == 1:
            lines.append("- no details")
        return "\n".join(lines)[:3900]

    @staticmethod
    def _format_task_list(tasks: list[dict[str, Any]]) -> str:
        if not tasks:
            return "No tasks found."
        lines = ["Tasks:"]
        for task in tasks[:10]:
            if not isinstance(task, dict):
                continue
            task_id = task.get("id")
            title = str(task.get("title") or task.get("request") or "").strip()
            status = str(task.get("status") or "").strip()
            progress = task.get("progress")
            parts = [f"#{task_id}" if task_id is not None else "#?", title or "untitled"]
            if status:
                parts.append(status)
            if progress is not None:
                parts.append(f"{progress}%")
            lines.append("- " + " | ".join(parts))
        return "\n".join(lines)[:3900]

    @staticmethod
    def _format_memory_list(items: list[dict[str, Any]], *, header: str) -> str:
        if not items:
            return f"{header}\n- empty"
        lines = [header]
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("id") or "").strip()
            section = str(item.get("section") or "").strip()
            value = item.get("value")
            preview = str(value) if not isinstance(value, (dict, list)) else str(value)[:120]
            if key or preview:
                prefix = f"[{section}] " if section else ""
                lines.append(f"- {prefix}{key or 'item'}: {preview[:220]}")
        return "\n".join(lines)[:3900]

    @staticmethod
    def _format_music_status(data: dict[str, Any]) -> str:
        if not isinstance(data, dict):
            return "Music status unavailable."
        mode = str(data.get("mode") or data.get("state") or "unknown").strip()
        track = str(data.get("current") or data.get("track") or data.get("title") or "").strip()
        volume = data.get("volume")
        lines = [f"Music: {mode}"]
        if track:
            lines.append(f"Track: {track}")
        if volume is not None:
            lines.append(f"Volume: {volume}")
        return "\n".join(lines)

    @staticmethod
    def _natural_language_query(command: str, query: str) -> str:
        prefix = command.lstrip("/").lower()
        if prefix == "news":
            return f"новини про {query}"
        if prefix == "open":
            return f"відкрий {query}"
        if prefix == "run":
            return f"виконай команду {query}"
        return query

    @staticmethod
    def _usage_for(command: str) -> str:
        prefix = command.lstrip("/").lower()
        usages = {
            "search": "Usage: /search python fastapi",
            "ask": "Usage: /ask who is Alan Turing",
            "news": "Usage: /news artificial intelligence",
            "open": "Usage: /open chrome",
            "run": "Usage: /run npm test",
        }
        return usages.get(prefix, "Command requires arguments.")

    @staticmethod
    def _help_text() -> str:
        return (
            "Available commands:\n"
            "/help - show this list\n"
            "/ping - quick health check\n"
            "/status - assistant state\n"
            "/models - current model/provider info\n"
            "/tasks - recent tasks\n"
            "/task <id> - task details\n"
            "/memory [query] - recent memory or search\n"
            "/mode <name> - switch mode\n"
            "/activate - run activation flow\n"
            "/music status|play|pause|resume|stop\n"
            "/weather <city> - live weather\n"
            "/search <query> - internet search\n"
            "/ask <question> - ask the assistant\n"
            "/news <topic> - recent news\n"
            "/open <app> - open app or site\n"
            "/run <command> - execute a command request"
        )
