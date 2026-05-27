import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS hetzner_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    storagebox_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    product TEXT NOT NULL,
    disk_quota INTEGER NOT NULL,
    disk_usage INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS truenas_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    pool_name TEXT NOT NULL,
    size INTEGER NOT NULL,
    allocated INTEGER NOT NULL,
    free INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hetzner_storagebox_ts ON hetzner_snapshots (storagebox_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_truenas_pool_ts ON truenas_snapshots (pool_name, timestamp);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
