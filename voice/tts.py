from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from config import Settings
from core.events import EventBus


class Speaker(ABC):
    @abstractmethod
    async def say(self, text: str) -> None:
        raise NotImplementedError

    async def set_profile(self, profile: str) -> None:
        return None

    async def close(self) -> None:
        return None


class NullSpeaker(Speaker):
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    async def say(self, text: str) -> None:
        await self.event_bus.publish("voice.tts.skipped", {"text": text}, source="voice")


class Pyttsx3Speaker(Speaker):
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self._lock = asyncio.Lock()
        self._engine = None
        self._profile = "default"
        self._voice_name: str | None = None

    async def say(self, text: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._ensure_engine)
            await self.event_bus.publish(
                "voice.tts.started",
                {"text": text, "profile": self._profile, "voice": self._voice_name},
                source="voice",
            )
            await asyncio.to_thread(self._say_blocking, text)
            await self.event_bus.publish("voice.tts.completed", {"text": text}, source="voice")

    async def set_profile(self, profile: str) -> None:
        self._profile = profile
        await self.event_bus.publish("voice.profile", {"profile": profile}, source="voice")

    async def close(self) -> None:
        if self._engine is not None:
            await asyncio.to_thread(self._engine.stop)

    def _say_blocking(self, text: str) -> None:
        self._ensure_engine()

        if self._profile == "quiet":
            self._engine.setProperty("rate", int(self.settings.get("voice.pyttsx3.quiet_rate", 150)))
            self._engine.setProperty("volume", float(self.settings.get("voice.pyttsx3.quiet_volume", 0.46)))
        else:
            self._engine.setProperty("rate", int(self.settings.get("voice.pyttsx3.rate", 168)))
            self._engine.setProperty("volume", float(self.settings.get("voice.pyttsx3.volume", 0.82)))

        self._engine.say(text)
        self._engine.runAndWait()

    def _ensure_engine(self) -> None:
        if self._engine is not None:
            return
        import pyttsx3

        self._engine = pyttsx3.init()
        self._select_voice()

    def _select_voice(self) -> None:
        if self._engine is None:
            return
        preferred = [str(item).lower() for item in self.settings.get("voice.pyttsx3.preferred_voice_keywords", [])]
        try:
            voices = list(self._engine.getProperty("voices") or [])
        except Exception:
            voices = []

        selected = None
        if preferred:
            for voice in voices:
                haystack = f"{getattr(voice, 'name', '')} {getattr(voice, 'id', '')}".lower()
                if any(keyword in haystack for keyword in preferred):
                    selected = voice
                    break

        if selected is None and voices:
            selected = voices[0]

        if selected is not None:
            self._engine.setProperty("voice", selected.id)
            self._voice_name = getattr(selected, "name", None) or str(selected.id)


class ElevenLabsSpeaker(Speaker):
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus

    async def say(self, text: str) -> None:
        await self.event_bus.publish(
            "voice.tts.external_pending",
            {"text": text, "provider": "elevenlabs"},
            source="voice",
        )
        # Production hook: call ElevenLabs streaming TTS and play the received audio.


def create_speaker(settings: Settings, event_bus: EventBus) -> Speaker:
    engine = str(settings.get("voice.tts_engine", "pyttsx3")).lower()
    if engine == "elevenlabs":
        return ElevenLabsSpeaker(settings, event_bus)
    if engine == "none":
        return NullSpeaker(event_bus)
    return Pyttsx3Speaker(settings, event_bus)
