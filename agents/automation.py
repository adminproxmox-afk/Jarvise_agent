from __future__ import annotations

from agents.base import AgentDescriptor, BaseAgent


class AutomationAgent(BaseAgent):
    descriptor = AgentDescriptor(
        name="automation",
        title="Automation Agent",
        role="Runs repeatable operating-system and tool workflows",
        capabilities=["script_execution", "scheduled_routines", "process_control", "notifications"],
        default_task_type="planning",
        tools=["terminal", "docker", "git", "telegram"],
    )

    def can_handle(self, request: str) -> float:
        text = request.lower()
        keywords = ("автомат", "скрипт", "routine", "schedule", "docker", "git", "deploy", "деплой")
        return 0.8 if any(keyword in text for keyword in keywords) else 0.2

    def plan(self, request: str) -> list[str]:
        return [
            "Map routine steps",
            "Check tool availability",
            "Run workflow step by step",
            "Capture logs",
            "Notify user",
        ]
