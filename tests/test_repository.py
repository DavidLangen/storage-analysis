import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.db.repository import (
    get_hetzner_history,
    get_hetzner_storagebox_ids,
    get_latest_hetzner_snapshots,
    get_latest_truenas_snapshots,
    get_truenas_history,
    get_truenas_pool_names,
    insert_hetzner_snapshot,
    insert_truenas_snapshot,
)
from src.models import HetznerSnapshot, TrueNASSnapshot

NOW = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
EARLIER = NOW - timedelta(hours=2)
YESTERDAY = NOW - timedelta(days=1)
LAST_WEEK = NOW - timedelta(days=7)


def _hetzner(ts=NOW, storagebox_id=123, disk_usage=2_000_000_000_000):
    return HetznerSnapshot(
        timestamp=ts,
        storagebox_id=storagebox_id,
        name="backup-box",
        product="BX31",
        disk_quota=5_000_000_000_000,
        disk_usage=disk_usage,
    )


def _truenas(ts=NOW, pool_name="tank", allocated=3_000_000_000_000):
    return TrueNASSnapshot(
        timestamp=ts,
        pool_name=pool_name,
        size=10_000_000_000_000,
        allocated=allocated,
        free=10_000_000_000_000 - allocated,
    )


def test_insert_hetzner_snapshot(test_db):
    insert_hetzner_snapshot(test_db, _hetzner())
    rows = test_db.execute("SELECT * FROM hetzner_snapshots").fetchall()
    assert len(rows) == 1
    assert rows[0]["storagebox_id"] == 123
    assert rows[0]["disk_usage"] == 2_000_000_000_000


def test_insert_truenas_snapshot(test_db):
    insert_truenas_snapshot(test_db, _truenas())
    rows = test_db.execute("SELECT * FROM truenas_snapshots").fetchall()
    assert len(rows) == 1
    assert rows[0]["pool_name"] == "tank"
    assert rows[0]["allocated"] == 3_000_000_000_000


def test_get_hetzner_history_returns_matching(test_db):
    insert_hetzner_snapshot(test_db, _hetzner(ts=NOW))
    insert_hetzner_snapshot(test_db, _hetzner(ts=YESTERDAY))
    since = NOW - timedelta(hours=1)
    result = get_hetzner_history(test_db, 123, since)
    assert len(result) == 1
    assert result[0]["disk_usage"] == 2_000_000_000_000


def test_get_hetzner_history_empty_when_no_match(test_db):
    insert_hetzner_snapshot(test_db, _hetzner(ts=LAST_WEEK))
    since = YESTERDAY
    result = get_hetzner_history(test_db, 123, since)
    assert result == []


def test_get_hetzner_history_filters_by_storagebox_id(test_db):
    insert_hetzner_snapshot(test_db, _hetzner(storagebox_id=123))
    insert_hetzner_snapshot(test_db, _hetzner(storagebox_id=456))
    result = get_hetzner_history(test_db, 123, LAST_WEEK)
    assert all(r["storagebox_id"] == 123 for r in result)
    assert len(result) == 1


def test_get_truenas_history_returns_matching(test_db):
    insert_truenas_snapshot(test_db, _truenas(ts=NOW))
    insert_truenas_snapshot(test_db, _truenas(ts=YESTERDAY))
    since = NOW - timedelta(hours=1)
    result = get_truenas_history(test_db, "tank", since)
    assert len(result) == 1


def test_get_truenas_history_empty(test_db):
    result = get_truenas_history(test_db, "tank", LAST_WEEK)
    assert result == []


def test_get_truenas_history_filters_by_pool(test_db):
    insert_truenas_snapshot(test_db, _truenas(pool_name="tank"))
    insert_truenas_snapshot(test_db, _truenas(pool_name="backup"))
    result = get_truenas_history(test_db, "tank", LAST_WEEK)
    assert len(result) == 1
    assert result[0]["pool_name"] == "tank"


def test_get_latest_hetzner_returns_most_recent(test_db):
    insert_hetzner_snapshot(test_db, _hetzner(ts=EARLIER, disk_usage=1_000_000_000_000))
    insert_hetzner_snapshot(test_db, _hetzner(ts=NOW, disk_usage=2_000_000_000_000))
    latest = get_latest_hetzner_snapshots(test_db)
    assert len(latest) == 1
    assert latest[0]["disk_usage"] == 2_000_000_000_000


def test_get_latest_hetzner_one_per_storagebox(test_db):
    insert_hetzner_snapshot(test_db, _hetzner(storagebox_id=123, ts=NOW))
    insert_hetzner_snapshot(test_db, _hetzner(storagebox_id=456, ts=NOW))
    latest = get_latest_hetzner_snapshots(test_db)
    assert len(latest) == 2


def test_get_latest_truenas_returns_most_recent(test_db):
    insert_truenas_snapshot(test_db, _truenas(ts=EARLIER, allocated=1_000_000_000_000))
    insert_truenas_snapshot(test_db, _truenas(ts=NOW, allocated=3_000_000_000_000))
    latest = get_latest_truenas_snapshots(test_db)
    assert len(latest) == 1
    assert latest[0]["allocated"] == 3_000_000_000_000


def test_get_latest_truenas_empty(test_db):
    assert get_latest_truenas_snapshots(test_db) == []


def test_get_hetzner_storagebox_ids(test_db):
    insert_hetzner_snapshot(test_db, _hetzner(storagebox_id=123))
    insert_hetzner_snapshot(test_db, _hetzner(storagebox_id=456))
    ids = get_hetzner_storagebox_ids(test_db)
    assert set(ids) == {123, 456}


def test_get_truenas_pool_names(test_db):
    insert_truenas_snapshot(test_db, _truenas(pool_name="tank"))
    insert_truenas_snapshot(test_db, _truenas(pool_name="backup"))
    names = get_truenas_pool_names(test_db)
    assert set(names) == {"tank", "backup"}


def test_history_ordered_by_timestamp(test_db):
    insert_hetzner_snapshot(test_db, _hetzner(ts=NOW, disk_usage=200))
    insert_hetzner_snapshot(test_db, _hetzner(ts=EARLIER, disk_usage=100))
    result = get_hetzner_history(test_db, 123, LAST_WEEK)
    assert result[0]["disk_usage"] == 100
    assert result[1]["disk_usage"] == 200
