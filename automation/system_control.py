from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

from config import Settings
from core.events import EventBus


class SystemControl:
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus

    async def shutdown_from_voice(self) -> dict[str, Any]:
        if not self.settings.get("safety.allow_shutdown_command", False):
            result = {
                "status": "blocked",
                "reason": "Shutdown by voice is disabled in config/default.yaml safety.allow_shutdown_command.",
            }
            await self.event_bus.publish("system.shutdown_blocked", result, source="system")
            return result

        command = ["shutdown", "/s", "/t", "30"] if os.name == "nt" else ["shutdown", "-h", "+1"]
        await self.event_bus.publish("system.shutdown_scheduled", {"seconds": 30, "command": command}, source="system")
        await asyncio.to_thread(subprocess.Popen, command)
        return {"status": "scheduled", "seconds": 30, "command": command}

    async def set_focus_assist(self, enabled: bool) -> dict[str, Any]:
        if os.name != "nt":
            result = {"status": "unsupported", "enabled": enabled, "platform": os.name}
            await self.event_bus.publish("system.focus_assist", result, source="system")
            return result

        script = (
            "New-ItemProperty -Path HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\Cache\\DefaultAccount "
            "-Name JarvisFocusAssist -Value 1 -PropertyType DWord -Force | Out-Null"
        )
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                check=False,
                capture_output=True,
                text=True,
            )
            result = {"status": "requested", "enabled": enabled}
        except Exception as exc:
            result = {"status": "failed", "enabled": enabled, "detail": str(exc)}
        await self.event_bus.publish("system.focus_assist", result, source="system")
        return result
