from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents import AgentRegistry
from ai.brain import JarvisBrain
from api.routes import create_router
from automation.launcher import WorkspaceLauncher
from automation.system_control import SystemControl
from brain import Brain
from character import Character
from config import load_settings
from core.actions import ActionSystem
from core.commands import VoiceCommandRouter
from core.events import EventBus
from core.orchestrator import JarvisOrchestrator
from core.orchestrator_v2 import JarviseOrchestrator as ModularOrchestrator
from core.task_manager import TaskManager
from integrations import TelegramService
from memory.store import MemoryStore
from music.local_player import LocalMusicPlayer
from planner import Planner
from providers.base import ProviderConfig
from providers.ollama import OllamaProvider
from system.sound import StartupSoundPlayer
from system.stats import SystemStatsService
from tools import ToolRegistry
from voice.clap import ClapDetector
from voice.tts import create_speaker


def create_app(config_path: str = "config/default.yaml") -> FastAPI:
    settings = load_settings(config_path)
    event_bus = EventBus()
    memory = MemoryStore(settings.path("memory.path", "memory/jarvis.sqlite3"))
    speaker = create_speaker(settings, event_bus)
    sound = StartupSoundPlayer(settings, event_bus)
    music = LocalMusicPlayer(settings, event_bus)
    workspace = WorkspaceLauncher(settings, event_bus)
    system_control = SystemControl(settings, event_bus)
    stats = SystemStatsService()
    clap_detector = ClapDetector(settings, event_bus)
    command_router = VoiceCommandRouter()
    brain = JarvisBrain(settings, memory, command_router)
    agents = AgentRegistry()
    telegram = TelegramService(settings, event_bus)
    tools = ToolRegistry(settings, event_bus, telegram=telegram)
    task_manager = TaskManager(memory=memory, event_bus=event_bus, agents=agents, gateway=brain.gateway)
    actions = ActionSystem(
        settings=settings,
        event_bus=event_bus,
        workspace=workspace,
        music=music,
        system_control=system_control,
        speaker=speaker,
    )

    provider = OllamaProvider(ProviderConfig(name="ollama", model=os.getenv("JARVIS_MODEL", "llama3")))
    modular_brain = Brain(provider=provider, system_prompt=str(settings.get("ai.system_prompt", "")))
    modular_character = Character()
    modular_orchestrator = ModularOrchestrator(
        brain=modular_brain,
        character=modular_character,
        planner=Planner(),
    )

    orchestrator = JarvisOrchestrator(
        settings=settings,
        event_bus=event_bus,
        memory=memory,
        workspace=workspace,
        speaker=speaker,
        sound=sound,
        music=music,
        system_control=system_control,
        stats=stats,
        clap_detector=clap_detector,
        command_router=command_router,
        brain=brain,
        actions=actions,
        agents=agents,
        tools=tools,
        task_manager=task_manager,
        telegram=telegram,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await memory.connect()
        await orchestrator.start()
        try:
            yield
        finally:
            await orchestrator.shutdown()

    app = FastAPI(title="JARVIS Desktop Assistant", version="0.1.0", lifespan=lifespan)
    app.state.jarvis = orchestrator
    app.state.modular_orchestrator = modular_orchestrator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get("api.cors_origins", ["http://127.0.0.1:5173"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api_router = create_router(orchestrator, modular_orchestrator)
    app.router.routes.extend(api_router.routes)
    return app
