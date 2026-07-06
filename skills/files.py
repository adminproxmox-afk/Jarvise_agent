from __future__ import annotations

from pathlib import Path

from skills.base import Skill, SkillContext, SkillResult


class FileSkill(Skill):
    name = "files"

    async def execute(self, context: SkillContext) -> SkillResult:
        path = context.metadata.get("path")
        if not path:
            return SkillResult(ok=False, message="No path provided")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(context.metadata.get("content", ""), encoding="utf-8")
        return SkillResult(ok=True, message=f"Created file at {path}", data={"path": path})
