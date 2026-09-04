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
        self._lock = asyncio.Lock()

    async def connect(self) -> aiosqlite.Connection:
        """Establish or return an active connection to SQLite."""
        async with self._lock:
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
        async with self._lock:
            if self._connection is not None:
                await self._connection.close()
                self._connection = None


# Default shared database instance
database_manager = DatabaseManager()

__all__ = ["DatabaseManager", "database_manager"]
