from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re
from typing import Any


@dataclass(slots=True)
class CommandIntent:
    action: str
    confidence: float = 1.0
    args: dict[str, Any] = field(default_factory=dict)
    original_text: str = ""


class VoiceCommandRouter:
    def __init__(self) -> None:
        self._app_aliases: dict[str, tuple[str, ...]] = {
            "telegram": ("telegram", "телеграм", "телегу", "ayugram", "аюграм"),
            "chrome": ("chrome", "хром", "браузер", "browser", "google chrome"),
            "discord": ("discord", "дискорд"),
            "vscode": ("vscode", "vs code", "visual studio code", "код", "редактор"),
            "android_studio": ("android studio", "андроид студио", "андроїд студіо"),
        }
        self._open_words = (
            "open",
            "start",
            "launch",
            "run",
            "открой",
            "запусти",
            "запустить",
            "відкрий",
            "відкрити",
            "запусти",
            "запустити",
        )
        self._rules: list[tuple[tuple[str, ...], str, dict[str, Any]]] = [
            (
                (
                    "запусти рабочий режим",
                    "рабочий режим",
                    "режим кодинга",
                    "режим кода",
                    "начни работу",
                    "почни роботу",
                    "робочий режим",
                    "режим кодування",
                    "режим кодингу",
                    "coding mode",
                    "start coding",
                    "work mode",
                    "start work",
                ),
                "mode.coding",
                {},
            ),
            (
                (
                    "открой проект",
                    "відкрий проект",
                    "відкрий проєкт",
                    "open project",
                    "open workspace",
                    "проект",
                    "проєкт",
                    "код открой",
                    "код відкрий",
                    "open code",
                ),
                "project.open",
                {},
            ),
            (
                (
                    "включи музыку",
                    "поставь музыку",
                    "увімкни музику",
                    "постав музику",
                    "запусти музику",
                    "play music",
                    "start music",
                    "music",
                    "вруби трек",
                    "включи трек",
                    "увімкни трек",
                    "запусти музыку",
                    "музыка из папки",
                    "музика з папки",
                    "локальную музыку",
                    "локальну музику",
                ),
                "music.play",
                {},
            ),
            (
                (
                    "пауза",
                    "pause",
                    "pause music",
                    "поставь на паузу",
                    "постав на паузу",
                    "приостанови музыку",
                    "призупини музику",
                ),
                "music.pause",
                {},
            ),
            (
                (
                    "останови музыку",
                    "выключи музыку",
                    "зупини музику",
                    "вимкни музику",
                    "офни музыку",
                    "оффни музыку",
                    "отключи музыку",
                    "выруби музыку",
                    "убери музыку",
                    "хватит музыку",
                    "закрой музыку",
                    "стоп музыка",
                    "офни музон",
                    "выруби музон",
                    "вируби музику",
                    "прибери музику",
                    "stop music",
                    "stop audio",
                    "turn off music",
                    "shut off music",
                    "kill music",
                    "заглуши музыку",
                    "музыку стоп",
                    "музику стоп",
                    "полностью останови музыку",
                    "повністю зупини музику",
                ),
                "music.stop",
                {},
            ),
            (
                (
                    "продолжи музыку",
                    "продовж музику",
                    "resume music",
                    "continue music",
                    "play again",
                    "продолжить воспроизведение",
                    "продовж відтворення",
                ),
                "music.resume",
                {},
            ),
            (
                (
                    "закрой лишнее",
                    "закрий зайве",
                    "focus mode",
                    "фокус",
                    "режим фокуса",
                    "режим фокусу",
                    "не отвлекать",
                    "не турбувати",
                    "do not disturb",
                ),
                "mode.focus",
                {},
            ),
            (
                (
                    "открой telegram",
                    "открой телеграм",
                    "відкрий telegram",
                    "відкрий телеграм",
                    "запусти телеграм",
                    "запусти телеграм",
                    "telegram",
                    "телеграм",
                    "ayugram",
                    "аюграм",
                ),
                "app.open",
                {"app_id": "telegram"},
            ),
            (("открой chrome", "відкрий chrome", "хром", "браузер", "open chrome", "open browser"), "app.open", {"app_id": "chrome"}),
            (("открой discord", "відкрий discord", "discord", "дискорд"), "app.open", {"app_id": "discord"}),
            (
                (
                    "открой vscode",
                    "відкрий vscode",
                    "vs code",
                    "visual studio code",
                    "код",
                    "open editor",
                    "open vscode",
                ),
                "app.open",
                {"app_id": "vscode"},
            ),
            (("android studio", "андроид студио", "андроїд студіо"), "app.open", {"app_id": "android_studio"}),
            (
                (
                    "выключи компьютер",
                    "вимкни комп ютер",
                    "shutdown",
                    "shut down",
                    "power off",
                    "turn off computer",
                    "выключение",
                    "вимкнення",
                ),
                "system.shutdown",
                {},
            ),
            (
                (
                    "запусти сервер",
                    "підніми сервер",
                    "запусти сервер",
                    "start server",
                    "run server",
                    "dev server",
                    "сервер",
                ),
                "server.start",
                {},
            ),
            (("gaming mode", "игровой режим", "ігровий режим", "режим игры", "режим гри"), "mode.gaming", {}),
            (("night mode", "ночной режим", "нічний режим", "тихий режим", "quiet mode"), "mode.night", {}),
        ]

    def parse(self, text: str) -> CommandIntent:
        if text.strip().startswith("/"):
            return CommandIntent("ai.chat", confidence=0.2, args={"text": text}, original_text=text)

        normalized = self._normalize(text)
        volume = self._parse_volume(normalized)
        if volume is not None:
            return CommandIntent("music.volume", confidence=0.92, args={"volume": volume}, original_text=text)

        app_id = self._parse_app_open(normalized)
        if app_id:
            return CommandIntent("app.open", confidence=0.9, args={"app_id": app_id}, original_text=text)

        best_action = "ai.chat"
        best_args: dict[str, Any] = {"text": text}
        best_score = 0.0

        for phrases, action, args in self._rules:
            for phrase in phrases:
                phrase_norm = self._normalize(phrase)
                if phrase_norm in normalized:
                    score = min(1.0, 0.86 + len(phrase_norm) / max(len(normalized), 1) * 0.14)
                else:
                    score = SequenceMatcher(None, normalized, phrase_norm).ratio()
                    token_overlap = self._token_overlap(normalized, phrase_norm)
                    score = max(score, token_overlap)
                if score > best_score:
                    best_score = score
                    best_action = action
                    best_args = dict(args)

        if best_score >= 0.52:
            return CommandIntent(best_action, confidence=round(best_score, 3), args=best_args, original_text=text)

        return CommandIntent("ai.chat", confidence=round(max(best_score, 0.25), 3), args={"text": text}, original_text=text)

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower().replace("ё", "е")
        text = re.sub(r"[^a-zа-яіїєґ0-9\s]", " ", text)
        return " ".join(text.split())

    def _parse_app_open(self, normalized: str) -> str | None:
        if not any(word in normalized for word in self._open_words):
            return None
        for app_id, aliases in self._app_aliases.items():
            if any(self._normalize(alias) in normalized for alias in aliases):
                return app_id
        return None

    @staticmethod
    def _token_overlap(a: str, b: str) -> float:
        a_tokens = set(a.split())
        b_tokens = set(b.split())
        if not a_tokens or not b_tokens:
            return 0.0
        return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)

    @staticmethod
    def _parse_volume(normalized: str) -> int | None:
        if not any(word in normalized for word in ("громкость", "гучність", "гучность", "volume", "sound", "звук")):
            return None
        match = re.search(r"\b(\d{1,3})\b", normalized)
        if not match:
            return None
        return max(0, min(100, int(match.group(1))))
