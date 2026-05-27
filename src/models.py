from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


class StorageBox(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    login: str
    name: str
    product: str
    disk_quota: int
    disk_usage: int
    disk_usage_data: int = 0
    disk_usage_snapshots: int = 0


class TrueNASPool(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    status: str
    size: int = 0
    allocated: int = 0
    free: int = 0

    @field_validator("size", "allocated", "free", mode="before")
    @classmethod
    def coerce_to_int(cls, v: object) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0


class HetznerSnapshot(BaseModel):
    timestamp: datetime
    storagebox_id: int
    name: str
    product: str
    disk_quota: int
    disk_usage: int


class TrueNASSnapshot(BaseModel):
    timestamp: datetime
    pool_name: str
    size: int
    allocated: int
    free: int


class DownscaleThreshold(BaseModel):
    storagebox_id: int
    storagebox_name: str
    current_product: str
    current_quota_bytes: int
    disk_used_bytes: int
    next_smaller_product: str | None
    next_smaller_quota_bytes: int | None
    data_to_move_bytes: int
    can_downscale: bool
    truenas_free_bytes: int
    threshold_met: bool


class CombinedStats(BaseModel):
    total_quota_bytes: int
    total_used_bytes: int
    total_free_bytes: int
    hetzner_storageboxes: list[StorageBox]
    truenas_pools: list[TrueNASPool]
    downscale_thresholds: list[DownscaleThreshold]
