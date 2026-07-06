from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod

from config import Settings
from core.events import EventBus


class Transcriber(ABC):
    @abstractmethod
    async def listen_once(self, seconds: float | None = None) -> str:
        raise NotImplementedError


class VoskTranscriber(Transcriber):
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus

    async def listen_once(self, seconds: float | None = None) -> str:
        return await asyncio.to_thread(self._listen_blocking, seconds)

    def _listen_blocking(self, seconds: float | None = None) -> str:
        import pyaudio
        from vosk import KaldiRecognizer, Model

        model_path = str(self.settings.path("voice.vosk_model_path", "models/vosk"))
        sample_rate = int(self.settings.get("clap.sample_rate", 16000))
        listen_seconds = seconds or float(self.settings.get("voice.command_listening_seconds", 7))

        model = Model(model_path)
        recognizer = KaldiRecognizer(model, sample_rate)
        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            frames_per_buffer=4000,
        )
        chunks = int(sample_rate / 4000 * listen_seconds)
        try:
            for _ in range(max(chunks, 1)):
                data = stream.read(4000, exception_on_overflow=False)
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    if result.get("text"):
                        return str(result["text"])
            return str(json.loads(recognizer.FinalResult()).get("text", ""))
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()


class WhisperTranscriber(Transcriber):
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus

    async def listen_once(self, seconds: float | None = None) -> str:
        await self.event_bus.publish(
            "voice.stt.whisper_pending",
            {"seconds": seconds or self.settings.get("voice.command_listening_seconds", 7)},
            source="voice",
        )
        return ""
