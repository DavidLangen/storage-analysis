import asyncio
from functools import partial

import paramiko

from ..models import StorageBox

# Confirmed plan sizes from Hetzner Robot panel (decimal TB)
HETZNER_PLANS: list[tuple[str, int]] = [
    ("BX11", 1_000_000_000_000),
    ("BX21", 5_000_000_000_000),
    ("BX31", 10_000_000_000_000),   # confirmed: 10 TB
    ("BX41", 20_000_000_000_000),
]


def _detect_product(quota_bytes: int) -> str:
    """Return the Hetzner plan name closest to the given quota."""
    for name, size in HETZNER_PLANS:
        if quota_bytes <= size * 1.15:  # 15 % tolerance for filesystem overhead
            return name
    return HETZNER_PLANS[-1][0]


class HetznerClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 23,
        product: str | None = None,
    ) -> None:
        self._host = host
        self._username = username
        self._password = password
        self._port = port
        self._product_override = product

    def _fetch_stats_sync(self) -> StorageBox:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                timeout=30,
            )
            _, stdout, _ = ssh.exec_command("df -B1 /")
            lines = stdout.read().decode().strip().splitlines()
            # df output: Filesystem 1B-blocks Used Available Use% Mounted
            parts = lines[-1].split()
            total = int(parts[1])
            used = int(parts[2])
            product = self._product_override or _detect_product(total)
            return StorageBox(
                id=0,
                login=self._username,
                name=self._host,
                product=product,
                disk_quota=total,
                disk_usage=used,
            )
        finally:
            ssh.close()

    async def get_storageboxes(self) -> list[StorageBox]:
        loop = asyncio.get_event_loop()
        box = await loop.run_in_executor(None, self._fetch_stats_sync)
        return [box]

    async def get_storagebox(self, storagebox_id: int) -> StorageBox:
        boxes = await self.get_storageboxes()
        return boxes[0]
