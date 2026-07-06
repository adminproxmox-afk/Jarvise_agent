from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from api.schemas import ActivateRequest, CommandRequest, MemoryWriteRequest, ModelSelectRequest, TaskCreateRequest, ToolExecuteRequest
from core.orchestrator import JarvisOrchestrator
from core.orchestrator_v2 import JarviseOrchestrator as ModularOrchestrator


def create_router(orchestrator: JarvisOrchestrator, modular_orchestrator: ModularOrchestrator | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "service": "jarvis-backend"}

    @router.get("/status")
    async def status() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.status()}

    @router.post("/activate")
    async def activate(payload: ActivateRequest) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.activate(trigger=payload.trigger)}

    @router.post("/command")
    async def command(payload: CommandRequest) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.handle_text_command(payload.text)}

    if modular_orchestrator is not None:
        @router.post("/modular/command")
        async def modular_command(payload: CommandRequest) -> dict[str, object]:
            return {"ok": True, "data": await modular_orchestrator.handle(payload.text)}

    @router.get("/tasks")
    async def tasks(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.list_tasks(limit=limit)}

    @router.post("/tasks")
    async def create_task(payload: TaskCreateRequest) -> dict[str, object]:
        return {
            "ok": True,
            "data": await orchestrator.create_task(payload.request, title=payload.title, agent=payload.agent),
        }

    @router.get("/tasks/{task_id}")
    async def task_detail(task_id: int) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.get_task(task_id)}

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: int) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.cancel_task(task_id)}

    @router.get("/agents")
    async def agents() -> dict[str, object]:
        return {"ok": True, "data": orchestrator.agents_status()}

    @router.get("/models")
    async def models() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.models_status()}

    @router.post("/models/{provider}/test")
    async def test_model(provider: str) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.test_model_provider(provider)}

    @router.post("/models/select")
    async def select_model(payload: ModelSelectRequest) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.select_model(payload.provider, payload.model)}

    @router.post("/models/reset")
    async def reset_model_selection() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.clear_model_selection()}

    @router.get("/tools")
    async def tools() -> dict[str, object]:
        return {"ok": True, "data": orchestrator.tools_status()}

    @router.post("/tools/{tool}")
    async def execute_tool(tool: str, payload: ToolExecuteRequest) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.execute_tool(tool, payload.action, payload.payload)}

    @router.get("/memory")
    async def memory(section: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.list_memory(section=section, limit=limit)}

    @router.post("/memory")
    async def remember(payload: MemoryWriteRequest) -> dict[str, object]:
        return {
            "ok": True,
            "data": await orchestrator.remember_memory(payload.section, payload.key, payload.value, payload.tags),
        }

    @router.get("/memory/search")
    async def search_memory(q: str, limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.search_memory(q, limit=limit)}

    @router.get("/notifications")
    async def notifications() -> dict[str, object]:
        return {"ok": True, "data": orchestrator.notifications()}

    @router.get("/telegram/status")
    async def telegram_status() -> dict[str, object]:
        return {"ok": True, "data": orchestrator.telegram.status()}

    @router.post("/telegram/test")
    async def telegram_test() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.telegram_test()}

    @router.post("/workspace/start")
    async def start_workspace() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.workspace.launch_workspace("coding")}

    @router.post("/modes/{mode}")
    async def mode(mode: str) -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.enable_mode(mode)}

    @router.get("/music/status")
    async def music_status() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.status()}

    @router.post("/music/play")
    async def music_play() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.play_default()}

    @router.post("/music/pause")
    async def music_pause() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.pause()}

    @router.post("/music/resume")
    async def music_resume() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.resume()}

    @router.post("/music/stop")
    async def music_stop() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.stop()}

    @router.get("/spotify/status")
    async def spotify_status_compat() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.status(), "deprecated": True}

    @router.post("/spotify/play")
    async def spotify_play_compat() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.play_default(), "deprecated": True}

    @router.post("/spotify/pause")
    async def spotify_pause_compat() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.pause(), "deprecated": True}

    @router.post("/spotify/resume")
    async def spotify_resume_compat() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.resume(), "deprecated": True}

    @router.post("/spotify/stop")
    async def spotify_stop_compat() -> dict[str, object]:
        return {"ok": True, "data": await orchestrator.music.stop(), "deprecated": True}

    @router.websocket("/ws")
    async def websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = await orchestrator.event_bus.subscribe(replay=True)
        sender = asyncio.create_task(_send_events(websocket, queue), name="jarvis.ws.sender")
        try:
            while True:
                message = await websocket.receive_json()
                if message.get("type") == "command":
                    await orchestrator.handle_text_command(str(message.get("text", "")))
                elif message.get("type") == "activate":
                    await orchestrator.activate(trigger="ui")
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            try:
                await sender
            except asyncio.CancelledError:
                pass
            await orchestrator.event_bus.unsubscribe(queue)

    return router


async def _send_events(websocket: WebSocket, queue: asyncio.Queue) -> None:
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event.to_dict())
    except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
        return
