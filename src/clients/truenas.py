import httpx

from ..models import TrueNASPool


def _parse_zfs_value(v: object) -> int:
    """Extract integer bytes from a ZFS property value.

    TrueNAS CORE wraps numeric fields as {"parsed": 12345, "rawvalue": "12345", ...}.
    TrueNAS SCALE returns plain integers. Both cases are handled here.
    """
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, dict):
        for key in ("parsed", "rawvalue", "value"):
            raw = v.get(key)
            if raw is not None:
                try:
                    return int(raw)
                except (ValueError, TypeError):
                    continue
    if isinstance(v, str):
        try:
            return int(v)
        except (ValueError, TypeError):
            pass
    return 0


class TrueNASClient:
    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = True) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._verify_ssl = verify_ssl

    async def get_pools(self) -> list[TrueNASPool]:
        async with httpx.AsyncClient(
            headers=self._headers,
            verify=self._verify_ssl,
            timeout=30,
        ) as client:
            pool_resp = await client.get(f"{self._base_url}/api/v2.0/pool")
            pool_resp.raise_for_status()
            pools_raw = pool_resp.json()

            pool_names = [p["name"] for p in pools_raw]
            dataset_stats = await self._fetch_root_dataset_stats(client, pool_names)

            result = []
            for pool in pools_raw:
                name = pool["name"]
                if name in dataset_stats:
                    pool.update(dataset_stats[name])
                result.append(TrueNASPool(**pool))
            return result

    async def _fetch_root_dataset_stats(
        self, client: httpx.AsyncClient, pool_names: list[str]
    ) -> dict[str, dict]:
        """Fetch size/allocated/free from root datasets (needed for TrueNAS CORE)."""
        try:
            resp = await client.get(f"{self._base_url}/api/v2.0/pool/dataset")
            resp.raise_for_status()
            stats: dict[str, dict] = {}
            for ds in resp.json():
                ds_id = ds.get("id") or ds.get("name", "")
                if ds_id not in pool_names:
                    continue
                used = _parse_zfs_value(ds.get("used", 0))
                available = _parse_zfs_value(ds.get("available", 0))
                stats[ds_id] = {
                    "allocated": used,
                    "free": available,
                    "size": used + available,
                }
            return stats
        except Exception:
            return {}

    async def get_pool(self, name: str) -> TrueNASPool | None:
        pools = await self.get_pools()
        return next((p for p in pools if p.name == name), None)
