"""PulseFlow pipeline: Event Repository.

CRUD operations for persisting and querying processed events in SQLite.
"""

import json
from typing import Any, Dict, List, Optional
from contracts.priorities import Priority
from pipeline.storage.database import DatabaseManager, database_manager


class EventRepository:
    """Data access repository for processed events."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or database_manager

    async def insert_event(
        self,
        event_id: str,
        event_type: str,
        priority: str,
        status: str,
        processing_mode: str,
        payload: Dict[str, Any],
        received_at: Optional[float],
        processed_at: float,
        latency_ms: float,
    ) -> None:
        """Insert a single processed event record."""
        conn = await self.db.connect()
        sql = """
        INSERT OR REPLACE INTO processed_events (
            event_id, event_type, priority, status, processing_mode, payload, received_at, processed_at, latency_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        payload_json = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
        await conn.execute(
            sql,
            (
                event_id,
                event_type,
                str(priority),
                status,
                processing_mode,
                payload_json,
                received_at,
                processed_at,
                latency_ms,
            ),
        )
        await conn.commit()

    async def insert_events_batch(self, records: List[Dict[str, Any]]) -> None:
        """Bulk insert multiple processed event records."""
        if not records:
            return
        conn = await self.db.connect()
        sql = """
        INSERT OR REPLACE INTO processed_events (
            event_id, event_type, priority, status, processing_mode, payload, received_at, processed_at, latency_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                r["event_id"],
                r["event_type"],
                str(r["priority"]),
                r["status"],
                r["processing_mode"],
                json.dumps(r.get("payload", {})) if isinstance(r.get("payload"), (dict, list)) else str(r.get("payload", "")),
                r.get("received_at"),
                r["processed_at"],
                r["latency_ms"],
            )
            for r in records
        ]
        await conn.executemany(sql, rows)
        await conn.commit()

    async def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single event by event_id."""
        conn = await self.db.connect()
        sql = "SELECT * FROM processed_events WHERE event_id = ?"
        async with conn.execute(sql, (event_id,)) as cursor:
            row = await cursor.fetchone()
            if row is not None:
                d = dict(row)
                if d.get("payload"):
                    try:
                        d["payload"] = json.loads(d["payload"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                return d
        return None

    async def count_events(self, priority: Optional[Priority] = None) -> int:
        """Count total processed events, optionally filtered by priority lane."""
        conn = await self.db.connect()
        if priority is not None:
            sql = "SELECT COUNT(*) FROM processed_events WHERE priority = ?"
            async with conn.execute(sql, (priority.value,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        else:
            sql = "SELECT COUNT(*) FROM processed_events"
            async with conn.execute(sql) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def clear(self) -> None:
        """Truncate processed_events table."""
        conn = await self.db.connect()
        await conn.execute("DELETE FROM processed_events")
        await conn.commit()


# Default shared repository instance
event_repository = EventRepository()

__all__ = ["EventRepository", "event_repository"]
