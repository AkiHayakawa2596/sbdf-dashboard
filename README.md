# SBDF Multi-Data Explorer

A LAN-friendly web dashboard for **multiple Spotfire SBDF files**.

It can:

- auto-discover `*.sbdf` files in a local Apache/server folder;
- monitor each SBDF independently;
- support explicitly configured local files or HTTP/HTTPS SBDF URLs;
- convert changed SBDF files to **Parquet + CSV**;
- query Parquet with **DuckDB** instead of keeping every dataset in RAM;
- switch datasets from one web dashboard;
- visualize dynamic columns with bar/line charts;
- filter, search and paginate data server-side;
- download a CSV for each dataset;
- create **APPEND** datasets from multiple compatible SBDF files;
- create **JOIN** datasets using common key columns;
- keep the last successfully converted data if a later refresh fails.

## Architecture

```text
Apache / server folder
├─ production_a.sbdf
├─ production_b.sbdf
├─ defects.sbdf
└─ lots.sbdf
        │
        ▼
Python SBDF service
        │
        ├─ detects only changed files
        ├─ Spotfire SBDF -> pandas
        ├─ writes Parquet
        └─ writes CSV
        │
        ▼
DuckDB query layer
        │
        ├─ individual datasets
        ├─ append views
        └─ join views
        │
        ▼
Browser dashboard
```

The browser never needs to understand the binary SBDF format.

---

# 1. Offline Windows deployment (recommended for managed PCs)

For environments where unsigned custom EXEs or BAT launchers are restricted, use the **offline wheelhouse** deployment. The target PC runs the readable Python source with an organization-approved **Python 3.12 x64** installation. All Python dependencies are supplied as local `.whl` files, so pip does not need internet access.

The GitHub Actions workflow is:

```text
.github/workflows/build-windows-offline-wheelhouse.yml
```

From GitHub, open **Actions → Build Windows Offline Wheelhouse → Run workflow**. The Windows x64 runner will:

```text
requirements.txt
      ↓
pip download --only-binary=:all:
      ↓
wheelhouse/*.whl
      ↓
clean Python 3.12 venv
      ↓
pip install --no-index --find-links=wheelhouse
      ↓
import test
      ↓
requirements-lock.txt
      ↓
second clean locked offline install
      ↓
server.py /health smoke test
      ↓
SHA256SUMS.txt
      ↓
SBDF-Dashboard-Offline-Windows-x64.zip
```

The deployment ZIP intentionally contains **no custom `SBDFDashboard.exe` and no BAT launcher**.

On the target Windows PC, after Python 3.12 x64 is installed/approved, run these commands from Command Prompt:

```cmd
cd /d C:\SBDF-Dashboard
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --no-index --find-links=wheelhouse -r requirements-lock.txt
.venv\Scripts\python.exe server.py
```

Then open:

```text
http://localhost:8080
```

See `OFFLINE-INSTALL-WINDOWS.md` for the full target-PC procedure and `TERMUX-GITHUB-BUILD.md` for the Android/Termux → GitHub workflow.

A version tag such as:

```bash
git tag v1.1.0
git push origin v1.1.0
```

also triggers the offline Windows build and attaches `SBDF-Dashboard-Offline-Windows-x64.zip` to the GitHub Release.

---

# 2. Test from Android/mobile

Run the Python server on the PC/server.

Find its LAN IPv4 address:

```bat
ipconfig
```

Example:

```text
192.168.1.123
```

Connect the phone to the same LAN/Wi-Fi and open:

```text
http://192.168.1.123:8080
```

Health test:

```text
http://192.168.1.123:8080/health
```

Allow Python through Windows Defender Firewall on **Private networks** if the phone cannot connect.

---

# 3. Recommended setup: auto-discover an Apache folder

If this Python app runs on the same Windows machine that contains the Apache SBDF folder, edit `config.json`:

```json
"discovery": {
  "enabled": true,
  "folder": "C:/Apache24/htdocs/sbdf",
  "pattern": "*.sbdf",
  "recursive": false,
  "rescan_seconds": 30,
  "poll_seconds": 60
}
```

Example folder:

```text
C:/Apache24/htdocs/sbdf/
├─ production.sbdf
├─ defects.sbdf
├─ yield.sbdf
└─ cycle_time.sbdf
```

The dashboard automatically creates:

```text
Production
Defects
Yield
Cycle Time
```

No source-code change is required when another SBDF is added to that folder.

The folder is re-scanned every `rescan_seconds`.

Each discovered SBDF is checked independently every `poll_seconds`.

---

# 4. Explicitly configure multiple SBDF files

This is useful for files stored in different folders or served by Apache URLs.

Example:

```json
"datasets": [
  {
    "id": "production",
    "name": "Production",
    "source": "http://192.168.1.50/data/production.sbdf",
    "poll_seconds": 30,
    "enabled": true
  },
  {
    "id": "defects",
    "name": "Defects",
    "source": "http://192.168.1.50/data/defects.sbdf",
    "poll_seconds": 60,
    "enabled": true
  }
]
```

You can mix URL and local path sources:

```json
{
  "id": "yield",
  "name": "Yield",
  "source": "C:/Apache24/htdocs/data/yield.sbdf",
  "poll_seconds": 120,
  "enabled": true
}
```

Local paths are preferable when the Python service and Apache files are on the same server.

---

# 5. APPEND multiple SBDF datasets

Use APPEND when the files have the same or compatible columns.

Example physical files:

```text
production-jan.sbdf
production-feb.sbdf
production-mar.sbdf
```

Give them IDs such as:

```text
production-jan
production-feb
production-mar
```

Then configure either explicit IDs:

```json
"members": ["production-jan", "production-feb", "production-mar"]
```

or a wildcard that automatically includes newly discovered matching datasets:

```json
"derived": {
  "append": [
    {
      "id": "production-history",
      "name": "Production History",
      "members": ["production-*"],
      "enabled": true
    }
  ]
}
```

The dashboard then exposes one virtual dataset:

```text
Production History
```

Internally DuckDB uses `UNION ALL BY NAME`, so compatible columns are combined by column name.

The source Parquet files stay separate.

---

# 6. JOIN multiple datasets

Use JOIN when datasets share a common key.

Example:

`lots.sbdf`

```text
LotNumber
Device
Machine
Output
```

`defects.sbdf`

```text
LotNumber
DefectCode
DefectQty
```

Configure:

```json
"derived": {
  "join": [
    {
      "id": "lot-quality",
      "name": "Lot Quality",
      "left": "lots",
      "right": "defects",
      "on": ["LotNumber"],
      "how": "left",
      "enabled": true
    }
  ]
}
```

The resulting virtual dataset contains the left-side columns plus the non-key right-side columns.

Supported join modes:

```text
left
right
inner
full
```

Multiple keys are supported:

```json
"on": ["LotNumber", "Device"]
```

---

# 7. Why Parquet + DuckDB is used

The old single-file prototype stored the full dataset in a pandas DataFrame in RAM.

That does not scale well when several large SBDF files are open.

This version does:

```text
SBDF
  ↓
pandas only during conversion
  ↓
Parquet on disk
  ↓
DuckDB queries
  ↓
small chart/table result
  ↓
browser
```

For example, the browser requesting 25 table rows does not receive the entire source dataset.

Charts are grouped on the server before values are sent to the phone/browser.

---

# 8. Generated storage

Each converted physical dataset gets separate files:

```text
data/
├─ parquet/
│  ├─ production.parquet
│  ├─ defects.parquet
│  └─ yield.parquet
└─ csv/
   ├─ production.csv
   ├─ defects.csv
   └─ yield.csv
```

Derived APPEND/JOIN datasets are primarily virtual DuckDB queries. Their CSV is generated when you click **Download CSV**.

---

# 9. Change detection

### Local SBDF

The service compares:

```text
file modification timestamp + file size
```

If unchanged, no SBDF conversion occurs.

### HTTP/HTTPS SBDF

The service reuses Apache response headers when available:

```text
ETag
Last-Modified
```

and can receive:

```text
304 Not Modified
```

instead of downloading the file again.

Every physical dataset has its own fingerprint and refresh timer.

---

# 10. Dashboard features

The UI includes:

- dataset dropdown;
- dataset registry/status list;
- row/column/version/refresh cards;
- X/category selection;
- numeric Y/metric selection;
- count/sum/average/min/max;
- bar chart;
- line chart;
- value or label sorting;
- top 10/20/50/100 groups;
- two generic `contains` filters;
- searchable table;
- server-side pagination;
- CSV download;
- current-dataset refresh;
- refresh-all;
- automatic 15-second browser status check;
- responsive/mobile layout.

---

# 11. API

Global:

```text
GET  /api/status
GET  /api/datasets
POST /api/refresh-all
GET  /health
```

Per dataset:

```text
GET  /api/datasets/<id>/status
GET  /api/datasets/<id>/schema
GET  /api/datasets/<id>/rows
GET  /api/datasets/<id>/chart
POST /api/datasets/<id>/refresh
GET  /download/<id>.csv
```

Example:

```text
/api/datasets/production/chart?x=Machine&y=Output&agg=sum
```

---

# 12. Important limitation

This application detects changes to the **SBDF files themselves**.

It does not cause Spotfire or SQL Server to refresh an SBDF.

Your upstream process must still produce/update the source SBDF:

```text
SQL / source system
       ↓
existing Spotfire / scheduled export process
       ↓
updated .sbdf
       ↓
this dashboard detects the changed file
```

If the SBDF on Apache is a static snapshot and Spotfire only refreshes data internally when an analysis opens, the web dashboard will only see the snapshot stored in that SBDF.

---

# Project structure

```text
sbdf-live-dashboard/
├─ .github/
│  └─ workflows/
│     └─ build-windows-offline-wheelhouse.yml
├─ config.json
├─ requirements.txt
├─ server.py
├─ start.sh
├─ package_offline.ps1
├─ OFFLINE-INSTALL-WINDOWS.md
├─ TERMUX-GITHUB-BUILD.md
├─ README.md
├─ data/
│  ├─ parquet/
│  └─ csv/
└─ web/
   ├─ index.html
   ├─ styles.css
   └─ app.js
```

## Main Python dependencies

```text
Flask
pandas
requests
duckdb
spotfire
```

---

## Offline Windows deployment (recommended for managed enterprise PCs)

The repository now includes a GitHub Actions workflow named **Build Windows Offline Wheelhouse**. It creates `SBDF-Dashboard-Offline-Windows-x64.zip`, containing the source dashboard, a Windows x64/Python 3.12 wheelhouse, an exact dependency lock file, and SHA-256 checksums. The workflow verifies installation with `--no-index` in clean virtual environments and smoke-tests `/health` before publishing the artifact.

See `OFFLINE-INSTALL-WINDOWS.md` and `TERMUX-GITHUB-BUILD.md`.
