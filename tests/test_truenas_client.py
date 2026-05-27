import pytest
import respx
import httpx

from src.clients.truenas import TrueNASClient, _parse_zfs_value
from tests.conftest import TRUENAS_POOLS_RESPONSE

BASE = "http://truenas.test"

# TrueNAS CORE-style pool response: no top-level size/allocated/free
TRUENAS_CORE_POOL_RESPONSE = [
    {
        "id": 1,
        "name": "storage",
        "status": "ONLINE",
        "healthy": True,
        "topology": {},
        "scan": {},
    }
]

# TrueNAS CORE-style dataset response (nested ZFS property dicts)
TRUENAS_CORE_DATASET_RESPONSE = [
    {
        "id": "storage",
        "name": "storage",
        "pool": "storage",
        "type": "FILESYSTEM",
        "used": {"parsed": 17_550_846_386_176, "rawvalue": "17550846386176", "value": "16 TiB"},
        "available": {"parsed": 1_354_341_474_304, "rawvalue": "1354341474304", "value": "1.2 TiB"},
    }
]


def _mock_dataset_empty():
    respx.get(f"{BASE}/api/v2.0/pool/dataset").mock(
        return_value=httpx.Response(200, json=[])
    )


@pytest.fixture
def client():
    return TrueNASClient(base_url=BASE, api_key="test-key", verify_ssl=False)


# ── _parse_zfs_value unit tests ───────────────────────────────────────────────

def test_parse_zfs_value_plain_int():
    assert _parse_zfs_value(12345) == 12345


def test_parse_zfs_value_dict_parsed():
    assert _parse_zfs_value({"parsed": 999, "rawvalue": "999"}) == 999


def test_parse_zfs_value_dict_rawvalue_fallback():
    assert _parse_zfs_value({"rawvalue": "888"}) == 888


def test_parse_zfs_value_string():
    assert _parse_zfs_value("42000") == 42000


def test_parse_zfs_value_none():
    assert _parse_zfs_value(None) == 0


def test_parse_zfs_value_empty_dict():
    assert _parse_zfs_value({}) == 0


# ── TrueNAS SCALE (flat fields in pool response) ─────────────────────────────

@respx.mock
async def test_get_pools_scale_returns_flat_fields(client):
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=TRUENAS_POOLS_RESPONSE)
    )
    _mock_dataset_empty()
    pools = await client.get_pools()
    assert len(pools) == 1
    pool = pools[0]
    assert pool.name == "tank"
    assert pool.status == "ONLINE"
    assert pool.size == 10_000_000_000_000
    assert pool.allocated == 3_000_000_000_000
    assert pool.free == 7_000_000_000_000


@respx.mock
async def test_get_pools_scale_string_values_coerced(client):
    string_response = [
        {
            "id": 1,
            "name": "tank",
            "status": "ONLINE",
            "size": "10000000000000",
            "allocated": "3000000000000",
            "free": "7000000000000",
        }
    ]
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=string_response)
    )
    _mock_dataset_empty()
    pools = await client.get_pools()
    assert pools[0].size == 10_000_000_000_000
    assert pools[0].allocated == 3_000_000_000_000


# ── TrueNAS CORE (size/allocated/free come from dataset endpoint) ─────────────

@respx.mock
async def test_get_pools_core_uses_dataset_stats(client):
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=TRUENAS_CORE_POOL_RESPONSE)
    )
    respx.get(f"{BASE}/api/v2.0/pool/dataset").mock(
        return_value=httpx.Response(200, json=TRUENAS_CORE_DATASET_RESPONSE)
    )
    pools = await client.get_pools()
    assert len(pools) == 1
    pool = pools[0]
    assert pool.name == "storage"
    assert pool.allocated == 17_550_846_386_176
    assert pool.free == 1_354_341_474_304
    assert pool.size == 17_550_846_386_176 + 1_354_341_474_304


@respx.mock
async def test_get_pools_core_dataset_endpoint_fails_gracefully(client):
    """If dataset endpoint fails, pool is still returned with zero stats."""
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=TRUENAS_CORE_POOL_RESPONSE)
    )
    respx.get(f"{BASE}/api/v2.0/pool/dataset").mock(
        return_value=httpx.Response(500, text="error")
    )
    pools = await client.get_pools()
    assert len(pools) == 1
    assert pools[0].size == 0
    assert pools[0].allocated == 0


@respx.mock
async def test_get_pools_core_dataset_only_root_dataset_used(client):
    """Only root datasets (id == pool_name) should contribute stats."""
    dataset_response = [
        {
            "id": "storage/dataset1",
            "name": "storage/dataset1",
            "pool": "storage",
            "type": "FILESYSTEM",
            "used": {"parsed": 5_000_000_000, "rawvalue": "5000000000"},
            "available": {"parsed": 1_000_000_000, "rawvalue": "1000000000"},
        }
    ]
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=TRUENAS_CORE_POOL_RESPONSE)
    )
    respx.get(f"{BASE}/api/v2.0/pool/dataset").mock(
        return_value=httpx.Response(200, json=dataset_response)
    )
    pools = await client.get_pools()
    # Non-root datasets must not be used → stats stay at 0
    assert pools[0].size == 0


# ── Common behaviour ──────────────────────────────────────────────────────────

@respx.mock
async def test_get_pool_by_name(client):
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=TRUENAS_POOLS_RESPONSE)
    )
    _mock_dataset_empty()
    pool = await client.get_pool("tank")
    assert pool is not None
    assert pool.name == "tank"


@respx.mock
async def test_get_pool_not_found(client):
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=TRUENAS_POOLS_RESPONSE)
    )
    _mock_dataset_empty()
    pool = await client.get_pool("nonexistent")
    assert pool is None


@respx.mock
async def test_get_pools_empty(client):
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=[])
    )
    pools = await client.get_pools()
    assert pools == []


@respx.mock
async def test_get_pools_unauthorized(client):
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(403, json={"message": "Not authenticated"})
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await client.get_pools()
    assert exc.value.response.status_code == 403


@respx.mock
async def test_get_pools_server_error(client):
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(500, text="error")
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_pools()


@respx.mock
async def test_uses_bearer_auth(client):
    route = respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=TRUENAS_POOLS_RESPONSE)
    )
    _mock_dataset_empty()
    await client.get_pools()
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-key"


@respx.mock
async def test_get_pools_multiple(client):
    two_pools = [
        TRUENAS_POOLS_RESPONSE[0],
        {
            "id": 2,
            "name": "backup",
            "status": "ONLINE",
            "size": 4_000_000_000_000,
            "allocated": 1_000_000_000_000,
            "free": 3_000_000_000_000,
        },
    ]
    respx.get(f"{BASE}/api/v2.0/pool").mock(
        return_value=httpx.Response(200, json=two_pools)
    )
    _mock_dataset_empty()
    pools = await client.get_pools()
    assert len(pools) == 2
    assert pools[1].name == "backup"
