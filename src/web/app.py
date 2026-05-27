import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from ..clients.hetzner import HetznerClient
from ..clients.truenas import TrueNASClient
from ..db.database import get_connection, init_db
from ..db.repository import (
    get_hetzner_history,
    get_hetzner_storagebox_ids,
    get_latest_hetzner_snapshots,
    get_latest_truenas_snapshots,
    get_truenas_history,
    get_truenas_pool_names,
)
from ..models import CombinedStats, DownscaleThreshold
from ..scheduler import create_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Hetzner plans ordered smallest to largest (decimal TB, confirmed from Robot panel)
HETZNER_PLANS: list[tuple[str, int]] = [
    ("BX11", 1_000_000_000_000),
    ("BX21", 5_000_000_000_000),
    ("BX31", 10_000_000_000_000),
    ("BX41", 20_000_000_000_000),
]

_hetzner_client: HetznerClient | None = None
_truenas_client: TrueNASClient | None = None
_db_path: str = ""
_scheduler = None


def _build_clients() -> tuple[HetznerClient, TrueNASClient]:
    hetzner = HetznerClient(
        host=os.environ["HETZNER_STORAGEBOX_HOST"],
        username=os.environ["HETZNER_STORAGEBOX_USER"],
        password=os.environ["HETZNER_STORAGEBOX_PASSWORD"],
        port=int(os.getenv("HETZNER_STORAGEBOX_PORT", "23")),
        product=os.getenv("HETZNER_STORAGEBOX_PRODUCT"),
    )
    truenas = TrueNASClient(
        base_url=os.environ["TRUENAS_BASE_URL"],
        api_key=os.environ["TRUENAS_API_KEY"],
        verify_ssl=os.getenv("TRUENAS_VERIFY_SSL", "true").lower() != "false",
    )
    return hetzner, truenas


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _hetzner_client, _truenas_client, _db_path, _scheduler

    _db_path = os.getenv("DB_PATH", "/data/storage.db")
    Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(_db_path)
    init_db(conn)
    conn.close()

    _hetzner_client, _truenas_client = _build_clients()
    _scheduler = create_scheduler(_hetzner_client, _truenas_client, _db_path)
    _scheduler.start()
    logger.info("Scheduler started, collecting every %s hour(s)", os.getenv("COLLECTION_INTERVAL_HOURS", "1"))

    yield

    _scheduler.shutdown(wait=False)


app = FastAPI(title="Storage Analysis", lifespan=lifespan)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_db():
    conn = get_connection(_db_path)
    try:
        yield conn
    finally:
        conn.close()


DbDep = Annotated[object, Depends(get_db)]


def _find_next_smaller_plan(product: str, disk_quota: int) -> tuple[str, int] | tuple[None, None]:
    """Return (product_name, quota_bytes) for the next smaller Hetzner plan."""
    # Try exact match first, fallback to quota-based position
    plan_names = [p[0] for p in HETZNER_PLANS]
    if product in plan_names:
        idx = plan_names.index(product)
        if idx > 0:
            return HETZNER_PLANS[idx - 1]
        return None, None

    # fallback: find by quota
    for i, (name, quota) in enumerate(HETZNER_PLANS):
        if quota >= disk_quota and i > 0:
            return HETZNER_PLANS[i - 1]
    return None, None


def _compute_downscale_thresholds(
    latest_hetzner: list[dict],
    truenas_free_total: int,
) -> list[DownscaleThreshold]:
    thresholds = []
    for row in latest_hetzner:
        next_product, next_quota = _find_next_smaller_plan(row["product"], row["disk_quota"])
        disk_used = row["disk_usage"]
        if next_product is None or next_quota is None:
            data_to_move = 0
            can_downscale = False
            threshold_met = False
        else:
            data_to_move = max(0, disk_used - next_quota)
            can_downscale = disk_used <= next_quota
            threshold_met = truenas_free_total >= data_to_move

        thresholds.append(
            DownscaleThreshold(
                storagebox_id=row["storagebox_id"],
                storagebox_name=row["name"],
                current_product=row["product"],
                current_quota_bytes=row["disk_quota"],
                disk_used_bytes=disk_used,
                next_smaller_product=next_product,
                next_smaller_quota_bytes=next_quota,
                data_to_move_bytes=data_to_move,
                can_downscale=can_downscale,
                truenas_free_bytes=truenas_free_total,
                threshold_met=threshold_met,
            )
        )
    return thresholds


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/hetzner/history")
async def hetzner_history(
    db=Depends(get_db),
    storagebox_id: int = Query(..., description="Storagebox ID"),
    days: int = Query(30, ge=1, le=365),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return get_hetzner_history(db, storagebox_id, since)


@app.get("/api/hetzner/ids")
async def hetzner_ids(db=Depends(get_db)):
    return get_hetzner_storagebox_ids(db)


@app.get("/api/truenas/history")
async def truenas_history(
    db=Depends(get_db),
    pool: str = Query(..., description="Pool name"),
    days: int = Query(30, ge=1, le=365),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return get_truenas_history(db, pool, since)


@app.get("/api/truenas/pools")
async def truenas_pools(db=Depends(get_db)):
    return get_truenas_pool_names(db)


@app.get("/api/combined", response_model=CombinedStats)
async def combined(db=Depends(get_db)):
    latest_hetzner = get_latest_hetzner_snapshots(db)
    latest_truenas = get_latest_truenas_snapshots(db)

    total_hetzner_quota = sum(r["disk_quota"] for r in latest_hetzner)
    total_hetzner_used = sum(r["disk_usage"] for r in latest_hetzner)
    total_truenas_size = sum(r["size"] for r in latest_truenas)
    total_truenas_allocated = sum(r["allocated"] for r in latest_truenas)
    total_truenas_free = sum(r["free"] for r in latest_truenas)

    from ..models import StorageBox, TrueNASPool

    hetzner_boxes = [
        StorageBox(
            id=r["storagebox_id"],
            login="",
            name=r["name"],
            product=r["product"],
            disk_quota=r["disk_quota"],
            disk_usage=r["disk_usage"],
        )
        for r in latest_hetzner
    ]
    truenas_pool_models = [
        TrueNASPool(
            id=0,
            name=r["pool_name"],
            status="ONLINE",
            size=r["size"],
            allocated=r["allocated"],
            free=r["free"],
        )
        for r in latest_truenas
    ]

    thresholds = _compute_downscale_thresholds(latest_hetzner, total_truenas_free)

    return CombinedStats(
        total_quota_bytes=total_hetzner_quota + total_truenas_size,
        total_used_bytes=total_hetzner_used + total_truenas_allocated,
        total_free_bytes=(total_hetzner_quota - total_hetzner_used) + total_truenas_free,
        hetzner_storageboxes=hetzner_boxes,
        truenas_pools=truenas_pool_models,
        downscale_thresholds=thresholds,
    )


@app.post("/api/collect")
async def trigger_collect():
    if _scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    await _scheduler.collect_all()
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("WEB_PORT", "8000"))
    uvicorn.run("src.web.app:app", host="0.0.0.0", port=port, reload=False)
