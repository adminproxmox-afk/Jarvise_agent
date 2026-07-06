from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from agents.registry import AgentRegistry
from ai.gateway import AIGateway
from core.events import EventBus
from memory.store import MemoryStore


class TaskRuntime:
    def __init__(self, manager: "TaskManager", task_id: int) -> None:
        self.manager = manager
        self.task_id = task_id

    async def log(self, message: str) -> None:
        await self.manager.append_log(self.task_id, message)

    async def step(self, index: int, status: str, *, progress: float | None = None, detail: str | None = None) -> None:
        await self.manager.update_step(self.task_id, index, status, progress=progress, detail=detail)


class TaskManager:
    def __init__(
        self,
        *,
        memory: MemoryStore,
        event_bus: EventBus,
        agents: AgentRegistry,
        gateway: AIGateway,
    ) -> None:
        self.memory = memory
        self.event_bus = event_bus
        self.agents = agents
        self.gateway = gateway
        self._running: dict[int, asyncio.Task[None]] = {}

    async def start(self) -> None:
        interrupted = await self.memory.mark_unfinished_tasks_interrupted()
        if interrupted:
            await self.event_bus.publish(
                "task.recovered",
                {"interrupted": interrupted},
                source="tasks",
                level="warning",
            )

    async def shutdown(self) -> None:
        for task in list(self._running.values()):
            task.cancel()
        if self._running:
            await asyncio.gather(*self._running.values(), return_exceptions=True)
        self._running.clear()

    async def create_task(
        self,
        request: str,
        *,
        title: str | None = None,
        agent_hint: str | None = None,
        start: bool = True,
    ) -> dict[str, Any]:
        agent = self.agents.select(request, hint=agent_hint)
        task_type = agent.descriptor.default_task_type
        selection = self.gateway.current_selection()
        provider_name = selection["provider"] if selection else self.gateway.route_for_task(task_type)
        provider = self.gateway.providers.get(provider_name)
        model = selection["model"] if selection else (provider.model if provider else "auto")
        steps = [
            {"title": item, "status": "pending", "progress": 0.0, "detail": ""}
            for item in agent.plan(request)
        ]
        record = await self.memory.create_task_record(
            title=title or self._title_from_request(request),
            request=request,
            agent=agent.descriptor.name,
            model=model,
            steps=steps,
        )
        await self.event_bus.publish("task.created", self._public_task(record), source="tasks")
        if start:
            self.start_task(int(record["id"]))
        return record

    def start_task(self, task_id: int) -> None:
        if task_id in self._running:
            return
        task = asyncio.create_task(self._run_task(task_id), name=f"jarvis.task.{task_id}")
        self._running[task_id] = task
        task.add_done_callback(lambda finished, current=task_id: self._running.pop(current, None))

    async def cancel_task(self, task_id: int) -> dict[str, Any]:
        running = self._running.get(task_id)
        if running:
            running.cancel()
        record = await self.memory.get_task_record(task_id)
        if not record:
            return {"ok": False, "reason": "task_not_found"}
        record["status"] = "canceled"
        record["completed_at"] = self._now()
        record = await self.memory.save_task_record(record)
        await self.event_bus.publish("task.canceled", self._public_task(record), source="tasks", level="warning")
        return {"ok": True, "task": record}

    async def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self.memory.list_task_records(limit=limit)

    async def get_task(self, task_id: int) -> dict[str, Any] | None:
        return await self.memory.get_task_record(task_id)

    async def append_log(self, task_id: int, message: str) -> None:
        record = await self.memory.get_task_record(task_id)
        if not record:
            return
        record.setdefault("logs", []).append({"time": self._now(), "message": message})
        await self.memory.save_task_record(record)
        await self.event_bus.publish("task.log", {"id": task_id, "message": message}, source="tasks")

    async def update_step(
        self,
        task_id: int,
        index: int,
        status: str,
        *,
        progress: float | None = None,
        detail: str | None = None,
    ) -> None:
        record = await self.memory.get_task_record(task_id)
        if not record:
            return
        steps = record.get("steps", [])
        if not (0 <= index < len(steps)):
            return
        steps[index]["status"] = status
        if detail is not None:
            steps[index]["detail"] = detail
        if progress is not None:
            steps[index]["progress"] = progress
        elif status == "completed":
            steps[index]["progress"] = 100.0
        record["steps"] = steps
        record["progress"] = self._calculate_progress(steps)
        await self.memory.save_task_record(record)
        await self.event_bus.publish("task.progress", self._public_task(record), source="tasks")

    async def _run_task(self, task_id: int) -> None:
        record = await self.memory.get_task_record(task_id)
        if not record:
            return
        agent = self.agents.get(str(record["agent"])) or self.agents.select(str(record["request"]))
        try:
            record["status"] = "running"
            record["started_at"] = record.get("started_at") or self._now()
            record = await self.memory.save_task_record(record)
            await self.event_bus.publish("task.started", self._public_task(record), source="tasks")
            result = await agent.execute(str(record["request"]), TaskRuntime(self, task_id))
            record = await self.memory.get_task_record(task_id) or record
            record["status"] = "completed"
            record["progress"] = 100.0
            record["completed_at"] = self._now()
            record.setdefault("logs", []).append({"time": self._now(), "message": f"Result: {result}"})
            record = await self.memory.save_task_record(record)
            await self.event_bus.publish("task.completed", self._public_task(record), source="tasks")
        except asyncio.CancelledError:
            record = await self.memory.get_task_record(task_id) or record
            record["status"] = "canceled"
            record["completed_at"] = self._now()
            await self.memory.save_task_record(record)
            raise
        except Exception as exc:
            record = await self.memory.get_task_record(task_id) or record
            record["status"] = "failed"
            record["error"] = str(exc)
            record["completed_at"] = self._now()
            record = await self.memory.save_task_record(record)
            await self.event_bus.publish("task.failed", self._public_task(record), source="tasks", level="error")

    @staticmethod
    def _calculate_progress(steps: list[dict[str, Any]]) -> float:
        if not steps:
            return 0.0
        total = sum(float(step.get("progress", 0.0)) for step in steps)
        return round(total / len(steps), 1)

    @staticmethod
    def _public_task(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record.get("id"),
            "title": record.get("title"),
            "status": record.get("status"),
            "progress": record.get("progress"),
            "agent": record.get("agent"),
            "model": record.get("model"),
            "current_step": TaskManager._current_step(record),
        }

    @staticmethod
    def _current_step(record: dict[str, Any]) -> str | None:
        for step in record.get("steps", []):
            if step.get("status") in {"pending", "running"}:
                return str(step.get("title"))
        return None

    @staticmethod
    def _title_from_request(request: str) -> str:
        compact = " ".join(request.split())
        return compact[:72] + ("..." if len(compact) > 72 else "")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
