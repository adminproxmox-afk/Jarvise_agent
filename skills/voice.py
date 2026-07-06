from __future__ import annotations

from skills.base import Skill, SkillContext, SkillResult


class VoiceSkill(Skill):
    name = "voice"

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(ok=True, message="Voice skill ready", data={"request": context.request})
