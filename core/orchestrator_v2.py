from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brain import Brain
from character import Character
from memory.long_term import LongTermMemory
from memory.profile import ProfileMemory
from memory.projects import ProjectMemory
from memory.short_term import ShortTermMemory
from memory.knowledge import KnowledgeMemory
from planner import Planner
from skills import CodingSkill, FileSkill, InternetSkill, Skill, SkillContext, SkillResult, VoiceSkill


@dataclass(slots=True)
class OrchestratorContext:
    user_input: str
    short_term: ShortTermMemory = field(default_factory=ShortTermMemory)
    long_term: LongTermMemory = field(default_factory=LongTermMemory)
    profile: ProfileMemory = field(default_factory=ProfileMemory)
    projects: ProjectMemory = field(default_factory=ProjectMemory)
    knowledge: KnowledgeMemory = field(default_factory=KnowledgeMemory)


class JarviseOrchestrator:
    """Central orchestrator for the new modular architecture."""

    def __init__(self, brain: Brain, character: Character, planner: Planner | None = None) -> None:
        self.brain = brain
        self.character = character
        self.planner = planner or Planner()
        self.skills: list[Skill] = [CodingSkill(), FileSkill(), InternetSkill(), VoiceSkill()]

    async def handle(self, user_input: str, *, context: OrchestratorContext | None = None) -> dict[str, Any]:
        runtime = context or OrchestratorContext(user_input=user_input)
        runtime.short_term.add("user", user_input)

        plan = self.planner.build_plan(user_input)
        skill = self._select_skill(user_input)
        if skill is None:
            brain_response = await self.brain.respond(user_input, context=self.character.build_system_prompt())
            return {
                "response": self.character.adapt_response(brain_response.text),
                "plan": plan.to_dict(),
                "memory": runtime.long_term.snapshot(),
            }

        result = await skill.execute(SkillContext(request=user_input, memory={"plan": plan.to_dict()}, metadata={}))
        runtime.long_term.remember("last_skill", skill.name)
        runtime.short_term.add("assistant", result.message)
        return {
            "response": result.message,
            "plan": plan.to_dict(),
            "skill": skill.name,
            "memory": runtime.long_term.snapshot(),
        }

    def _select_skill(self, user_input: str) -> Skill | None:
        lower = user_input.lower()
        if any(keyword in lower for keyword in ("файл", "file", "папка", "folder", "create")):
            return next((skill for skill in self.skills if isinstance(skill, FileSkill)), None)
        if any(keyword in lower for keyword in ("код", "code", "program", "project")):
            return next((skill for skill in self.skills if isinstance(skill, CodingSkill)), None)
        if any(keyword in lower for keyword in ("web", "internet", "search", "документац")):
            return next((skill for skill in self.skills if isinstance(skill, InternetSkill)), None)
        if any(keyword in lower for keyword in ("голос", "voice", "speak", "tts", "stt")):
            return next((skill for skill in self.skills if isinstance(skill, VoiceSkill)), None)
        return None
