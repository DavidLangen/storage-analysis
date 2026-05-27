import sqlite3
from datetime import datetime

from ..models import HetznerSnapshot, TrueNASSnapshot


def insert_hetzner_snapshot(conn: sqlite3.Connection, snapshot: HetznerSnapshot) -> None:
    conn.execute(
        """
        INSERT INTO hetzner_snapshots (timestamp, storagebox_id, name, product, disk_quota, disk_usage)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.timestamp.isoformat(),
            snapshot.storagebox_id,
            snapshot.name,
            snapshot.product,
            snapshot.disk_quota,
            snapshot.disk_usage,
        ),
    )
    conn.commit()


def insert_truenas_snapshot(conn: sqlite3.Connection, snapshot: TrueNASSnapshot) -> None:
    conn.execute(
        """
        INSERT INTO truenas_snapshots (timestamp, pool_name, size, allocated, free)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            snapshot.timestamp.isoformat(),
            snapshot.pool_name,
            snapshot.size,
            snapshot.allocated,
            snapshot.free,
        ),
    )
    conn.commit()


def get_hetzner_history(
    conn: sqlite3.Connection, storagebox_id: int, since: datetime
) -> list[dict]:
    cursor = conn.execute(
        """
        SELECT timestamp, storagebox_id, name, product, disk_quota, disk_usage
        FROM hetzner_snapshots
        WHERE storagebox_id = ? AND timestamp >= ?
        ORDER BY timestamp
        """,
        (storagebox_id, since.isoformat()),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_truenas_history(
    conn: sqlite3.Connection, pool_name: str, since: datetime
) -> list[dict]:
    cursor = conn.execute(
        """
        SELECT timestamp, pool_name, size, allocated, free
        FROM truenas_snapshots
        WHERE pool_name = ? AND timestamp >= ?
        ORDER BY timestamp
        """,
        (pool_name, since.isoformat()),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_latest_hetzner_snapshots(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute(
        """
        SELECT h.*
        FROM hetzner_snapshots h
        INNER JOIN (
            SELECT storagebox_id, MAX(timestamp) AS max_ts
            FROM hetzner_snapshots
            GROUP BY storagebox_id
        ) latest ON h.storagebox_id = latest.storagebox_id AND h.timestamp = latest.max_ts
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def get_latest_truenas_snapshots(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute(
        """
        SELECT t.*
        FROM truenas_snapshots t
        INNER JOIN (
            SELECT pool_name, MAX(timestamp) AS max_ts
            FROM truenas_snapshots
            GROUP BY pool_name
        ) latest ON t.pool_name = latest.pool_name AND t.timestamp = latest.max_ts
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def get_hetzner_storagebox_ids(conn: sqlite3.Connection) -> list[int]:
    cursor = conn.execute("SELECT DISTINCT storagebox_id FROM hetzner_snapshots")
    return [row[0] for row in cursor.fetchall()]


def get_truenas_pool_names(conn: sqlite3.Connection) -> list[str]:
    cursor = conn.execute("SELECT DISTINCT pool_name FROM truenas_snapshots")
    return [row[0] for row in cursor.fetchall()]
