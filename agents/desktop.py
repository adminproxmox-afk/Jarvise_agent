from __future__ import annotations

from agents.base import AgentDescriptor, BaseAgent


class DesktopAgent(BaseAgent):
    descriptor = AgentDescriptor(
        name="desktop",
        title="Desktop Agent",
        role="Controls local applications, files and desktop workflows",
        capabilities=["app_launch", "file_management", "window_workflows", "workspace_modes"],
        default_task_type="local",
        tools=["filesystem", "terminal", "vscode"],
    )

    def can_handle(self, request: str) -> float:
        text = request.lower()
        keywords = ("открой", "запусти", "файл", "папк", "desktop", "приложение", "vscode", "terminal")
        return 0.82 if any(keyword in text for keyword in keywords) else 0.18

    def plan(self, request: str) -> list[str]:
        return [
            "Identify local resource",
            "Check access mode",
            "Execute desktop action",
            "Verify visible result",
            "Report status",
        ]
