"""PulseFlow pipeline: Database Manager.

Asynchronous SQLite connection and lifecycle management using aiosqlite.
"""

import asyncio
from typing import Optional
import aiosqlite
from pipeline.storage.schema import CREATE_PROCESSED_EVENTS_TABLE, CREATE_INDEXES


class DatabaseManager:
    """Manages asynchronous SQLite connections and schema initialization."""

    def __init__(self, db_path: str = "pulseflow.db") -> None:
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
            if self._lock is not None:
                lock_loop = getattr(self._lock, "_loop", None)
                if lock_loop is not None and (lock_loop.is_closed() or lock_loop is not current_loop):
                    self._lock = None
        except RuntimeError:
            pass
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def connect(self) -> aiosqlite.Connection:
        """Establish or return an active connection to SQLite."""
        lock = self._get_lock()
        async with lock:
            if self._connection is not None:
                # Check if connection's thread/loop is still valid
                conn_loop = getattr(self._connection, "_loop", None)
                try:
                    current_loop = asyncio.get_running_loop()
                    if conn_loop is not None and (conn_loop.is_closed() or conn_loop is not current_loop):
                        self._connection = None
                except RuntimeError:
                    pass

            if self._connection is None:
                self._connection = await aiosqlite.connect(self.db_path)
                self._connection.row_factory = aiosqlite.Row
            return self._connection

    async def init_db(self) -> None:
        """Initialize database schema, tables, and indexes."""
        conn = await self.connect()
        await conn.execute(CREATE_PROCESSED_EVENTS_TABLE)
        for idx_sql in CREATE_INDEXES:
            await conn.execute(idx_sql)
        await conn.commit()

    async def close(self) -> None:
        """Close active database connection."""
        lock = self._get_lock()
        async with lock:
            if self._connection is not None:
                try:
                    await self._connection.close()
                except Exception:
                    pass
                self._connection = None


# Default shared database instance
database_manager = DatabaseManager()

__all__ = ["DatabaseManager", "database_manager"]
