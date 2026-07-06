from __future__ import annotations

import asyncio
from typing import Any

from agents import AgentRegistry
from ai.brain import JarvisBrain
from automation.launcher import WorkspaceLauncher
from automation.system_control import SystemControl
from config import Settings
from core.actions import ActionSystem
from core.commands import VoiceCommandRouter
from core.decision_engine import DecisionEngine
from core.events import EventBus
from core.task_manager import TaskManager
from integrations import TelegramService
from internet import InternetService
from memory.service import MemoryService
from memory.store import MemoryStore
from music.local_player import LocalMusicPlayer
from planner.planner import Planner
from skills.manager import SkillManager
from system.sound import StartupSoundPlayer
from system.stats import SystemStatsService
from tools import ToolRegistry
from voice.clap import ClapDetector
from voice.tts import Speaker
from character.engine import CharacterEngine


class JarvisOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        event_bus: EventBus,
        memory: MemoryStore,
        workspace: WorkspaceLauncher,
        speaker: Speaker,
        sound: StartupSoundPlayer,
        music: LocalMusicPlayer,
        system_control: SystemControl,
        stats: SystemStatsService,
        clap_detector: ClapDetector,
        command_router: VoiceCommandRouter,
        brain: JarvisBrain,
        actions: ActionSystem,
        agents: AgentRegistry,
        tools: ToolRegistry,
        task_manager: TaskManager,
        telegram: TelegramService,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.memory = memory
        self.workspace = workspace
        self.speaker = speaker
        self.sound = sound
        self.music = music
        self.system_control = system_control
        self.stats = stats
        self.clap_detector = clap_detector
        self.command_router = command_router
        self.brain = brain
        self.actions = actions
        self.decision_engine = DecisionEngine()
        self.character = CharacterEngine()
        self.memory_service = MemoryService(memory)
        self.planner = Planner()
        self.skill_manager = SkillManager()
        self.internet = InternetService()
        self.agents = agents
        self.tools = tools
        self.task_manager = task_manager
        self.telegram = telegram
        self._active = False
        self._activation_lock = asyncio.Lock()
        self._stats_task: asyncio.Task[None] | None = None
        self._speech_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        await self.event_bus.publish("jarvis.boot", {"name": self.settings.assistant_name})
        await self.task_manager.start()
        if self.settings.get("clap.enabled", True):
            await self.clap_detector.start(self._on_double_clap)
        self._stats_task = asyncio.create_task(self._publish_stats_loop(), name="jarvis.stats")
        await self.telegram.start(
            command_handler=self.handle_text_command,
            status_provider=self.status,
            task_provider=self.task_manager.get_task,
            tasks_provider=self.list_tasks,
            models_provider=self.models_status,
            memory_search_provider=self.search_memory,
            memory_list_provider=self.list_memory,
            mode_provider=self.enable_mode,
            music_status_provider=self.music.status,
            music_play_provider=self.music.play_default,
            music_pause_provider=self.music.pause,
            music_resume_provider=self.music.resume,
            music_stop_provider=self.music.stop,
            activate_provider=lambda: self.activate(trigger="telegram"),
        )
        await self.event_bus.publish("jarvis.ready", {"clap": self.clap_detector.running})

    async def shutdown(self) -> None:
        await self.telegram.stop()
        await self.task_manager.shutdown()
        await self.clap_detector.stop()
        if self._stats_task:
            self._stats_task.cancel()
            try:
                await self._stats_task
            except asyncio.CancelledError:
                pass
        for task in list(self._speech_tasks):
            task.cancel()
        if self._speech_tasks:
            await asyncio.gather(*self._speech_tasks, return_exceptions=True)
        await self.music.close()
        await self.speaker.close()
        await self.memory.close()

    async def _publish_stats_loop(self) -> None:
        while True:
            await self.event_bus.publish("system.stats", self.stats.snapshot(), source="system")
            await asyncio.sleep(2.0)

    async def _on_double_clap(self) -> None:
        await self.activate(trigger="double_clap")

    async def activate(self, *, trigger: str = "manual") -> dict[str, Any]:
        if self._activation_lock.locked():
            await self.event_bus.publish("jarvis.activation_ignored", {"reason": "already_active", "trigger": trigger})
            return {"status": "already_active"}

        async with self._activation_lock:
            self._active = True
            launch_results: list[dict[str, Any]] = []
            try:
                await self.memory.remember_event("activation", {"trigger": trigger})
                await self.event_bus.publish("jarvis.activation_started", {"trigger": trigger})

                await self.sound.play()
                await self.event_bus.publish(
                    "ui.overlay",
                    {"visible": True, "duration_ms": self.settings.get("startup.overlay_duration_ms", 4200)},
                    source="ui",
                )

                if self.settings.get("voice.speak_on_startup", True):
                    await self.speaker.say(self.settings.get("assistant.greeting", "Система активирована."))

                if self.settings.get("startup.launch_workspace_on_activation", True):
                    launch_results = await self.workspace.launch_workspace("coding")

                if self.settings.get("music.play_on_activation", True):
                    await self.music.play_default()

                if self.settings.get("voice.speak_on_startup", True):
                    await self.speaker.say(self.settings.get("assistant.ready_phrase", "Готово."))

                await self.event_bus.publish("jarvis.activation_completed", {"trigger": trigger, "workspace": launch_results})
                return {"status": "completed", "workspace": launch_results}
            except Exception as exc:
                await self.event_bus.publish(
                    "jarvis.activation_failed",
                    {"trigger": trigger, "detail": str(exc)},
                    level="error",
                )
                return {"status": "failed", "detail": str(exc), "workspace": launch_results}
            finally:
                self._active = False

    async def handle_text_command(self, text: str) -> dict[str, Any]:
        decision_context = self.decision_engine.decide(text)
        await self.memory_service.remember_short_term("user", text)

        if decision_context.needs_memory:
            await self.memory_service.remember_fact("last_user_request", text)

        if decision_context.needs_internet:
            await self.event_bus.publish("jarvis.decision", {"reason": "internet", "text": text}, source="core")
            search_result = await self._answer_with_internet(text)
            return {
                "intent": "internet.search",
                "confidence": 0.95,
                "response": search_result.get("answer", "Я не зміг знайти інформацію.").strip(),
                "result": search_result,
            }

        if decision_context.needs_planning:
            plan = self.planner.build_plan(text)
            await self.event_bus.publish("jarvis.plan", plan.to_dict(), source="core")

        if decision_context.needs_skill:
            skill = self.skill_manager.select_skill(text)
            await self.event_bus.publish(
                "jarvis.skill_selected",
                {"skill": skill.name if skill else None, "reason": decision_context.reason},
                source="core",
            )

        if self._looks_like_operator_task(text) and not self._looks_like_immediate_action(text):
            task = await self.task_manager.create_task(text)
            await self.memory.remember_command(text, "task.create", 0.93)
            await self.event_bus.publish(
                "ai.intent",
                {
                    "text": text,
                    "intent": "task.create",
                    "confidence": 0.93,
                    "source": "operator-router",
                    "args": {"task_id": task["id"]},
                },
                source="ai",
            )
            response = f"Task #{task['id']} создан. Агент: {task['agent']}. Выполнение запущено."
            await self.event_bus.publish(
                "ai.response",
                {"text": response, "intent": "task.create", "source": "operator-router"},
                source="ai",
            )
            return {"intent": "task.create", "confidence": 0.93, "response": response, "task": task}

        decision = await self.brain.decide(text, available_tools=self.tools.describe())
        intent = decision.intent
        await self.memory.remember_command(text, intent.action, decision.confidence)
        await self.event_bus.publish(
            "ai.intent",
            {
                "text": text,
                "intent": intent.action,
                "confidence": decision.confidence,
                "source": decision.source,
                "args": intent.args,
            },
            source="ai",
        )

        if intent.action == "task.create":
            request = str(intent.args.get("request") or text)
            task = await self.task_manager.create_task(request)
            result = {"task": task}
            final_response = decision.response or f"Task #{task['id']} создан. Агент: {task['agent']}. Выполнение запущено."
        elif intent.action == "agent.tool_calls":
            result = await self._execute_agent_tool_calls(intent.args.get("tool_calls", []))
            final_response = self._tool_result_response(decision.response, result)
        else:
            result = await self.actions.execute(intent)
            final_response = decision.response

        final_response = self.character.influence(
            final_response,
            context={
                "needs_planning": decision_context.needs_planning,
                "needs_skill": decision_context.needs_skill,
            },
        )
        await self.event_bus.publish(
            "ai.response",
            {"text": final_response, "intent": intent.action, "source": decision.source},
            source="ai",
        )
        if self.settings.get("voice.speak_command_responses", True):
            if intent.action == "music.play":
                await self._speak_safely(final_response)
            else:
                self._speak_background(final_response)
        return {"intent": intent.action, "confidence": decision.confidence, "response": final_response, "result": result}

    async def enable_mode(self, mode: str) -> dict[str, Any]:
        return await self.actions.enable_mode(mode)

    async def status(self) -> dict[str, Any]:
        return {
            "name": self.settings.assistant_name,
            "active": self._active,
            "clap": self.clap_detector.status(),
            "stats": self.stats.snapshot(),
            "recent_commands": await self.memory.recent_commands(limit=8),
            "music": await self.music.status(),
            "tasks": {
                "running": len(self.task_manager._running),
                "recent": await self.task_manager.list_tasks(limit=5),
            },
            "telegram": self.telegram.status(),
            "security": {
                "mode": str(self.settings.get("security.mode", self.settings.get("tools.access_mode", "developer"))),
                "allowed_roots": self.settings.get("tools.allowed_roots", ["."]),
            },
        }

    async def models_status(self) -> dict[str, Any]:
        return await self.brain.gateway.describe()

    async def test_model_provider(self, provider: str) -> dict[str, Any]:
        return await self.brain.gateway.test_provider(provider)

    async def select_model(self, provider: str, model: str) -> dict[str, Any]:
        result = self.brain.gateway.select_model(provider, model)
        await self.event_bus.publish("ai.model_selected", result, source="ai", level="warning" if not result.get("ok") else "info")
        return result

    async def clear_model_selection(self) -> dict[str, Any]:
        result = self.brain.gateway.clear_model_selection()
        await self.event_bus.publish("ai.model_selection_cleared", result, source="ai")
        return result

    async def create_task(self, request: str, title: str | None = None, agent: str | None = None) -> dict[str, Any]:
        return await self.task_manager.create_task(request, title=title, agent_hint=agent)

    async def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self.task_manager.list_tasks(limit=limit)

    async def get_task(self, task_id: int) -> dict[str, Any] | None:
        return await self.task_manager.get_task(task_id)

    async def cancel_task(self, task_id: int) -> dict[str, Any]:
        return await self.task_manager.cancel_task(task_id)

    def agents_status(self) -> list[dict[str, object]]:
        return self.agents.describe()

    def tools_status(self) -> list[dict[str, Any]]:
        return self.tools.describe()

    async def execute_tool(self, tool: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.tools.execute(tool, action, payload)

    async def list_memory(self, section: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return await self.memory.list_memory(section=section, limit=limit)

    async def remember_memory(
        self,
        section: str,
        key: str,
        value: Any,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self.memory.remember_memory(section, key, value, tags=tags)

    async def search_memory(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return await self.memory.search_memory(query, limit=limit)

    def notifications(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in reversed(self.event_bus.history)]

    async def telegram_test(self) -> dict[str, Any]:
        return await self.telegram.test()

    async def _answer_with_internet(self, query: str) -> dict[str, object]:
        try:
            result = await self.internet.answer(
                query,
                gateway=self.brain.gateway,
                system_prompt=str(self.settings.get("ai.system_prompt", "")),
            )
            return {
                "ok": True,
                "query": query,
                "answer": str(result.get("answer") or result.get("summary") or "").strip(),
                "summary": str(result.get("summary") or "").strip(),
                "sources": result.get("sources", []),
                "data": result,
            }
        except Exception as exc:
            await self.event_bus.publish("jarvis.internet_failed", {"query": query, "error": str(exc)}, source="core", level="error")
            return {
                "ok": False,
                "query": query,
                "answer": "Не вдалося отримати відповідь з інтернету.",
                "summary": "Не вдалося отримати відповідь з інтернету.",
                "error": str(exc),
            }

    async def _execute_agent_tool_calls(self, raw_calls: object) -> dict[str, Any]:
        calls = raw_calls if isinstance(raw_calls, list) else []
        max_calls = int(self.settings.get("ai.max_tool_calls_per_request", 5))
        results: list[dict[str, Any]] = []
        for raw in calls[:max_calls]:
            if not isinstance(raw, dict):
                continue
            tool = str(raw.get("tool") or "").strip()
            action = str(raw.get("action") or "").strip()
            payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
            if not tool or not action:
                continue
            await self.event_bus.publish(
                "ai.tool_call",
                {"tool": tool, "action": action, "payload": payload},
                source="ai",
            )
            tool_result = await self.tools.execute(tool, action, payload)
            results.append(
                {
                    "tool": tool,
                    "action": action,
                    "payload": payload,
                    "ok": bool(tool_result.get("ok")),
                    "result": tool_result,
                }
            )
            if not tool_result.get("ok"):
                break
        return {"ok": bool(results) and all(item["ok"] for item in results), "calls": results}

    def _tool_result_response(self, planned_response: str, result: dict[str, Any]) -> str:
        calls = result.get("calls") if isinstance(result.get("calls"), list) else []
        if not calls:
            return planned_response or self._localized("Действие не выполнено.", "Дію не виконано.", "Action was not executed.")
        failed = next((call for call in calls if not call.get("ok")), None)
        if failed:
            details = failed.get("result") if isinstance(failed.get("result"), dict) else {}
            reason = str(details.get("reason") or details.get("stderr") or details.get("detail") or "tool_failed")
            if details.get("requires_confirmation"):
                return self._localized(
                    f"Нужно подтверждение: {reason}.",
                    f"Потрібне підтвердження: {reason}.",
                    f"Confirmation required: {reason}.",
                )
            return self._localized(
                f"Не получилось выполнить действие: {reason}.",
                f"Не вдалося виконати дію: {reason}.",
                f"Could not execute the action: {reason}.",
            )

        last = calls[-1]
        payload = last.get("payload") if isinstance(last.get("payload"), dict) else {}
        output = last.get("result") if isinstance(last.get("result"), dict) else {}
        path = str(output.get("path") or payload.get("path") or "").strip()
        if last.get("tool") == "filesystem" and last.get("action") == "mkdir" and path:
            return self._localized(f"Готово. Папка создана: {path}", f"Готово. Папку створено: {path}", f"Done. Folder created: {path}")
        if last.get("tool") == "filesystem" and last.get("action") == "write" and path:
            return self._localized(f"Готово. Файл создан: {path}", f"Готово. Файл створено: {path}", f"Done. File created: {path}")
        return planned_response or self._localized("Готово.", "Готово.", "Done.")

    def _localized(self, ru: str, uk: str, en: str) -> str:
        locale = str(self.settings.get("assistant.locale", "ru-RU")).lower()
        if locale.startswith("uk"):
            return uk
        if locale.startswith("en"):
            return en
        return ru

    @staticmethod
    def _looks_like_immediate_action(text: str) -> bool:
        normalized = text.lower().replace("ё", "е")
        immediate_markers = (
            "папк",
            "папочк",
            "директор",
            "каталог",
            "folder",
            "directory",
            "файл",
            "file",
            "диск",
            "диску",
            "desktop",
            "рабоч",
            "робоч",
            "открой",
            "відкрий",
            "open ",
            "запусти команду",
            "выполни команду",
            "run command",
        )
        return any(marker in normalized for marker in immediate_markers)

    @staticmethod
    def _looks_like_operator_task(text: str) -> bool:
        normalized = text.lower().replace("ё", "е")
        if JarvisOrchestrator._looks_like_immediate_action(text):
            return False
        task_markers = (
            "создай",
            "сделай проект",
            "сделай приложение",
            "напиши проект",
            "напиши приложение",
            "проанализируй проект",
            "подготовь деплой",
            "напиши документацию",
            "автоматизируй",
            "работай автономно",
            "створи",
            "зроби проект",
            "зроби проєкт",
            "зроби застосунок",
            "напиши проект",
            "напиши проєкт",
            "проаналізуй проект",
            "проаналізуй проєкт",
            "підготуй деплой",
            "напиши документацію",
            "автоматизуй",
            "працюй автономно",
            "create project",
            "create app",
            "build app",
            "build project",
            "analyze project",
            "prepare deploy",
            "write documentation",
            "work autonomously",
        )
        return len(normalized) > 24 and any(marker in normalized for marker in task_markers)

    def _speak_background(self, text: str) -> None:
        task = asyncio.create_task(self.speaker.say(text), name="jarvis.tts.response")
        self._speech_tasks.add(task)
        task.add_done_callback(self._finish_speech_task)

    async def _speak_safely(self, text: str) -> None:
        try:
            await self.speaker.say(text)
        except Exception as exc:
            await self.event_bus.publish(
                "voice.tts.failed",
                {"detail": str(exc)},
                source="voice",
                level="error",
            )

    def _finish_speech_task(self, task: asyncio.Task[None]) -> None:
        self._speech_tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            asyncio.create_task(
                self.event_bus.publish(
                    "voice.tts.failed",
                    {"detail": str(exc)},
                    source="voice",
                    level="error",
                )
            )
