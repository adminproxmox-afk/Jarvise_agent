from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class JarvisEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "core"
    category: str = "system"
    level: str = "info"
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventBus:
    def __init__(self, history_size: int = 200) -> None:
        self._subscribers: set[asyncio.Queue[JarvisEvent]] = set()
        self._history: deque[JarvisEvent] = deque(maxlen=history_size)
        self._lock = asyncio.Lock()

    @property
    def history(self) -> list[JarvisEvent]:
        return list(self._history)

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "core",
        category: str | None = None,
        level: str = "info",
        retain: bool | None = None,
    ) -> JarvisEvent:
        event = JarvisEvent(
            type=event_type,
            payload=payload or {},
            source=source,
            category=category or self._infer_category(event_type, source),
            level=level,
        )
        should_retain = retain if retain is not None else event_type != "system.stats"
        async with self._lock:
            if should_retain:
                self._history.append(event)
            subscribers = list(self._subscribers)

        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)
        return event

    async def subscribe(self, *, replay: bool = True) -> asyncio.Queue[JarvisEvent]:
        queue: asyncio.Queue[JarvisEvent] = asyncio.Queue(maxsize=300)
        async with self._lock:
            self._subscribers.add(queue)
            if replay:
                for event in self._history:
                    queue.put_nowait(event)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[JarvisEvent]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    @staticmethod
    def _infer_category(event_type: str, source: str) -> str:
        if event_type.startswith("ai."):
            return "ai"
        if event_type.startswith(("spotify.", "music.")):
            return "media"
        if event_type.startswith(("workspace.", "mode.")):
            return "automation"
        if event_type.startswith(("voice.", "clap.")):
            return "voice"
        if event_type.startswith("system."):
            return "system"
        if event_type.startswith("ui."):
            return "ui"
        return source
