import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .clients.hetzner import HetznerClient
from .clients.truenas import TrueNASClient
from .db.database import get_connection
from .db.repository import insert_hetzner_snapshot, insert_truenas_snapshot
from .models import HetznerSnapshot, TrueNASSnapshot

logger = logging.getLogger(__name__)


def create_scheduler(
    hetzner_client: HetznerClient,
    truenas_client: TrueNASClient,
    db_path: str,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    interval_hours = int(os.getenv("COLLECTION_INTERVAL_HOURS", "1"))

    async def collect_all() -> None:
        now = datetime.now(timezone.utc)
        conn = get_connection(db_path)
        try:
            try:
                boxes = await hetzner_client.get_storageboxes()
                for box in boxes:
                    insert_hetzner_snapshot(
                        conn,
                        HetznerSnapshot(
                            timestamp=now,
                            storagebox_id=box.id,
                            name=box.name,
                            product=box.product,
                            disk_quota=box.disk_quota,
                            disk_usage=box.disk_usage,
                        ),
                    )
                logger.info("Collected %d Hetzner storagebox snapshot(s)", len(boxes))
            except Exception:
                logger.exception("Failed to collect Hetzner data")

            try:
                pools = await truenas_client.get_pools()
                for pool in pools:
                    insert_truenas_snapshot(
                        conn,
                        TrueNASSnapshot(
                            timestamp=now,
                            pool_name=pool.name,
                            size=pool.size,
                            allocated=pool.allocated,
                            free=pool.free,
                        ),
                    )
                logger.info("Collected %d TrueNAS pool snapshot(s)", len(pools))
            except Exception:
                logger.exception("Failed to collect TrueNAS data")
        finally:
            conn.close()

    scheduler.add_job(
        collect_all,
        trigger=IntervalTrigger(hours=interval_hours),
        id="collect_all",
        replace_existing=True,
    )

    # expose for manual trigger
    scheduler.collect_all = collect_all  # type: ignore[attr-defined]

    return scheduler
