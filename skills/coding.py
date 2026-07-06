from __future__ import annotations

from skills.base import Skill, SkillContext, SkillResult


class CodingSkill(Skill):
    name = "coding"

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(ok=True, message="Coding skill ready", data={"request": context.request})
