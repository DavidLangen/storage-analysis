<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Chart.js-4.4-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-built--in-003B57?style=for-the-badge&logo=sqlite&logoColor=white" />
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/tests-66%20passed-34D399?style=for-the-badge&logo=pytest&logoColor=white" />
</p>

<h1 align="center">📦 Storage Analysis</h1>

<p align="center">
  A self-hosted, containerized monitoring dashboard for <strong>Hetzner Storageboxes</strong> and <strong>TrueNAS</strong>.
  Collects storage metrics on a schedule, persists them in SQLite, and visualises trends in a live web UI —
  including automated downscale recommendations.
</p>

---

## ✨ Features

| Feature | Details |
|---|---|
| **Multi-source collection** | Hetzner Storagebox via SSH/SFTP · TrueNAS CORE & SCALE via REST API |
| **Scheduled collection** | Configurable interval (default: every hour) via APScheduler |
| **Persistent storage** | Embedded SQLite — no external database required |
| **Live dashboard** | Dark-themed Chart.js UI with 7 / 30 / 90 day trend charts |
| **Downscale advisor** | Calculates whether your Hetzner box can be downgraded (BX41→BX31→…) and whether TrueNAS has enough free space to absorb the overflow |
| **Downgrade threshold line** | Visual annotation in the Hetzner trend chart showing exactly where the next plan boundary is |
| **One-shot collect** | "Collect now" button triggers an immediate snapshot |
| **Auto-refresh** | Dashboard refreshes every 5 minutes automatically |
| **Fully containerised** | Single Docker/Podman service, no manual Python setup |
| **Test suite** | 66 pytest tests covering clients, DB layer, and API endpoints |

---

## 🖥️ Dashboard Preview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Storage Analysis                          [7d] [30d] [90d]  ▶ Now  │
├──────────┬──────────┬──────────┬──────────┬────────────────────────┤
│ Total    │ Used     │ Free     │ Hetzner  │ TrueNAS                │
│ 20.0 TB  │ 10.2 TB  │ 9.8 TB  │ 7.2 TB   │ 3.0 TB                 │
├──────────┴──────────┴──────────┴──────────┴────────────────────────┤
│  TrueNAS — Trend          │  Hetzner Storagebox — Trend            │
│  ▓▓▓▓░░░░░░░░░░░ (chart)  │  ▓▓▓▓▓▓▓░ ·····BX21 limit·····        │
├───────────────────────────┴────────────────────────────────────────┤
│  Downscale Thresholds                                              │
│  backup-box  BX31 (10 TB)  7.2 TB used  →  BX21 (5 TB)           │
│  ● 2.2 TB needs to move · TrueNAS has 9.8 TB free  ✅ Possible    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) or [Podman](https://podman.io/) with compose support
- SSH/SFTP credentials for your Hetzner Storagebox
- An API key for your TrueNAS instance

### 1 — Clone & configure

```bash
git clone <this-repo> storage-analysis
cd storage-analysis

cp .env.example .env
$EDITOR .env          # fill in your credentials (see Configuration below)
```

### 2 — Build & run

```bash
docker compose up --build -d
```

### 3 — Open the dashboard

```
http://localhost:8000
```

Data is collected automatically on startup and then every hour. To trigger an
immediate collection, click **▶ Collect now** in the top-right corner or call:

```bash
curl -X POST http://localhost:8000/api/collect
```

---

## ⚙️ Configuration

All settings are controlled via environment variables, most easily set in a `.env` file
next to `docker-compose.yml`.

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `HETZNER_STORAGEBOX_HOST` | ✅ | — | SFTP hostname, e.g. `uXXXXXX.your-storagebox.de` |
| `HETZNER_STORAGEBOX_USER` | ✅ | — | SFTP username, e.g. `uXXXXXX` |
| `HETZNER_STORAGEBOX_PASSWORD` | ✅ | — | SFTP password (set in the Hetzner Robot panel) |
| `HETZNER_STORAGEBOX_PORT` | | `23` | SFTP port (Hetzner uses 23, not 22) |
| `HETZNER_STORAGEBOX_PRODUCT` | | auto-detect | Override plan detection: `BX11` / `BX21` / `BX31` / `BX41` |
| `TRUENAS_BASE_URL` | ✅ | — | Base URL of your TrueNAS, e.g. `https://truenas.local` |
| `TRUENAS_API_KEY` | ✅ | — | API key from **TrueNAS → Settings → API Keys** |
| `TRUENAS_VERIFY_SSL` | | `true` | Set to `false` if you use a self-signed certificate |
| `DB_PATH` | | `/data/storage.db` | Path inside the container where SQLite is stored |
| `COLLECTION_INTERVAL_HOURS` | | `1` | How often (in hours) to collect new snapshots |
| `WEB_PORT` | | `8000` | Port the web server listens on |

### Getting your Hetzner credentials

1. Log in to [Hetzner Robot](https://robot.your-server.de)
2. Go to **Storage Boxes** → select your box
3. Under **Settings** — set or reset the password
4. The hostname is shown as `uXXXXXX.your-storagebox.de`, username as `uXXXXXX`

### Getting your TrueNAS API key

**TrueNAS CORE / SCALE:**  
`Settings` → `API Keys` → `Add` → copy the generated key

---

## 🧠 How the Downscale Advisor works

The advisor checks whether you can move your Hetzner Storagebox to the next smaller plan:

```
BX41 (20 TB)  →  BX31 (10 TB)  →  BX21 (5 TB)  →  BX11 (1 TB)
```

For each storagebox it calculates:

| Field | Formula |
|---|---|
| `data_to_move_bytes` | `max(0, hetzner_used − next_plan_size)` |
| `can_downscale` | `hetzner_used ≤ next_plan_size` (data fits without moving anything) |
| `threshold_met` | `truenas_free ≥ data_to_move_bytes` (TrueNAS can absorb the overflow) |

The dashboard shows the next plan boundary as a dashed line in the Hetzner trend chart, so you can visually see how close you are.

**Status badges:**

| Badge | Meaning |
|---|---|
| 🟢 **Downscale possible** | Data already fits in the smaller plan |
| 🟠 **TrueNAS has space** | Data doesn't fit yet, but TrueNAS could absorb the excess |
| 🔴 **No downscale** | TrueNAS doesn't have enough free space either |
| 🟠 **Smallest plan** | Already on BX11, can't go lower |

---

## 🗂️ Architecture

```
storage-analysis/
├── src/
│   ├── clients/
│   │   ├── hetzner.py       # SSH/SFTP client (paramiko) — df -B1 / for stats
│   │   └── truenas.py       # REST client (httpx) — /api/v2.0/pool[/dataset]
│   ├── db/
│   │   ├── database.py      # SQLite schema init
│   │   └── repository.py    # insert / query helpers
│   ├── models.py            # Pydantic models (API + DB)
│   ├── scheduler.py         # APScheduler — collect_all() job
│   └── web/
│       ├── app.py           # FastAPI routes + downscale logic
│       └── templates/
│           └── index.html   # Chart.js dashboard (no build step)
├── tests/                   # 66 pytest tests
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

**Data flow:**

```
APScheduler (every N hours)
        │
        ├─► HetznerClient.get_storageboxes()
        │        SSH → df -B1 / → quota, used bytes → HetznerSnapshot → SQLite
        │
        └─► TrueNASClient.get_pools()
                 HTTPS → /api/v2.0/pool → pool list
                       → /api/v2.0/pool/dataset → size, allocated, free
                       → TrueNASSnapshot → SQLite

Browser → GET /api/combined  → latest snapshots + downscale thresholds
        → GET /api/hetzner/history?days=30  → chart data
        → GET /api/truenas/history?days=30  → chart data
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Dashboard HTML |
| `GET` | `/api/combined` | Latest stats for all systems + downscale thresholds |
| `GET` | `/api/hetzner/history` | Hetzner usage history (`?storagebox_id=N&days=30`) |
| `GET` | `/api/hetzner/ids` | List of known storagebox IDs |
| `GET` | `/api/truenas/history` | TrueNAS usage history (`?pool=tank&days=30`) |
| `GET` | `/api/truenas/pools` | List of known pool names |
| `POST` | `/api/collect` | Trigger an immediate data collection |

### Example: combined response

```json
{
  "total_quota_bytes": 20000000000000,
  "total_used_bytes": 10200000000000,
  "total_free_bytes": 9800000000000,
  "hetzner_storageboxes": [
    { "id": 0, "name": "uXXXXXX.your-storagebox.de", "product": "BX31",
      "disk_quota": 10000000000000, "disk_usage": 7200000000000 }
  ],
  "truenas_pools": [
    { "name": "tank", "status": "ONLINE",
      "size": 10000000000000, "allocated": 3000000000000, "free": 7000000000000 }
  ],
  "downscale_thresholds": [
    {
      "storagebox_id": 0,
      "current_product": "BX31",
      "next_smaller_product": "BX21",
      "next_smaller_quota_bytes": 5000000000000,
      "data_to_move_bytes": 2200000000000,
      "can_downscale": false,
      "threshold_met": true
    }
  ]
}
```

---

## 🧪 Development

### Run the test suite

```bash
# Inside Docker (recommended — matches production environment)
docker compose run --rm storage-analysis pytest tests/ -v

# Locally (requires Python 3.12 + dev dependencies)
pip install -e ".[dev]"
pytest tests/ -v
```

### Run locally without Docker

```bash
pip install -e ".[dev]"

export HETZNER_STORAGEBOX_HOST=uXXXXXX.your-storagebox.de
export HETZNER_STORAGEBOX_USER=uXXXXXX
export HETZNER_STORAGEBOX_PASSWORD=your-password
export TRUENAS_BASE_URL=https://truenas.local
export TRUENAS_API_KEY=your-api-key
export TRUENAS_VERIFY_SSL=false
export DB_PATH=/tmp/storage.db

python -m src.web.app
```

### Project conventions

- **No comments** unless the *why* is non-obvious
- **No mocking databases** — repository tests hit real (in-memory) SQLite
- Async tests use `pytest-asyncio` in `auto` mode
- TrueNAS client uses `respx` to mock httpx; Hetzner client mocks `paramiko.SSHClient`

---

## 🐳 Docker details

The image is built from `python:3.12-slim` and installs the package with all dev
dependencies so the test suite can run inside the container.

```bash
# Build
docker compose build

# Start in background
docker compose up -d

# Tail logs
docker compose logs -f

# Run tests
docker compose run --rm storage-analysis pytest tests/ -v

# Stop
docker compose down
```

The SQLite database is persisted in `./data/storage.db` on your host via the
`./data:/data` volume mount.

---

## 🔒 Security notes

- Credentials are passed via environment variables / `.env` file — never commit `.env` to version control
- The TrueNAS API key is transmitted over HTTPS; set `TRUENAS_VERIFY_SSL=false` only on trusted internal networks
- The dashboard has no authentication — bind to `127.0.0.1` or protect with a reverse proxy if exposed externally
- The Hetzner SFTP connection uses password auth on port 23 (Hetzner's standard for storageboxes)

---

<p align="center">
  Built with ♥ using
  <a href="https://fastapi.tiangolo.com">FastAPI</a> ·
  <a href="https://www.paramiko.org">Paramiko</a> ·
  <a href="https://www.python-httpx.org">httpx</a> ·
  <a href="https://apscheduler.readthedocs.io">APScheduler</a> ·
  <a href="https://www.chartjs.org">Chart.js</a>
</p>
