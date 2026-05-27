import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.db.database import get_connection, init_db
from src.db.repository import insert_hetzner_snapshot, insert_truenas_snapshot
from src.models import HetznerSnapshot, TrueNASSnapshot
from src.web.app import _compute_downscale_thresholds, _find_next_smaller_plan, app

NOW = datetime.now(timezone.utc) - timedelta(hours=1)

_TEST_ENV = {
    "HETZNER_STORAGEBOX_HOST": "u123.your-storagebox.de",
    "HETZNER_STORAGEBOX_USER": "u123",
    "HETZNER_STORAGEBOX_PASSWORD": "test-pass",
    "TRUENAS_BASE_URL": "http://truenas.test",
    "TRUENAS_API_KEY": "test-api-key",
    "DB_PATH": "/tmp/storage_test_pytest.db",
}


@pytest.fixture
def mem_db():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


@pytest.fixture
def client_with_db(mem_db, monkeypatch):
    from src.web import app as web_module

    for k, v in _TEST_ENV.items():
        monkeypatch.setenv(k, v)

    mock_sched = MagicMock()
    mock_sched.collect_all = AsyncMock()

    def override_db():
        try:
            yield mem_db
        finally:
            pass

    app.dependency_overrides[web_module.get_db] = override_db

    with patch("src.web.app.create_scheduler", return_value=mock_sched):
        with TestClient(app) as c:
            yield c, mem_db

    app.dependency_overrides.clear()


def _seed(db: sqlite3.Connection):
    insert_hetzner_snapshot(
        db,
        HetznerSnapshot(
            timestamp=NOW,
            storagebox_id=123,
            name="backup-box",
            product="BX31",
            disk_quota=5_000_000_000_000,
            disk_usage=2_000_000_000_000,
        ),
    )
    insert_truenas_snapshot(
        db,
        TrueNASSnapshot(
            timestamp=NOW,
            pool_name="tank",
            size=10_000_000_000_000,
            allocated=3_000_000_000_000,
            free=7_000_000_000_000,
        ),
    )


# ── Downscale logic unit tests ────────────────────────────────────────────────

def test_find_next_smaller_plan_bx31():
    # BX31=10TB → next smaller is BX21=5TB
    product, quota = _find_next_smaller_plan("BX31", 10_000_000_000_000)
    assert product == "BX21"
    assert quota == 5_000_000_000_000


def test_find_next_smaller_plan_bx11_is_smallest():
    product, quota = _find_next_smaller_plan("BX11", 1_000_000_000_000)
    assert product is None
    assert quota is None


def test_find_next_smaller_plan_bx41():
    product, quota = _find_next_smaller_plan("BX41", 20_000_000_000_000)
    assert product == "BX31"
    assert quota == 10_000_000_000_000


def test_find_next_smaller_plan_unknown_falls_back_to_quota():
    # 5.5TB is between BX21(5TB) and BX31(10TB) → returns BX21
    product, quota = _find_next_smaller_plan("UNKNOWN", 5_500_000_000_000)
    assert product == "BX21"


def test_downscale_threshold_can_downscale():
    latest_hetzner = [
        {
            "storagebox_id": 1,
            "name": "box",
            "product": "BX31",
            "disk_quota": 10_000_000_000_000,
            "disk_usage": 3_000_000_000_000,  # fits in BX21 (5 TB)
        }
    ]
    truenas_free = 10_000_000_000_000
    thresholds = _compute_downscale_thresholds(latest_hetzner, truenas_free)
    assert len(thresholds) == 1
    t = thresholds[0]
    assert t.can_downscale is True
    assert t.data_to_move_bytes == 0
    assert t.threshold_met is True


def test_downscale_threshold_needs_to_move_data():
    latest_hetzner = [
        {
            "storagebox_id": 1,
            "name": "box",
            "product": "BX31",
            "disk_quota": 10_000_000_000_000,
            "disk_usage": 7_000_000_000_000,  # 2 TB over BX21 (5 TB)
        }
    ]
    truenas_free = 3_000_000_000_000
    thresholds = _compute_downscale_thresholds(latest_hetzner, truenas_free)
    t = thresholds[0]
    assert t.can_downscale is False
    assert t.data_to_move_bytes == 2_000_000_000_000
    assert t.threshold_met is True  # TrueNAS has 3TB free, 2TB needs to move


def test_downscale_threshold_truenas_too_full():
    latest_hetzner = [
        {
            "storagebox_id": 1,
            "name": "box",
            "product": "BX31",
            "disk_quota": 10_000_000_000_000,
            "disk_usage": 9_000_000_000_000,  # 4 TB over BX21 (5 TB)
        }
    ]
    truenas_free = 500_000_000_000  # only 500 GB free
    thresholds = _compute_downscale_thresholds(latest_hetzner, truenas_free)
    t = thresholds[0]
    assert t.threshold_met is False
    assert t.data_to_move_bytes == 4_000_000_000_000


def test_downscale_threshold_smallest_plan():
    latest_hetzner = [
        {
            "storagebox_id": 1,
            "name": "box",
            "product": "BX11",
            "disk_quota": 1_000_000_000_000,
            "disk_usage": 500_000_000_000,
        }
    ]
    thresholds = _compute_downscale_thresholds(latest_hetzner, 10_000_000_000_000)
    t = thresholds[0]
    assert t.next_smaller_product is None
    assert t.can_downscale is False
    assert t.threshold_met is False


# ── API endpoint tests ────────────────────────────────────────────────────────

def test_dashboard_returns_html(client_with_db):
    client, _ = client_with_db
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Storage Analysis" in resp.text


def test_combined_empty_db(client_with_db):
    client, _ = client_with_db
    resp = client.get("/api/combined")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_quota_bytes"] == 0
    assert data["total_used_bytes"] == 0
    assert data["downscale_thresholds"] == []


def test_combined_with_data(client_with_db):
    client, db = client_with_db
    _seed(db)
    resp = client.get("/api/combined")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_quota_bytes"] == 15_000_000_000_000
    assert data["total_used_bytes"] == 5_000_000_000_000
    assert data["total_free_bytes"] == 10_000_000_000_000
    assert len(data["hetzner_storageboxes"]) == 1
    assert len(data["truenas_pools"]) == 1
    assert len(data["downscale_thresholds"]) == 1


def test_hetzner_ids_empty(client_with_db):
    client, _ = client_with_db
    resp = client.get("/api/hetzner/ids")
    assert resp.status_code == 200
    assert resp.json() == []


def test_hetzner_ids_with_data(client_with_db):
    client, db = client_with_db
    _seed(db)
    resp = client.get("/api/hetzner/ids")
    assert 123 in resp.json()


def test_hetzner_history(client_with_db):
    client, db = client_with_db
    _seed(db)
    resp = client.get("/api/hetzner/history?storagebox_id=123&days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["disk_usage"] == 2_000_000_000_000


def test_hetzner_history_missing_id(client_with_db):
    client, _ = client_with_db
    resp = client.get("/api/hetzner/history?days=30")
    assert resp.status_code == 422


def test_truenas_pools(client_with_db):
    client, db = client_with_db
    _seed(db)
    resp = client.get("/api/truenas/pools")
    assert resp.status_code == 200
    assert "tank" in resp.json()


def test_truenas_history(client_with_db):
    client, db = client_with_db
    _seed(db)
    resp = client.get("/api/truenas/history?pool=tank&days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["allocated"] == 3_000_000_000_000


def test_truenas_history_missing_pool(client_with_db):
    client, _ = client_with_db
    resp = client.get("/api/truenas/history?days=30")
    assert resp.status_code == 422


def test_collect_endpoint(client_with_db):
    client, _ = client_with_db
    mock_collect = AsyncMock()
    with patch("src.web.app._scheduler") as mock_scheduler:
        mock_scheduler.collect_all = mock_collect
        resp = client.post("/api/collect")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
