from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlanStep:
    title: str
    details: str = ""


@dataclass(slots=True)
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"goal": self.goal, "steps": [{"title": step.title, "details": step.details} for step in self.steps]}


class Planner:
    """Simple planner that turns a request into executable steps."""

    def build_plan(self, request: str) -> Plan:
        normalized = request.strip().lower()
        steps: list[PlanStep] = []
        if any(keyword in normalized for keyword in ("проект", "project", "app", "application", "python", "code", "код")):
            steps.extend(
                [
                    PlanStep("Create project folder", "Prepare a workspace directory for the new project."),
                    PlanStep("Initialize repository", "Run git init if needed."),
                    PlanStep("Create docs", "Add a README or project notes."),
                    PlanStep("Open workspace", "Open the result in the developer environment."),
                ]
            )
        elif any(keyword in normalized for keyword in ("файл", "file", "папка", "folder")):
            steps.extend(
                [
                    PlanStep("Resolve target path", "Determine the requested location."),
                    PlanStep("Create target", "Create the file or folder."),
                    PlanStep("Confirm result", "Report completion to the user."),
                ]
            )
        else:
            steps.append(PlanStep("Understand request", "Clarify the user intent and choose the correct skill."))
            steps.append(PlanStep("Execute action", "Use the relevant skill or tool."))
            steps.append(PlanStep("Report outcome", "Inform the user of the result."))

        return Plan(goal=request, steps=steps)
