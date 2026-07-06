from __future__ import annotations

from agents.base import AgentDescriptor, BaseAgent


class BrowserAgent(BaseAgent):
    descriptor = AgentDescriptor(
        name="browser",
        title="Browser Agent",
        role="Automates browser sessions with Playwright-compatible workflows",
        capabilities=["open_sites", "fill_forms", "download_files", "auth_flows", "visual_checks"],
        default_task_type="search",
        tools=["browser", "filesystem"],
    )

    def can_handle(self, request: str) -> float:
        text = request.lower()
        keywords = ("browser", "браузер", "сайт", "форм", "скачай", "авториз", "playwright", "chrome")
        return 0.84 if any(keyword in text for keyword in keywords) else 0.12

    def plan(self, request: str) -> list[str]:
        return [
            "Open browser context",
            "Navigate to target",
            "Perform requested interactions",
            "Validate page state",
            "Return browser result",
        ]
