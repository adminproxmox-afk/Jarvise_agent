from __future__ import annotations

from typing import Any

from automation.launcher import WorkspaceLauncher
from automation.system_control import SystemControl
from config import Settings
from core.commands import CommandIntent
from core.events import EventBus
from music.local_player import LocalMusicPlayer
from voice.tts import Speaker


class ActionSystem:
    def __init__(
        self,
        *,
        settings: Settings,
        event_bus: EventBus,
        workspace: WorkspaceLauncher,
        music: LocalMusicPlayer,
        system_control: SystemControl,
        speaker: Speaker,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.workspace = workspace
        self.music = music
        self.system_control = system_control
        self.speaker = speaker

    async def execute(self, intent: CommandIntent) -> dict[str, Any]:
        action = intent.action
        if action == "mode.coding":
            return {"workspace": await self.workspace.launch_workspace("coding")}
        if action == "project.open":
            return {"app": await self.workspace.launch_app("vscode")}
        if action == "music.play":
            return {"music": await self.music.play_default()}
        if action == "music.pause":
            return {"music": await self.music.pause()}
        if action == "music.resume":
            return {"music": await self.music.resume()}
        if action == "music.stop":
            return {"music": await self.music.stop()}
        if action == "music.volume":
            return {"music": await self.music.set_volume(int(intent.args.get("volume", 55)))}
        if action == "mode.focus":
            return await self.enable_mode("focus")
        if action == "app.open":
            return {"app": await self.workspace.launch_app(str(intent.args["app_id"]))}
        if action == "system.shutdown":
            return {"system": await self.system_control.shutdown_from_voice()}
        if action == "server.start":
            return {"server": await self.workspace.launch_app("local_dev_server", force=True)}
        if action in {"mode.gaming", "mode.night"}:
            return await self.enable_mode(action.split(".")[1])
        if action == "ai.chat":
            return {"status": "no_action", "message": "AI response only."}
        return {"status": "unknown_intent", "intent": action}

    async def enable_mode(self, mode: str) -> dict[str, Any]:
        await self.event_bus.publish("mode.started", {"mode": mode}, source="automation")
        result: dict[str, Any] = {"mode": mode, "steps": []}

        if mode == "coding":
            result["steps"].append({"workspace": await self.workspace.launch_workspace("coding")})
        elif mode == "focus":
            result["steps"].append({"closed": await self.workspace.close_distractions()})
            result["steps"].append({"music": await self.music.play_focus_playlist()})
            result["steps"].append({"notifications": await self.system_control.set_focus_assist(True)})
        elif mode == "gaming":
            result["steps"].append({"closed": await self.workspace.close_distractions()})
            result["steps"].append({"notifications": await self.system_control.set_focus_assist(True)})
        elif mode == "night":
            result["steps"].append({"ui": {"brightness": self.settings.get("modes.night.ui_brightness", 0.55)}})
            await self.speaker.set_profile("quiet")
        else:
            result["warning"] = "unknown_mode"

        await self.event_bus.publish("mode.completed", result, source="automation")
        return result
