from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from ai.gateway import AIGateway, AIMessage
from config import Settings
from core.commands import CommandIntent, VoiceCommandRouter
from memory.store import MemoryStore


@dataclass(slots=True)
class BrainDecision:
    intent: CommandIntent
    response: str
    source: str
    confidence: float
    context: dict[str, Any] = field(default_factory=dict)


class JarvisBrain:
    def __init__(self, settings: Settings, memory: MemoryStore, router: VoiceCommandRouter) -> None:
        self.settings = settings
        self.memory = memory
        self.router = router
        self.gateway = AIGateway(settings)

    async def decide(self, text: str, *, available_tools: list[dict[str, Any]] | None = None) -> BrainDecision:
        intent = self.router.parse(text)
        if intent.action != "ai.chat" and intent.confidence >= float(self.settings.get("ai.local_intent_threshold", 0.58)):
            return BrainDecision(
                intent=intent,
                response=self._response_for_intent(intent),
                source="local-intent",
                confidence=intent.confidence,
            )

        local_tool_decision = self._local_tool_plan(text, available_tools or [])
        if local_tool_decision:
            return local_tool_decision

        if available_tools and self.settings.get("ai.agentic_commands", True):
            tool_decision = await self._provider_tool_plan(text, available_tools)
            if tool_decision:
                return tool_decision

        provider_response = await self._provider_chat(text)
        if provider_response:
            return BrainDecision(
                intent=intent,
                response=provider_response,
                source="ai-provider",
                confidence=intent.confidence,
            )

        return BrainDecision(
            intent=intent,
            response=self._fallback_response(text),
            source="fallback",
            confidence=intent.confidence,
        )

    async def _provider_chat(self, text: str) -> str | None:
        recent = await self.memory.recent_commands(limit=5)
        recent_text = "\n".join(f"- {item['text']} -> {item['intent']}" for item in recent)
        messages = [
            AIMessage(role="system", content=str(self.settings.get("ai.system_prompt", ""))),
            AIMessage(
                role="user",
                content=(
                    "Ответь как desktop assistant JARVIS: кратко, уверенно и по делу. "
                    "Понимай русский, украинский и английский; отвечай на языке текущей команды. "
                    "Не изображай выполнение действия, если оно не было запрошено как команда. "
                    "Доступные модули: локальная музыка, workspace launcher, focus/night/gaming modes, системные команды.\n"
                    f"Недавние команды:\n{recent_text or '- none'}\n"
                    f"Текущая команда: {text}"
                ),
            ),
        ]
        try:
            result = await self.gateway.chat(messages, task_type=self.gateway.classify_task(text))
        except Exception:
            return None
        return result.text if result and result.text else None

    async def _provider_tool_plan(
        self,
        text: str,
        available_tools: list[dict[str, Any]],
    ) -> BrainDecision | None:
        tool_context = [
            {
                "name": tool.get("name"),
                "description": tool.get("description"),
                "actions": tool.get("actions", []),
                "access": tool.get("access"),
            }
            for tool in available_tools
            if tool.get("enabled", True)
        ]
        recent = await self.memory.recent_commands(limit=5)
        recent_text = "\n".join(f"- {item['text']} -> {item['intent']}" for item in recent)
        messages = [
            AIMessage(
                role="system",
                content=(
                    "You are the JARVIS action planner. Return only one JSON object, no markdown. "
                    "Schema: {\"mode\":\"chat|tools|task\", \"response\":\"short user-facing answer\", "
                    "\"confidence\":0.0, \"tool_calls\":[{\"tool\":\"filesystem\", \"action\":\"mkdir\", "
                    "\"payload\":{}}], \"task\":{\"request\":\"optional long task\"}}. "
                    "Use tools when the user asks to perform a local action: create folders/files, read/write files, "
                    "run terminal commands, open URLs/apps, use git/docker/vscode/telegram. "
                    "For a folder request use filesystem mkdir with payload {\"path\":\"...\", "
                    "\"parents\":true, \"exist_ok\":true}. "
                    "For a file request use filesystem write with payload {\"path\":\"...\", \"content\":\"...\", "
                    "\"create_parents\":true}. "
                    "For relative paths, use paths relative to the JARVIS workspace. "
                    "Do not call delete, shutdown, format, git reset, or other destructive actions unless the user "
                    "explicitly asks and confirms. If confirmation is missing, use mode chat and ask one short question. "
                    "For ordinary conversation or questions, use mode chat and answer directly in response. "
                    "Respond in the language of the user."
                ),
            ),
            AIMessage(
                role="user",
                content=(
                    f"Available tools JSON:\n{json.dumps(tool_context, ensure_ascii=False)}\n\n"
                    f"Recent commands:\n{recent_text or '- none'}\n\n"
                    f"User request:\n{text}"
                ),
            ),
        ]
        try:
            result = await self.gateway.chat(messages, task_type=self.gateway.classify_task(text), temperature=0.1)
        except Exception:
            return None
        if not result or not result.text:
            return None

        data = self._parse_json_object(result.text)
        if not data:
            return None

        mode = str(data.get("mode") or "chat").lower()
        confidence = self._coerce_confidence(data.get("confidence"), default=0.72)
        response = str(data.get("response") or "").strip()

        if mode == "tools":
            tool_calls = self._validated_tool_calls(data.get("tool_calls"), available_tools)
            if not tool_calls:
                return None
            return BrainDecision(
                intent=CommandIntent(
                    "agent.tool_calls",
                    confidence=confidence,
                    args={"tool_calls": tool_calls, "model": result.model, "provider": result.provider},
                    original_text=text,
                ),
                response=response or self._generic_action_response(text),
                source="ai-tool-planner",
                confidence=confidence,
                context={"provider": result.provider, "model": result.model, "tool_calls": tool_calls},
            )

        if mode == "task" and isinstance(data.get("task"), dict):
            request = str(data["task"].get("request") or text).strip()
            return BrainDecision(
                intent=CommandIntent(
                    "task.create",
                    confidence=confidence,
                    args={"request": request, "provider": result.provider, "model": result.model},
                    original_text=text,
                ),
                response=response or self._generic_action_response(text),
                source="ai-task-planner",
                confidence=confidence,
                context={"provider": result.provider, "model": result.model},
            )

        if mode == "chat" and response:
            return BrainDecision(
                intent=CommandIntent("ai.chat", confidence=confidence, args={"text": text}, original_text=text),
                response=response,
                source="ai-planner-chat",
                confidence=confidence,
                context={"provider": result.provider, "model": result.model},
            )
        return None

    def _local_tool_plan(
        self,
        text: str,
        available_tools: list[dict[str, Any]],
    ) -> BrainDecision | None:
        if not available_tools:
            return None
        allowed = self._tool_action_map(available_tools)
        if allowed and "filesystem" not in allowed:
            return None

        normalized = text.lower().replace("ё", "е")
        create_words = (
            "создай",
            "создать",
            "сделай",
            "сделать",
            "створи",
            "зроби",
            "create",
            "make",
        )
        if not any(word in normalized for word in create_words):
            return None

        folder_words = ("папк", "директор", "каталог", "folder", "directory")
        if any(word in normalized for word in folder_words):
            path = self._extract_requested_path(text, r"папк\w*|директор\w*|каталог\w*|folder|directory")
            if not path:
                return None
            path = self._apply_location_hint(path, text)
            tool_calls = [{"tool": "filesystem", "action": "mkdir", "payload": {"path": path, "parents": True, "exist_ok": True}}]
            return BrainDecision(
                intent=CommandIntent("agent.tool_calls", confidence=0.93, args={"tool_calls": tool_calls}, original_text=text),
                response=self._localized_action_response(text, f"Создаю папку {path}.", f"Створюю папку {path}.", f"Creating folder {path}."),
                source="local-tool-heuristic",
                confidence=0.93,
                context={"tool_calls": tool_calls},
            )

        file_words = ("файл", "file")
        if any(word in normalized for word in file_words):
            path = self._extract_requested_path(text, r"файл\w*|file")
            if not path:
                return None
            content = self._extract_file_content(text)
            path = self._apply_location_hint(path, text)
            tool_calls = [
                {
                    "tool": "filesystem",
                    "action": "write",
                    "payload": {"path": path, "content": content, "create_parents": True},
                }
            ]
            return BrainDecision(
                intent=CommandIntent("agent.tool_calls", confidence=0.9, args={"tool_calls": tool_calls}, original_text=text),
                response=self._localized_action_response(text, f"Создаю файл {path}.", f"Створюю файл {path}.", f"Creating file {path}."),
                source="local-tool-heuristic",
                confidence=0.9,
                context={"tool_calls": tool_calls},
            )

        return None

    @staticmethod
    def _validated_tool_calls(raw_calls: Any, available_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = JarvisBrain._tool_action_map(available_tools)
        if not allowed:
            return []
        calls = raw_calls if isinstance(raw_calls, list) else []
        validated: list[dict[str, Any]] = []
        for raw in calls[:5]:
            if not isinstance(raw, dict):
                continue
            tool = str(raw.get("tool") or "").strip()
            action = str(raw.get("action") or "").strip()
            if "." in tool and not action:
                tool, action = tool.split(".", 1)
            payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
            if tool in allowed and action in allowed[tool]:
                validated.append({"tool": tool, "action": action, "payload": payload})
        return validated

    @staticmethod
    def _tool_action_map(available_tools: list[dict[str, Any]]) -> dict[str, set[str]]:
        return {
            str(tool.get("name")): {str(action) for action in tool.get("actions", [])}
            for tool in available_tools
            if tool.get("name") and tool.get("enabled", True)
        }

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```$", "", stripped)
        candidates = [stripped]
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            candidates.append(stripped[start : end + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _coerce_confidence(value: Any, *, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _extract_requested_path(text: str, target_regex: str) -> str | None:
        named_path = JarvisBrain._extract_named_location_path(text)
        if named_path:
            return named_path

        match = re.search(
            rf"(?:{target_regex})(?:\s+(?:с\s+именем|под\s+названием|з\s+назвою|named|called))?\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            raw = match.group(1)
            named_path = JarvisBrain._extract_named_location_path(raw)
            if named_path:
                return named_path
            return JarvisBrain._clean_path_candidate(raw)
        quoted = re.search(r"[\"'«“](.+?)[\"'»”]", text)
        if quoted:
            return JarvisBrain._clean_path_candidate(quoted.group(1))
        return None

    @staticmethod
    def _extract_named_location_path(text: str) -> str | None:
        name_match = re.search(
            r"(?:с\s+именем|под\s+названием|назови|з\s+назвою|із\s+назвою|named|called)\s+[\"'«“]?(.+?)[\"'»”]?$",
            text,
            flags=re.IGNORECASE,
        )
        if not name_match:
            return None
        name = JarvisBrain._clean_path_candidate(name_match.group(1))
        if not name:
            return None

        drive_match = re.search(
            r"(?:\bна\s+|\bв\s+)?(?:диск[а-яіїєґ]*|drive)\s*([a-zA-Z])\b|\bна\s+([a-zA-Z])\b",
            text,
            flags=re.IGNORECASE,
        )
        if drive_match:
            drive = (drive_match.group(1) or drive_match.group(2) or "").upper()
            if drive:
                return f"{drive}:/{name}"
        return name

    @staticmethod
    def _clean_path_candidate(candidate: str) -> str | None:
        cleaned = candidate.strip().strip(" \"'«»“”").rstrip(".,!?:;")
        cleaned = re.split(
            r"\s+(?:с\s+текстом|із\s+текстом|з\s+текстом|with\s+text|на\s+рабочем\s+столе|на\s+робочому\s+столі|on\s+desktop|in\s+desktop)\b",
            cleaned,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        cleaned = re.sub(r"\b(?:пожалуйста|будь\s+ласка|please)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip().strip(" \"'«»“”").rstrip(".,!?:;")
        return cleaned or None

    @staticmethod
    def _apply_location_hint(path: str, text: str) -> str:
        normalized = text.lower().replace("ё", "е")
        if re.match(r"^[a-zA-Z]:[\\/]", path) or path.startswith("\\\\") or path.startswith("%"):
            return path

        location_markers: list[tuple[tuple[str, ...], str]] = [
            (("рабочем столе", "рабочий стол", "робочому столі", "робочий стіл", "desktop", "десктоп"), "%USERPROFILE%/Desktop"),
            (("documents", "document", "документы", "документи", "документ", "мои документы", "мої документи"), "%USERPROFILE%/Documents"),
            (("downloads", "download", "загрузки", "завантаження", "завантаженнями", "скачки"), "%USERPROFILE%/Downloads"),
            (("pictures", "picture", "images", "images folder", "фото", "зображення"), "%USERPROFILE%/Pictures"),
            (("music", "музыка", "музику", "музика"), "%USERPROFILE%/Music"),
            (("videos", "video", "видео", "відео"), "%USERPROFILE%/Videos"),
        ]
        for markers, base in location_markers:
            if any(marker in normalized for marker in markers):
                return f"{base}/{path}"
        return path

    @staticmethod
    def _extract_file_content(text: str) -> str:
        quoted_after_text = re.search(
            r"(?:с\s+текстом|із\s+текстом|з\s+текстом|with\s+text)\s+[\"'«“](.+?)[\"'»”]",
            text,
            flags=re.IGNORECASE,
        )
        if quoted_after_text:
            return quoted_after_text.group(1)
        after_marker = re.search(
            r"(?:с\s+текстом|із\s+текстом|з\s+текстом|with\s+text)\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        return after_marker.group(1).strip() if after_marker else ""

    @staticmethod
    def _generic_action_response(text: str) -> str:
        return JarvisBrain._localized_action_response(text, "Выполняю действие.", "Виконую дію.", "Executing.")

    @staticmethod
    def _localized_action_response(text: str, ru: str, uk: str, en: str) -> str:
        language = JarvisBrain._detect_language(text)
        return {"ru": ru, "uk": uk, "en": en}[language]

    @staticmethod
    def _response_for_intent(intent: CommandIntent) -> str:
        language = JarvisBrain._detect_language(intent.original_text)
        responses = {
            "ru": {
                "mode.coding": "Запускаю рабочий режим.",
                "project.open": "Открываю проект.",
                "music.play": "Включаю локальную музыкальную библиотеку.",
                "music.pause": "Приостанавливаю воспроизведение.",
                "music.resume": "Продолжаю воспроизведение.",
                "music.stop": "Останавливаю музыку.",
                "music.volume": "Настраиваю громкость.",
                "mode.focus": "Включаю focus mode.",
                "mode.gaming": "Готовлю игровой режим.",
                "mode.night": "Перехожу в ночной режим.",
                "app.open": "Открываю приложение.",
                "system.shutdown": "Команда выключения проверяется.",
                "server.start": "Запускаю сервер.",
            },
            "uk": {
                "mode.coding": "Запускаю робочий режим.",
                "project.open": "Відкриваю проєкт.",
                "music.play": "Увімкнув локальну музичну бібліотеку.",
                "music.pause": "Призупиняю відтворення.",
                "music.resume": "Продовжую відтворення.",
                "music.stop": "Зупиняю музику.",
                "music.volume": "Налаштовую гучність.",
                "mode.focus": "Вмикаю focus mode.",
                "mode.gaming": "Готую ігровий режим.",
                "mode.night": "Переходжу в нічний режим.",
                "app.open": "Відкриваю застосунок.",
                "system.shutdown": "Команда вимкнення перевіряється.",
                "server.start": "Запускаю сервер.",
            },
            "en": {
                "mode.coding": "Starting work mode.",
                "project.open": "Opening the project.",
                "music.play": "Starting the local music library.",
                "music.pause": "Pausing playback.",
                "music.resume": "Resuming playback.",
                "music.stop": "Stopping music.",
                "music.volume": "Adjusting volume.",
                "mode.focus": "Enabling focus mode.",
                "mode.gaming": "Preparing gaming mode.",
                "mode.night": "Switching to night mode.",
                "app.open": "Opening the app.",
                "system.shutdown": "Checking the shutdown command.",
                "server.start": "Starting the server.",
            },
        }
        return responses[language].get(intent.action, {"ru": "Выполняю.", "uk": "Виконую.", "en": "Executing."}[language])

    @staticmethod
    def _fallback_response(text: str) -> str:
        language = JarvisBrain._detect_language(text)
        return {
            "ru": "Команда не распознана. Уточните действие.",
            "uk": "Команду не розпізнано. Уточни дію.",
            "en": "I did not recognize the command. Please clarify the action.",
        }[language]

    @staticmethod
    def _detect_language(text: str) -> str:
        normalized = text.lower()
        if re.search(r"[іїєґ]", normalized) or any(
            word in normalized
            for word in (
                "відкрий",
                "увімкни",
                "вимкни",
                "гучність",
                "проєкт",
                "робочий",
                "нічний",
                "ігровий",
                "музику",
            )
        ):
            return "uk"
        if re.search(r"[а-яё]", normalized):
            return "ru"
        return "en"
