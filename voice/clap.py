from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from config import Settings
from core.events import EventBus


DoubleClapCallback = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class ClapMetrics:
    energy: float
    peak: float
    sharpness: float
    noise_floor: float


class ClapDetector:
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.running = False
        self.available = False
        self.last_error: str | None = None
        self.noise_floor = 0.0
        self.last_metrics: ClapMetrics | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = False
        self._callback: DoubleClapCallback | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self, callback: DoubleClapCallback) -> None:
        if self.running:
            return
        self._callback = callback
        self._loop = asyncio.get_running_loop()
        self._stop = False
        self._task = asyncio.create_task(asyncio.to_thread(self._listen_blocking), name="jarvis.clap")
        self.running = True
        await self.event_bus.publish("clap.listener_started", self.status(), source="voice")

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self.running = False
        await self.event_bus.publish("clap.listener_stopped", self.status(), source="voice")

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "available": self.available,
            "last_error": self.last_error,
            "threshold": self.settings.get("clap.energy_threshold", 0.68),
            "noise_floor": round(self.noise_floor, 5),
            "last_metrics": None if self.last_metrics is None else self.last_metrics.__dict__,
        }

    def _listen_blocking(self) -> None:
        try:
            import numpy as np
            import pyaudio
        except Exception as exc:  # pragma: no cover - depends on host audio stack
            self.available = False
            self.last_error = f"Audio stack unavailable: {exc}"
            self.running = False
            self._publish_threadsafe("clap.unavailable", self.status())
            return

        audio = pyaudio.PyAudio()
        stream = None
        try:
            sample_rate = int(self.settings.get("clap.sample_rate", 44100))
            chunk_size = int(self.settings.get("clap.chunk_size", 1024))
            device_index = self.settings.get("clap.device_index")
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk_size,
            )
            self.available = True
            self._publish_threadsafe("clap.calibration_started", {"seconds": self.settings.get("clap.calibration_seconds", 2.5)})
            noise_floor = self._calibrate(stream, np, sample_rate, chunk_size)
            self.noise_floor = noise_floor
            self._publish_threadsafe("clap.calibration_completed", {"noise_floor": noise_floor})
            self._detect_loop(stream, np, sample_rate, noise_floor)
        except Exception as exc:  # pragma: no cover - hardware dependent
            self.available = False
            self.last_error = str(exc)
            self._publish_threadsafe("clap.error", self.status())
        finally:
            self.running = False
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            audio.terminate()

    def _calibrate(self, stream: Any, np: Any, sample_rate: int, chunk_size: int) -> float:
        end_at = time.monotonic() + float(self.settings.get("clap.calibration_seconds", 2.5))
        samples: list[float] = []
        while time.monotonic() < end_at and not self._stop:
            data = stream.read(chunk_size, exception_on_overflow=False)
            metrics = self._metrics(data, np)
            samples.append(metrics.energy)
        if not samples:
            return 0.03
        samples.sort()
        index = min(len(samples) - 1, math.floor(len(samples) * 0.8))
        return max(0.02, samples[index])

    def _detect_loop(self, stream: Any, np: Any, sample_rate: int, noise_floor: float) -> None:
        threshold = float(self.settings.get("clap.energy_threshold", 0.68))
        adaptive = bool(self.settings.get("clap.adaptive_noise_floor", True))
        min_peak_distance = float(self.settings.get("clap.min_peak_distance_ms", 140)) / 1000
        double_window = float(self.settings.get("clap.double_clap_window_ms", 650)) / 1000
        cooldown = float(self.settings.get("clap.cooldown_ms", 2500)) / 1000

        claps: list[float] = []
        last_peak_at = 0.0
        cooldown_until = 0.0
        chunk_size = int(self.settings.get("clap.chunk_size", 1024))

        while not self._stop:
            data = stream.read(chunk_size, exception_on_overflow=False)
            now = time.monotonic()
            metrics = self._metrics(data, np, noise_floor)
            self.last_metrics = metrics
            dynamic_threshold = max(threshold, noise_floor * 4.5)

            if adaptive and metrics.energy < dynamic_threshold * 0.55:
                noise_floor = (noise_floor * 0.98) + (metrics.energy * 0.02)
                self.noise_floor = noise_floor

            is_clap = (
                now >= cooldown_until
                and now - last_peak_at >= min_peak_distance
                and metrics.energy >= dynamic_threshold
                and metrics.peak >= dynamic_threshold * 1.15
                and metrics.sharpness >= dynamic_threshold * 0.85
                and metrics.peak / max(metrics.energy, 0.0001) >= 2.2
            )

            if is_clap:
                last_peak_at = now
                claps = [stamp for stamp in claps if now - stamp <= double_window]
                claps.append(now)
                self._publish_threadsafe("clap.detected", {"count": len(claps), **metrics.__dict__})
                if len(claps) >= 2:
                    claps.clear()
                    cooldown_until = now + cooldown
                    self._publish_threadsafe("clap.double_detected", {"cooldown_until": cooldown_until})
                    self._fire_callback()

            sleep_for = max(0.001, chunk_size / sample_rate / 3)
            time.sleep(sleep_for)

    @staticmethod
    def _metrics(data: bytes, np: Any, noise_floor: float = 0.03) -> ClapMetrics:
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return ClapMetrics(0.0, 0.0, 0.0, noise_floor)
        diff = np.diff(samples, prepend=samples[0])
        energy = float(np.sqrt(np.mean(samples * samples)))
        peak = float(np.max(np.abs(samples)))
        sharpness = float(np.max(np.abs(diff)))
        return ClapMetrics(energy=energy, peak=peak, sharpness=sharpness, noise_floor=noise_floor)

    def _fire_callback(self) -> None:
        if not self._loop or not self._callback:
            return
        self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._callback()))

    def _publish_threadsafe(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self._loop:
            return
        self._loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.event_bus.publish(event_type, payload, source="voice"))
        )
