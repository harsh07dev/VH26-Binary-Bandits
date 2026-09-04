"""PulseFlow pipeline: Storage Schema.

Defines the SQLite DDL for persisting processed events and their processing metrics.
"""

CREATE_PROCESSED_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    processing_mode TEXT NOT NULL,
    payload TEXT,
    received_at REAL,
    processed_at REAL NOT NULL,
    latency_ms REAL NOT NULL
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_processed_events_priority ON processed_events(priority);",
    "CREATE INDEX IF NOT EXISTS idx_processed_events_type ON processed_events(event_type);",
    "CREATE INDEX IF NOT EXISTS idx_processed_events_processed_at ON processed_events(processed_at);",
]
