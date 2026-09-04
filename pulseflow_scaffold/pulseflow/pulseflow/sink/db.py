import sqlite3
from pathlib import Path

DB_PATH = Path("pulseflow.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            processing_mode TEXT,
            created_at TEXT,
            processed_at TEXT,
            latency_ms REAL
        )
        """
    )
    conn.commit()
    conn.close()
