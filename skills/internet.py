from __future__ import annotations

from skills.base import Skill, SkillContext, SkillResult


class InternetSkill(Skill):
    name = "internet"

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(ok=True, message="Internet skill ready", data={"request": context.request})
