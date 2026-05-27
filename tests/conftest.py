import sqlite3
from datetime import datetime, timezone

import pytest

from src.db.database import init_db
from src.models import HetznerSnapshot, TrueNASSnapshot


HETZNER_RESPONSE_LIST = [
    {
        "storagebox": {
            "id": 123,
            "login": "u123",
            "name": "backup-box",
            "product": "BX31",
            "disk_quota": 5_000_000_000_000,
            "disk_usage": 2_000_000_000_000,
            "disk_usage_data": 2_000_000_000_000,
            "disk_usage_snapshots": 0,
        }
    }
]

HETZNER_RESPONSE_SINGLE = {
    "storagebox": {
        "id": 123,
        "login": "u123",
        "name": "backup-box",
        "product": "BX31",
        "disk_quota": 5_000_000_000_000,
        "disk_usage": 2_000_000_000_000,
        "disk_usage_data": 2_000_000_000_000,
        "disk_usage_snapshots": 0,
    }
}

TRUENAS_POOLS_RESPONSE = [
    {
        "id": 1,
        "name": "tank",
        "status": "ONLINE",
        "size": 10_000_000_000_000,
        "allocated": 3_000_000_000_000,
        "free": 7_000_000_000_000,
    }
]


@pytest.fixture
def test_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


@pytest.fixture
def db_with_data(test_db: sqlite3.Connection) -> sqlite3.Connection:
    from src.db.repository import insert_hetzner_snapshot, insert_truenas_snapshot

    ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    insert_hetzner_snapshot(
        test_db,
        HetznerSnapshot(
            timestamp=ts,
            storagebox_id=123,
            name="backup-box",
            product="BX31",
            disk_quota=5_000_000_000_000,
            disk_usage=2_000_000_000_000,
        ),
    )
    insert_truenas_snapshot(
        test_db,
        TrueNASSnapshot(
            timestamp=ts,
            pool_name="tank",
            size=10_000_000_000_000,
            allocated=3_000_000_000_000,
            free=7_000_000_000_000,
        ),
    )
    return test_db
