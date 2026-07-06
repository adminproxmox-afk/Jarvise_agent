from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await asyncio.to_thread(sqlite3.connect, self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        await asyncio.to_thread(self._migrate)

    async def close(self) -> None:
        if self._conn:
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    async def set_preference(self, key: str, value: Any) -> None:
        async with self._lock:
            await asyncio.to_thread(self._set_preference_sync, key, value)

    async def get_preference(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return await asyncio.to_thread(self._get_preference_sync, key, default)

    async def remember_command(self, text: str, intent: str, confidence: float) -> None:
        async with self._lock:
            await asyncio.to_thread(self._remember_command_sync, text, intent, confidence)

    async def remember_event(self, event_type: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._remember_event_sync, event_type, payload)

    async def remember_memory(
        self,
        section: str,
        key: str,
        value: Any,
        *,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._remember_memory_sync, section, key, value, tags or [])

    async def list_memory(self, section: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._list_memory_sync, section, limit)

    async def search_memory(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._search_memory_sync, query, limit)

    async def recent_commands(self, limit: int = 10) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._recent_commands_sync, limit)

    async def create_task_record(
        self,
        *,
        title: str,
        request: str,
        agent: str,
        model: str,
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(
                self._create_task_record_sync,
                title,
                request,
                agent,
                model,
                steps,
            )

    async def save_task_record(self, record: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._save_task_record_sync, record)

    async def get_task_record(self, task_id: int) -> dict[str, Any] | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_task_record_sync, task_id)

    async def list_task_records(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._list_task_records_sync, limit)

    async def mark_unfinished_tasks_interrupted(self) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._mark_unfinished_tasks_interrupted_sync)

    def _migrate(self) -> None:
        conn = self._require_conn()
        # WAL is not reliably available in every workspace filesystem, so fall
        # back to SQLite's default rollback journal when enabling it fails.
        try:
            journal_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        except sqlite3.OperationalError:
            conn.execute("PRAGMA journal_mode=DELETE")
        else:
            if not journal_mode or str(journal_mode[0]).lower() != "wal":
                conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA busy_timeout=3000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS command_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                intent TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS event_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section TEXT NOT NULL,
                item_key TEXT NOT NULL,
                value TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(section, item_key)
            );

            CREATE TABLE IF NOT EXISTS vector_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_item_id INTEGER NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(memory_item_id) REFERENCES memory_items(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS task_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                request TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL,
                agent TEXT NOT NULL,
                model TEXT NOT NULL,
                steps TEXT NOT NULL,
                logs TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );
            """
        )
        conn.commit()

    def _set_preference_sync(self, key: str, value: Any) -> None:
        conn = self._require_conn()
        conn.execute(
            """
            INSERT INTO preferences(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), self._now()),
        )
        conn.commit()

    def _get_preference_sync(self, key: str, default: Any = None) -> Any:
        row = self._require_conn().execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        return json.loads(row["value"])

    def _remember_command_sync(self, text: str, intent: str, confidence: float) -> None:
        conn = self._require_conn()
        conn.execute(
            "INSERT INTO command_history(text, intent, confidence, created_at) VALUES (?, ?, ?, ?)",
            (text, intent, confidence, self._now()),
        )
        conn.commit()

    def _remember_event_sync(self, event_type: str, payload: dict[str, Any]) -> None:
        conn = self._require_conn()
        conn.execute(
            "INSERT INTO event_history(event_type, payload, created_at) VALUES (?, ?, ?)",
            (event_type, json.dumps(payload, ensure_ascii=False), self._now()),
        )
        conn.commit()

    def _remember_memory_sync(
        self,
        section: str,
        key: str,
        value: Any,
        tags: list[str],
    ) -> dict[str, Any]:
        conn = self._require_conn()
        now = self._now()
        conn.execute(
            """
            INSERT INTO memory_items(section, item_key, value, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(section, item_key) DO UPDATE SET
                value=excluded.value,
                tags=excluded.tags,
                updated_at=excluded.updated_at
            """,
            (
                section,
                key,
                json.dumps(value, ensure_ascii=False),
                json.dumps(tags, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM memory_items WHERE section = ? AND item_key = ?",
            (section, key),
        ).fetchone()
        return self._memory_row_to_dict(row)

    def _list_memory_sync(self, section: str | None, limit: int) -> list[dict[str, Any]]:
        conn = self._require_conn()
        if section:
            rows = conn.execute(
                """
                SELECT * FROM memory_items
                WHERE section = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (section, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM memory_items
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._memory_row_to_dict(row) for row in rows]

    def _search_memory_sync(self, query: str, limit: int) -> list[dict[str, Any]]:
        like = f"%{query}%"
        rows = self._require_conn().execute(
            """
            SELECT * FROM memory_items
            WHERE section LIKE ? OR item_key LIKE ? OR value LIKE ? OR tags LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (like, like, like, like, limit),
        ).fetchall()
        return [self._memory_row_to_dict(row) for row in rows]

    def _recent_commands_sync(self, limit: int) -> list[dict[str, Any]]:
        rows = self._require_conn().execute(
            """
            SELECT text, intent, confidence, created_at
            FROM command_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in rows.fetchall()]

    def _create_task_record_sync(
        self,
        title: str,
        request: str,
        agent: str,
        model: str,
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        conn = self._require_conn()
        now = self._now()
        cursor = conn.execute(
            """
            INSERT INTO task_records(
                title, request, status, progress, agent, model, steps, logs,
                error, created_at, updated_at, started_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                request,
                "pending",
                0.0,
                agent,
                model,
                json.dumps(steps, ensure_ascii=False),
                json.dumps([], ensure_ascii=False),
                None,
                now,
                now,
                None,
                None,
            ),
        )
        conn.commit()
        return self._get_task_record_sync(int(cursor.lastrowid)) or {}

    def _save_task_record_sync(self, record: dict[str, Any]) -> dict[str, Any]:
        conn = self._require_conn()
        task_id = int(record["id"])
        record["updated_at"] = self._now()
        conn.execute(
            """
            UPDATE task_records
            SET title = ?, request = ?, status = ?, progress = ?, agent = ?, model = ?,
                steps = ?, logs = ?, error = ?, updated_at = ?, started_at = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                record.get("title", ""),
                record.get("request", ""),
                record.get("status", "pending"),
                float(record.get("progress", 0.0)),
                record.get("agent", "automation"),
                record.get("model", "auto"),
                json.dumps(record.get("steps", []), ensure_ascii=False),
                json.dumps(record.get("logs", []), ensure_ascii=False),
                record.get("error"),
                record.get("updated_at"),
                record.get("started_at"),
                record.get("completed_at"),
                task_id,
            ),
        )
        conn.commit()
        return self._get_task_record_sync(task_id) or {}

    def _get_task_record_sync(self, task_id: int) -> dict[str, Any] | None:
        row = self._require_conn().execute("SELECT * FROM task_records WHERE id = ?", (task_id,)).fetchone()
        return self._task_row_to_dict(row) if row else None

    def _list_task_records_sync(self, limit: int) -> list[dict[str, Any]]:
        rows = self._require_conn().execute(
            """
            SELECT * FROM task_records
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._task_row_to_dict(row) for row in rows]

    def _mark_unfinished_tasks_interrupted_sync(self) -> int:
        conn = self._require_conn()
        now = self._now()
        cursor = conn.execute(
            """
            UPDATE task_records
            SET status = 'interrupted', updated_at = ?, error = 'Backend restarted before task completed.'
            WHERE status IN ('pending', 'running')
            """,
            (now,),
        )
        conn.commit()
        return cursor.rowcount

    @staticmethod
    def _memory_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "section": row["section"],
            "key": row["item_key"],
            "item_key": row["item_key"],
            "value": json.loads(row["value"]),
            "tags": json.loads(row["tags"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _task_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "request": row["request"],
            "status": row["status"],
            "progress": row["progress"],
            "agent": row["agent"],
            "model": row["model"],
            "steps": json.loads(row["steps"]),
            "logs": json.loads(row["logs"]),
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("MemoryStore is not connected.")
        return self._conn

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
