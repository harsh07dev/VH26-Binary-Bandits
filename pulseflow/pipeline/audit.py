"""PulseFlow pipeline: Audit Logging.

Embedded SQLite audit logger in WAL mode (PRAGMA journal_mode=WAL;).
Provides decision lineage persistence via a dedicated single-threaded async worker
consuming from an asyncio.Queue and batch inserting via cursor.executemany()
every 500ms or 100 records to eliminate database write-locking errors under parallel loads.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from contracts.events import Event

INSERT_AUDIT_LOG_SQL = """
INSERT INTO decision_audit_logs (
    event_id, event_type, priority, rule_id, score, evaluated_at, features, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

CREATE_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS decision_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    priority TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    score REAL NOT NULL,
    evaluated_at REAL NOT NULL,
    features TEXT,
    created_at REAL NOT NULL
);
"""

CREATE_AUDIT_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_audit_event_id ON decision_audit_logs (event_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_evaluated_at ON decision_audit_logs (evaluated_at);",
    "CREATE INDEX IF NOT EXISTS idx_audit_priority ON decision_audit_logs (priority);",
]


class AuditLogger:
    """Async decision lineage audit logger backed by WAL-mode SQLite and batch flushes."""

    def __init__(
        self,
        db_path: str = "pulseflow_audit.db",
        batch_size: int = 100,
        flush_interval_ms: float = 500.0,
    ) -> None:
        self.db_path = db_path
        self.batch_size = max(1, batch_size)
        self.flush_interval_sec = max(0.01, flush_interval_ms / 1000.0)

        self._queue: Optional[asyncio.Queue[Dict[str, Any]]] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._conn: Optional[sqlite3.Connection] = None
        self._is_running = False
        self._flushed_count = 0
        self._batches_count = 0

    @property
    def queue(self) -> asyncio.Queue[Dict[str, Any]]:
        """Lazy-initialize queue attached to active event loop."""
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def flushed_count(self) -> int:
        return self._flushed_count

    @property
    def batches_count(self) -> int:
        return self._batches_count

    def _init_db_sync(self) -> None:
        """Initialize SQLite connection in WAL mode and create tables and indexes."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            # Enforce WAL mode and NORMAL synchronous setting
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute(CREATE_AUDIT_TABLE_SQL)
            for idx_sql in CREATE_AUDIT_INDEXES_SQL:
                cursor.execute(idx_sql)
            self._conn.commit()

    def get_journal_mode(self) -> str:
        """Return the current SQLite journal_mode (e.g. 'wal')."""
        self._init_db_sync()
        assert self._conn is not None
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        row = cursor.fetchone()
        return str(row[0]).lower() if row else "unknown"

    async def start(self) -> None:
        """Initialize database schema and launch background worker loop."""
        if self._is_running:
            return

        await asyncio.to_thread(self._init_db_sync)
        self._stop_event.clear()
        self._is_running = True
        self._worker_task = asyncio.create_task(
            self._worker_loop(),
            name=f"audit-logger-worker-{self.db_path}",
        )

    async def log(
        self,
        event_id: str,
        event_type: str,
        priority: str,
        rule_id: str,
        score: float,
        evaluated_at: float,
        features: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Asynchronously enqueue an audit record for batch persistence."""
        record = {
            "event_id": str(event_id),
            "event_type": str(event_type),
            "priority": str(priority),
            "rule_id": str(rule_id),
            "score": float(score),
            "evaluated_at": float(evaluated_at),
            "features": features or {},
            "created_at": time.time(),
        }
        await self.queue.put(record)

    def log_nowait(
        self,
        event_id: str,
        event_type: str,
        priority: str,
        rule_id: str,
        score: float,
        evaluated_at: float,
        features: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Synchronously enqueue an audit record without awaiting."""
        record = {
            "event_id": str(event_id),
            "event_type": str(event_type),
            "priority": str(priority),
            "rule_id": str(rule_id),
            "score": float(score),
            "evaluated_at": float(evaluated_at),
            "features": features or {},
            "created_at": time.time(),
        }
        self.queue.put_nowait(record)

    async def log_event(self, event: Event) -> None:
        """Extract decision lineage from an Event and enqueue it for audit logging."""
        audit_meta = event.audit or {}
        now = time.time()
        rule_id = audit_meta.get("rule_id", "rule-default")
        score = audit_meta.get("score", 0.0)
        evaluated_at = audit_meta.get("evaluated_at", now)
        features = audit_meta.get("features", {})
        priority = event.ensure_priority().value

        await self.log(
            event_id=event.event_id,
            event_type=event.event_type,
            priority=priority,
            rule_id=rule_id,
            score=score,
            evaluated_at=evaluated_at,
            features=features,
        )

    def log_event_nowait(self, event: Event) -> None:
        """Synchronously extract decision lineage from Event and enqueue without awaiting."""
        audit_meta = event.audit or {}
        now = time.time()
        rule_id = audit_meta.get("rule_id", "rule-default")
        score = audit_meta.get("score", 0.0)
        evaluated_at = audit_meta.get("evaluated_at", now)
        features = audit_meta.get("features", {})
        priority = event.ensure_priority().value

        self.log_nowait(
            event_id=event.event_id,
            event_type=event.event_type,
            priority=priority,
            rule_id=rule_id,
            score=score,
            evaluated_at=evaluated_at,
            features=features,
        )

    def _flush_sync(self, records: List[Dict[str, Any]]) -> int:
        """Synchronously execute batch insert via cursor.executemany."""
        if not records or self._conn is None:
            return 0

        rows = [
            (
                r["event_id"],
                r["event_type"],
                r["priority"],
                r["rule_id"],
                r["score"],
                r["evaluated_at"],
                json.dumps(r.get("features", {}))
                if isinstance(r.get("features"), (dict, list))
                else str(r.get("features", "")),
                r["created_at"],
            )
            for r in records
        ]

        cursor = self._conn.cursor()
        cursor.executemany(INSERT_AUDIT_LOG_SQL, rows)
        self._conn.commit()
        return len(rows)

    async def _flush_batch(self, batch: List[Dict[str, Any]]) -> int:
        """Offload batch insert to dedicated worker thread."""
        if not batch:
            return 0
        flushed = await asyncio.to_thread(self._flush_sync, batch)
        self._flushed_count += flushed
        self._batches_count += 1
        return flushed

    async def _worker_loop(self) -> None:
        """Single-threaded worker consuming from asyncio.Queue and writing batch inserts."""
        batch: List[Dict[str, Any]] = []

        while not self._stop_event.is_set():
            # 1. Await next record or sentinel
            try:
                item = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=min(0.2, self.flush_interval_sec),
                )
            except asyncio.TimeoutError:
                # Timeout reached with no new item: flush partial batch if any
                if batch:
                    await self._flush_batch(batch)
                    batch = []
                continue
            except asyncio.CancelledError:
                break

            # Check for flush sentinel
            if isinstance(item, tuple) and item[0] == "__FLUSH__":
                if batch:
                    await self._flush_batch(batch)
                    batch = []
                flush_fut = item[1]
                if not flush_fut.done():
                    flush_fut.set_result(True)
                self.queue.task_done()
                continue

            batch.append(item)
            self.queue.task_done()

            # 2. Gather additional items up to batch_size or until flush_interval_sec expires
            batch_start = time.time()
            while len(batch) < self.batch_size and not self._stop_event.is_set():
                elapsed = time.time() - batch_start
                remaining = self.flush_interval_sec - elapsed
                if remaining <= 0:
                    break

                try:
                    next_item = await asyncio.wait_for(self.queue.get(), timeout=remaining)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    break

                if isinstance(next_item, tuple) and next_item[0] == "__FLUSH__":
                    # Sentinel encountered mid-batch: flush accumulated batch and complete future
                    await self._flush_batch(batch)
                    batch = []
                    flush_fut = next_item[1]
                    if not flush_fut.done():
                        flush_fut.set_result(True)
                    self.queue.task_done()
                    break

                batch.append(next_item)
                self.queue.task_done()

            # 3. Write full or timed-out batch
            if batch:
                await self._flush_batch(batch)
                batch = []

        # Flush any remaining items in batch before exit
        if batch:
            await self._flush_batch(batch)
        await self._drain_remaining()

    async def _drain_remaining(self) -> int:
        """Drain any lingering records from queue and flush to SQLite."""
        drain_batch: List[Dict[str, Any]] = []
        q = self.queue
        while not q.empty():
            try:
                item = q.get_nowait()
                if isinstance(item, tuple) and item[0] == "__FLUSH__":
                    if not item[1].done():
                        item[1].set_result(True)
                else:
                    drain_batch.append(item)
                q.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break

        if drain_batch:
            return await self._flush_batch(drain_batch)
        return 0

    def _is_worker_alive(self) -> bool:
        """Check if background worker task is alive and on the current running loop."""
        if self._worker_task is None or self._worker_task.done():
            return False
        try:
            current_loop = asyncio.get_running_loop()
            task_loop = getattr(self._worker_task, "_loop", None)
            if task_loop is not None and (task_loop.is_closed() or task_loop is not current_loop):
                return False
        except RuntimeError:
            return False
        return True

    async def start(self) -> None:
        """Initialize database schema and launch background worker loop."""
        if self._is_running and self._is_worker_alive():
            return

        await asyncio.to_thread(self._init_db_sync)
        # Reset queue if foreign or closed loop
        try:
            current_loop = asyncio.get_running_loop()
            q_loop = getattr(self._queue, "_loop", None)
            if q_loop is not None and (q_loop.is_closed() or q_loop is not current_loop):
                self._queue = asyncio.Queue()
        except RuntimeError:
            pass

        self._stop_event = asyncio.Event()
        self._is_running = True
        self._worker_task = asyncio.create_task(
            self._worker_loop(),
            name=f"audit-logger-worker-{self.db_path}",
        )

    async def flush(self, timeout: float = 1.0) -> int:
        """Force flush all currently queued audit records immediately and wait for disk commit."""
        if not self._is_running or not self._is_worker_alive():
            return await self._drain_remaining()

        loop = asyncio.get_running_loop()
        flush_fut = loop.create_future()
        await self.queue.put(("__FLUSH__", flush_fut))
        try:
            await asyncio.wait_for(flush_fut, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            await self._drain_remaining()
        return self._flushed_count

    async def stop(self, timeout: float = 1.0) -> None:
        """Gracefully stop worker, flush all buffered records, and close connection."""
        if self._is_worker_alive():
            try:
                await self.flush(timeout=timeout)
            except Exception:
                pass

        self._stop_event.set()

        if self._worker_task is not None and not self._worker_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._worker_task), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except Exception:
                    pass

        # Final drain check
        await self._drain_remaining()

        # Close SQLite connection
        if self._conn is not None:
            def _close_sync():
                if self._conn is not None:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
            await asyncio.to_thread(_close_sync)

        self._is_running = False

    async def count_logs(self) -> int:
        """Return total count of audit logs in the database."""
        def _count():
            self._init_db_sync()
            assert self._conn is not None
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM decision_audit_logs;")
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        return await asyncio.to_thread(_count)

    async def get_logs_for_event(self, event_id: str) -> List[Dict[str, Any]]:
        """Retrieve audit log records for a specific event_id."""
        def _query():
            self._init_db_sync()
            assert self._conn is not None
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM decision_audit_logs WHERE event_id = ? ORDER BY id ASC;",
                (event_id,),
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if d.get("features"):
                    try:
                        d["features"] = json.loads(d["features"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                results.append(d)
            return results
        return await asyncio.to_thread(_query)

    async def clear(self) -> None:
        """Clear audit logs table (useful in test tear-downs)."""
        def _clear():
            self._init_db_sync()
            assert self._conn is not None
            self._conn.execute("DELETE FROM decision_audit_logs;")
            self._conn.commit()
        await asyncio.to_thread(_clear)


# Global singleton audit logger
audit_logger = AuditLogger()

__all__ = [
    "AuditLogger",
    "audit_logger",
    "CREATE_AUDIT_TABLE_SQL",
    "CREATE_AUDIT_INDEXES_SQL",
    "INSERT_AUDIT_LOG_SQL",
]
