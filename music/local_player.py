from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from config import Settings
from core.events import EventBus


class MusicPlayerError(RuntimeError):
    pass


@dataclass(slots=True)
class Track:
    path: Path
    score: float

    @property
    def title(self) -> str:
        return self.path.stem.replace("_", " ").strip()


class LocalMusicPlayer:
    """Small Windows-first local music controller.

    It uses the native MCI media API on Windows, so the assistant can play/pause/resume
    local MP3 files without opening a browser or requiring Spotify credentials.
    """

    DEFAULT_EXTENSIONS = (".mp3", ".wav", ".m4a", ".wma", ".aac", ".flac")

    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self._lock = asyncio.Lock()
        self._thread_lock = threading.RLock()
        self._alias = "jarvis_music"
        self._current: Path | None = None
        self._external_fallback = False
        self._volume = int(self.settings.get("music.volume", 72))

    async def play_default(self) -> dict[str, Any]:
        query = str(
            self.settings.get("music.default_query")
            or self.settings.get("music.default_track_name")
            or "Should I Stay Or Should I Go"
        )
        return await self.play_query(query)

    async def play_focus_playlist(self) -> dict[str, Any]:
        query = str(self.settings.get("music.focus_query") or self.settings.get("music.default_query") or "")
        return await self.play_query(query)

    async def play_query(self, query: str) -> dict[str, Any]:
        async with self._lock:
            track = self._resolve_track(query)
            if track is None:
                result = {
                    "status": "missing_track",
                    "query": query,
                    "library": str(self.library_path),
                }
                await self.event_bus.publish("music.play_skipped", result, source="music", level="warning")
                return result

            try:
                await asyncio.to_thread(self._play_blocking, track.path)
                result = {
                    "status": "playing",
                    "title": track.title,
                    "path": str(track.path),
                    "score": round(track.score, 3),
                    "engine": "external" if self._external_fallback else "mci",
                }
            except Exception as exc:
                result = {
                    "status": "failed",
                    "title": track.title,
                    "path": str(track.path),
                    "detail": str(exc),
                }

            await self.event_bus.publish(
                "music.playback",
                result,
                source="music",
                level="error" if result["status"] == "failed" else "info",
            )
            return result

    async def pause(self) -> dict[str, Any]:
        return await self._control("pause", "paused")

    async def resume(self) -> dict[str, Any]:
        return await self._control("resume", "playing")

    async def stop(self) -> dict[str, Any]:
        async with self._lock:
            title = self._current_title()
            try:
                await asyncio.to_thread(self._close_blocking)
                result = {"status": "stopped", "title": title}
            except Exception as exc:
                result = {"status": "failed", "detail": str(exc)}
            await self.event_bus.publish("music.control", result, source="music")
            return result

    async def set_volume(self, volume: int) -> dict[str, Any]:
        volume = max(0, min(100, int(volume)))
        self._volume = volume
        async with self._lock:
            try:
                await asyncio.to_thread(self._set_volume_blocking, volume)
                result = {"status": "volume_set", "volume": volume, "title": self._current_title()}
            except Exception as exc:
                result = {"status": "failed", "volume": volume, "detail": str(exc)}
            await self.event_bus.publish("music.volume", result, source="music")
            return result

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            try:
                mode = await asyncio.to_thread(self._status_blocking)
            except Exception:
                mode = "external" if self._external_fallback else "stopped"
            return {
                "enabled": bool(self.settings.get("music.enabled", True)),
                "library": str(self.library_path),
                "current": str(self._current) if self._current else None,
                "title": self._current_title(),
                "mode": mode,
                "volume": self._volume,
                "engine": "external" if self._external_fallback else "mci",
            }

    async def close(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._close_blocking)

    @property
    def library_path(self) -> Path:
        return self.settings.path("music.library_path", "music")

    def _resolve_track(self, query: str) -> Track | None:
        default_file = str(self.settings.get("music.default_file", "") or "")
        if default_file:
            candidate = Path(default_file)
            if not candidate.is_absolute():
                candidate = self.library_path / candidate
            if candidate.exists():
                return Track(candidate, 1.0)

        tracks = list(self._scan_library())
        if not tracks:
            return None

        normalized_query = self._normalize(query)
        if not normalized_query:
            return Track(tracks[0], 0.5)

        ranked = [Track(path, self._score(normalized_query, self._normalize(path.stem))) for path in tracks]
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[0] if ranked and ranked[0].score >= 0.24 else Track(tracks[0], 0.2)

    def _scan_library(self) -> list[Path]:
        library = self.library_path
        if not library.exists():
            return []
        extensions = tuple(str(item).lower() for item in self.settings.get("music.extensions", self.DEFAULT_EXTENSIONS))
        return sorted(path for path in library.rglob("*") if path.is_file() and path.suffix.lower() in extensions)

    def _play_blocking(self, path: Path) -> None:
        with self._thread_lock:
            self._external_fallback = False
            try:
                self._close_blocking()
                self._mci(f'open "{path}" type mpegvideo alias {self._alias}')
                self._current = path
                self._set_volume_blocking(self._volume)
                self._mci(f"play {self._alias} from 0")
            except Exception:
                self._current = None
                if not bool(self.settings.get("music.external_fallback", True)):
                    raise
                self._close_blocking()
                os.startfile(str(path))  # type: ignore[attr-defined]
                self._external_fallback = True
            self._current = path

    def _control_blocking(self, command: str) -> None:
        with self._thread_lock:
            if self._external_fallback:
                raise MusicPlayerError("The current track is controlled by the default external media app.")
            if not self._current:
                raise MusicPlayerError("No local track is loaded.")
            if command == "resume":
                self._mci(f"play {self._alias}")
            else:
                self._mci(f"{command} {self._alias}")

    def _set_volume_blocking(self, volume: int) -> None:
        with self._thread_lock:
            if not self._current or self._external_fallback:
                return
            self._mci(f"setaudio {self._alias} volume to {volume * 10}")

    def _status_blocking(self) -> str:
        with self._thread_lock:
            if not self._current or self._external_fallback:
                return "stopped"
            return self._mci(f"status {self._alias} mode").lower() or "unknown"

    def _close_blocking(self) -> None:
        with self._thread_lock:
            try:
                self._mci(f"close {self._alias}")
            except Exception:
                pass
            self._current = None
            self._external_fallback = False

    async def _control(self, command: str, status: str) -> dict[str, Any]:
        async with self._lock:
            try:
                await asyncio.to_thread(self._control_blocking, command)
                result = {"status": status, "title": self._current_title()}
            except Exception as exc:
                result = {"status": "failed", "detail": str(exc)}
            await self.event_bus.publish("music.control", result, source="music")
            return result

    def _mci(self, command: str) -> str:
        if sys.platform != "win32":
            raise MusicPlayerError("Windows MCI playback is only available on Windows.")

        import ctypes

        buffer = ctypes.create_unicode_buffer(512)
        rc = ctypes.windll.winmm.mciSendStringW(command, buffer, len(buffer), None)
        if rc != 0:
            error = ctypes.create_unicode_buffer(512)
            ctypes.windll.winmm.mciGetErrorStringW(rc, error, len(error))
            raise MusicPlayerError(error.value or f"MCI command failed: {command}")
        return buffer.value.strip()

    def _current_title(self) -> str | None:
        return self._current.stem.replace("_", " ") if self._current else None

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower().replace("ё", "е")
        text = re.sub(r"[^a-zа-я0-9]+", " ", text)
        return " ".join(text.split())

    @staticmethod
    def _score(query: str, candidate: str) -> float:
        if query in candidate:
            return 1.0
        query_tokens = set(query.split())
        candidate_tokens = set(candidate.split())
        overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens | candidate_tokens), 1)
        ratio = SequenceMatcher(None, query, candidate).ratio()
        return max(overlap, ratio * 0.82)
