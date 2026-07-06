from __future__ import annotations

import time
from typing import Any

from memory.store import MemoryStore


class MemoryService:
    """Unified memory interface that wraps the existing SQLite-backed memory store."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def remember_short_term(self, role: str, content: str) -> None:
        # Use a monotonic timestamp-based key so short-term turns never collide
        # and we do not need to count existing rows on each write.
        key = f"{role}:{time.time_ns()}"
        await self.store.remember_memory("short_term", key, {"role": role, "content": content})

    async def remember_fact(self, key: str, value: Any) -> None:
        await self.store.remember_memory("long_term", key, value, tags=["fact"])

    async def remember_profile(self, key: str, value: Any) -> None:
        await self.store.remember_memory("profile", key, value, tags=["profile"])

    async def remember_project(self, key: str, value: Any) -> None:
        await self.store.remember_memory("projects", key, value, tags=["project"])

    async def remember_knowledge(self, key: str, value: Any) -> None:
        await self.store.remember_memory("knowledge", key, value, tags=["knowledge"])

    async def remember_goal(self, key: str, value: Any) -> None:
        await self.store.remember_memory("goals", key, value, tags=["goal"])

    async def get_section(self, section: str, limit: int = 20) -> list[dict[str, Any]]:
        return await self.store.list_memory(section, limit=limit)

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return await self.store.search_memory(query, limit=limit)
