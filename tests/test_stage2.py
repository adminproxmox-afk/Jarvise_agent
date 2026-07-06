from __future__ import annotations

import asyncio
from pathlib import Path

from planner.planner import Planner
from skills.manager import SkillManager
from memory.service import MemoryService
from memory.store import MemoryStore


def test_planner_builds_project_plan() -> None:
    planner = Planner()
    plan = planner.build_plan("create a python project")
    assert plan.goal == "create a python project"
    assert any(step.title.lower() == "create project folder" for step in plan.steps)


def test_skill_manager_selects_coding_skill() -> None:
    manager = SkillManager()
    skill = manager.select_skill("create a python project")
    assert skill is not None
    assert skill.name == "coding"


def test_memory_service_supports_sections() -> None:
    import asyncio

    store = MemoryStore(Path("memory/test_memory.sqlite3"))
    service = MemoryService(store)

    async def run() -> None:
        await store.connect()
        await service.remember_knowledge("python", "Python is versatile")
        knowledge = await service.get_section("knowledge", limit=5)
        assert any(item.get("item_key") == "python" for item in knowledge)
        await store.close()

    asyncio.run(run())
    Path("memory/test_memory.sqlite3").unlink(missing_ok=True)
    Path("memory/test_memory.sqlite3-shm").unlink(missing_ok=True)
    Path("memory/test_memory.sqlite3-wal").unlink(missing_ok=True)


def test_short_term_memory_uses_unique_keys(tmp_path: Path) -> None:
    import asyncio

    store = MemoryStore(tmp_path / "memory.sqlite3")
    service = MemoryService(store)

    async def run() -> None:
        await store.connect()
        await service.remember_short_term("user", "first")
        await service.remember_short_term("assistant", "second")
        short_term = await service.get_section("short_term", limit=10)
        assert len(short_term) == 2
        assert {item["section"] for item in short_term} == {"short_term"}
        await store.close()

    asyncio.run(run())
