from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from config import Settings
from core.events import EventBus


class SpotifyClient:
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self._client: Any | None = None
        self._client_lock = asyncio.Lock()

    async def play_default(self) -> dict[str, Any]:
        uri = (
            self.settings.get("spotify.default_track_uri")
            or self.settings.get("spotify.coding_playlist_uri")
            or self.settings.get("spotify.focus_playlist_uri")
        )
        if not uri:
            result = {"status": "missing_uri", "config": "spotify.default_track_uri"}
            await self.event_bus.publish("spotify.play_skipped", result, source="spotify", level="warning")
            return result
        return await self.play_uri(str(uri))

    async def play_focus_playlist(self) -> dict[str, Any]:
        playlist = self.settings.get("spotify.focus_playlist_uri")
        if not playlist:
            result = {"status": "missing_playlist", "config": "spotify.focus_playlist_uri"}
            await self.event_bus.publish("spotify.play_skipped", result, source="spotify")
            return result
        return await self.play_uri(playlist)

    async def play_uri(self, uri: str) -> dict[str, Any]:
        try:
            client = await self._get_client()
            device = await self._ensure_device(client)
            kwargs: dict[str, Any] = {"device_id": device.get("id")}
            if uri.startswith("spotify:track:"):
                kwargs["uris"] = [uri]
            else:
                kwargs["context_uri"] = uri
            await asyncio.to_thread(client.start_playback, **kwargs)
            result = {"status": "playing", "uri": uri, "device": self._device_summary(device)}
        except Exception as exc:
            result = {"status": "failed", "uri": uri, "detail": str(exc)}
        await self.event_bus.publish(
            "spotify.playback",
            result,
            source="spotify",
            level="error" if result["status"] == "failed" else "info",
        )
        return result

    async def pause(self) -> dict[str, Any]:
        return await self._call_player("pause_playback", "paused")

    async def resume(self) -> dict[str, Any]:
        return await self._call_player("start_playback", "playing")

    async def set_volume(self, volume: int) -> dict[str, Any]:
        volume = max(0, min(100, volume))
        try:
            client = await self._get_client()
            device = await self._ensure_device(client)
            await asyncio.to_thread(client.volume, volume, device_id=device.get("id"))
            result = {"status": "volume_set", "volume": volume, "device": self._device_summary(device)}
        except Exception as exc:
            result = {"status": "failed", "volume": volume, "detail": str(exc)}
        await self.event_bus.publish("spotify.volume", result, source="spotify")
        return result

    async def status(self) -> dict[str, Any]:
        try:
            client = await self._get_client()
            playback = await asyncio.to_thread(client.current_playback)
            return {
                "configured": True,
                "active": bool(playback and playback.get("is_playing")),
                "device": self._device_summary((playback or {}).get("device") or {}),
                "item": ((playback or {}).get("item") or {}).get("name"),
            }
        except Exception as exc:
            return {"configured": self._has_credentials(), "status": "unavailable", "detail": str(exc)}

    async def _call_player(self, method_name: str, status: str) -> dict[str, Any]:
        try:
            client = await self._get_client()
            device = await self._ensure_device(client)
            method = getattr(client, method_name)
            await asyncio.to_thread(method, device_id=device.get("id"))
            result = {"status": status, "device": self._device_summary(device)}
        except Exception as exc:
            result = {"status": "failed", "detail": str(exc)}
        await self.event_bus.publish("spotify.control", result, source="spotify")
        return result

    async def _get_client(self) -> Any:
        async with self._client_lock:
            if self._client is not None:
                return self._client
            if not self._has_credentials():
                raise RuntimeError("Spotify OAuth is not configured. Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET.")
            self._client = await asyncio.to_thread(self._create_client)
            return self._client

    def _create_client(self) -> Any:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        scope = " ".join(
            [
                "user-read-playback-state",
                "user-modify-playback-state",
                "user-read-currently-playing",
                "streaming",
            ]
        )
        cache_path = str(self.settings.path("spotify.cache_path", "memory/.spotify_cache"))
        auth = SpotifyOAuth(
            client_id=os.getenv("274879d0ae1c4d7f9857268de06b1e08"),
            client_secret=os.getenv("4b501968544d461b8098d85e11cf837a"),
            redirect_uri=os.getenv("https://open.spotify.com/track/39shmbIHICJ2Wxnk1fPSdz?si=6b6503ceb365429f", "http://127.0.0.1:8765/spotify/callback"),
            scope=scope,
            cache_path=cache_path,
            open_browser=True,
        )
        return spotipy.Spotify(auth_manager=auth, requests_timeout=10, retries=2)

    async def _ensure_device(self, client: Any) -> dict[str, Any]:
        device = await self._active_device(client)
        if device:
            return device

        await self.event_bus.publish("spotify.device_missing", {"action": "launch_spotify"}, source="spotify", level="warning")
        self._launch_spotify()
        deadline = time.monotonic() + float(self.settings.get("spotify.device_wait_seconds", 12))
        while time.monotonic() < deadline:
            await asyncio.sleep(1.0)
            device = await self._active_device(client)
            if device:
                return device
        raise RuntimeError("No active Spotify device found. Open Spotify and start any playback once.")

    async def _active_device(self, client: Any) -> dict[str, Any] | None:
        devices_payload = await asyncio.to_thread(client.devices)
        devices = devices_payload.get("devices", [])
        if not devices:
            return None
        active = next((device for device in devices if device.get("is_active") and not device.get("is_restricted")), None)
        if active:
            return active
        candidate = next((device for device in devices if not device.get("is_restricted")), None)
        if candidate:
            await asyncio.to_thread(client.transfer_playback, candidate["id"], force_play=False)
            return candidate
        return None

    def _launch_spotify(self) -> None:
        try:
            os.startfile(str(self.settings.get("spotify.launch_uri", "spotify:")))  # type: ignore[attr-defined]
        except Exception:
            pass

    @staticmethod
    def _has_credentials() -> bool:
        return bool(os.getenv("SPOTIPY_CLIENT_ID") and os.getenv("SPOTIPY_CLIENT_SECRET"))

    @staticmethod
    def _device_summary(device: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": device.get("id"),
            "name": device.get("name"),
            "type": device.get("type"),
            "active": device.get("is_active"),
            "volume": device.get("volume_percent"),
        }
