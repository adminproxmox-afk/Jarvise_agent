from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class AgentDescriptor:
    name: str
    title: str
    role: str
    capabilities: list[str]
    default_task_type: str
    tools: list[str] = field(default_factory=list)


class TaskRuntime(Protocol):
    async def log(self, message: str) -> None:
        ...

    async def step(self, index: int, status: str, *, progress: float | None = None, detail: str | None = None) -> None:
        ...


class BaseAgent:
    descriptor = AgentDescriptor(
        name="base",
        title="Base Agent",
        role="Generic execution agent",
        capabilities=[],
        default_task_type="planning",
    )

    def can_handle(self, request: str) -> float:
        return 0.1

    def plan(self, request: str) -> list[str]:
        return ["Analyze request", "Prepare execution plan", "Report result"]

    async def execute(self, request: str, runtime: TaskRuntime) -> dict[str, Any]:
        steps = self.plan(request)
        for index, title in enumerate(steps):
            await runtime.step(index, "running", detail=title)
            await runtime.log(f"{self.descriptor.title}: {title}")
            await asyncio.sleep(0.25)
            await runtime.step(index, "completed")
        return {"status": "completed", "agent": self.descriptor.name}
