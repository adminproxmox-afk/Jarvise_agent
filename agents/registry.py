from __future__ import annotations

from agents.automation import AutomationAgent
from agents.base import BaseAgent
from agents.browser import BrowserAgent
from agents.coding import CodingAgent
from agents.desktop import DesktopAgent
from agents.research import ResearchAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: list[BaseAgent] = [
            CodingAgent(),
            ResearchAgent(),
            DesktopAgent(),
            BrowserAgent(),
            AutomationAgent(),
        ]

    @property
    def agents(self) -> list[BaseAgent]:
        return list(self._agents)

    def get(self, name: str) -> BaseAgent | None:
        return next((agent for agent in self._agents if agent.descriptor.name == name), None)

    def select(self, request: str, hint: str | None = None) -> BaseAgent:
        if hint:
            hinted = self.get(hint)
            if hinted:
                return hinted
        return max(self._agents, key=lambda agent: agent.can_handle(request))

    def describe(self) -> list[dict[str, object]]:
        return [
            {
                "name": agent.descriptor.name,
                "title": agent.descriptor.title,
                "role": agent.descriptor.role,
                "capabilities": agent.descriptor.capabilities,
                "default_task_type": agent.descriptor.default_task_type,
                "tools": agent.descriptor.tools,
            }
            for agent in self._agents
        ]
