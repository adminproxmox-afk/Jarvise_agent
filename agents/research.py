from __future__ import annotations

from agents.base import AgentDescriptor, BaseAgent


class ResearchAgent(BaseAgent):
    descriptor = AgentDescriptor(
        name="research",
        title="Research Agent",
        role="Searches information, reads documentation and compiles findings",
        capabilities=["web_research", "documentation_analysis", "data_collection", "source_summary"],
        default_task_type="search",
        tools=["browser", "filesystem"],
    )

    def can_handle(self, request: str) -> float:
        text = request.lower()
        keywords = ("найди", "поиск", "research", "исслед", "документац", "собери данные", "latest")
        return 0.86 if any(keyword in text for keyword in keywords) else 0.15

    def plan(self, request: str) -> list[str]:
        return [
            "Clarify research target",
            "Collect primary sources",
            "Compare source claims",
            "Extract actionable notes",
            "Save findings to memory",
        ]
