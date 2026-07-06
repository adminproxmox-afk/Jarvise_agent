from __future__ import annotations

import asyncio
from pathlib import Path

from config import Settings
from core.events import EventBus


class StartupSoundPlayer:
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus

    async def play(self) -> None:
        await self.event_bus.publish("startup.sound_started", {}, source="system")
        await asyncio.to_thread(self._play_blocking)
        await self.event_bus.publish("startup.sound_completed", {}, source="system")

    def _play_blocking(self) -> None:
        try:
            import winsound
        except Exception:
            return

        raw_path = str(self.settings.get("startup.sound_path", "") or "")
        if raw_path:
            path = Path(raw_path)
            if not path.is_absolute():
                path = self.settings.root_dir / path
            if path.exists():
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return

        for frequency, duration in [(523, 90), (784, 110), (1046, 160), (1568, 220)]:
            winsound.Beep(frequency, duration)
