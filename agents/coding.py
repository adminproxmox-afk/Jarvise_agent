from __future__ import annotations

from agents.base import AgentDescriptor, BaseAgent


class CodingAgent(BaseAgent):
    descriptor = AgentDescriptor(
        name="coding",
        title="Coding Agent",
        role="Creates projects, writes code, refactors and runs checks",
        capabilities=[
            "project_scaffolding",
            "code_generation",
            "refactoring",
            "test_execution",
            "dependency_setup",
        ],
        default_task_type="coding",
        tools=["filesystem", "terminal", "git", "docker", "vscode"],
    )

    def can_handle(self, request: str) -> float:
        text = request.lower()
        keywords = ("код", "code", "react", "fastapi", "python", "typescript", "создай проект", "crm", "тест")
        return 0.88 if any(keyword in text for keyword in keywords) else 0.2

    def plan(self, request: str) -> list[str]:
        text = request.lower()
        steps = ["Understand requirements", "Inspect target workspace"]
        if any(word in text for word in ("fastapi", "backend", "api")):
            steps.append("Create or update backend module")
        if any(word in text for word in ("react", "frontend", "ui", "electron")):
            steps.append("Create or update frontend module")
        if any(word in text for word in ("database", "база", "sqlite", "postgres")):
            steps.append("Configure persistence layer")
        steps.extend(["Install or verify dependencies", "Run checks", "Summarize delivery"])
        return steps
