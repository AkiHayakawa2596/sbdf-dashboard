from __future__ import annotations

import fnmatch
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb
import pandas as pd
import requests
from flask import Flask, jsonify, request, send_file, send_from_directory

try:
    from spotfire import sbdf
    SPOTFIRE_IMPORT_ERROR = None
except Exception as exc:  # Demo mode still works without the Spotfire package.
    sbdf = None
    SPOTFIRE_IMPORT_ERROR = str(exc)

# Portable-runtime paths:
# - APP_DIR is the writable folder beside SBDFDashboard.exe when frozen.
# - RESOURCE_DIR is where PyInstaller keeps bundled read-only assets.
# During normal Python development both point to the source folder.
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)).resolve()
else:
    APP_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = APP_DIR

BASE_DIR = APP_DIR  # Keep relative user paths/config anchored beside the executable.
_external_config = APP_DIR / "config.json"
_bundled_config = RESOURCE_DIR / "config.json"
CONFIG_PATH = _external_config if _external_config.exists() else _bundled_config
_external_web = APP_DIR / "web"
_bundled_web = RESOURCE_DIR / "web"
WEB_DIR = _external_web if _external_web.exists() else _bundled_web
STOP_EVENT = threading.Event()
REGISTRY_LOCK = threading.RLock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_id(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return value or "dataset"


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sql_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        config = json.load(fh)
    config["request_timeout_seconds"] = max(10, int(config.get("request_timeout_seconds", 120)))
    config["max_table_search_rows"] = max(1000, int(config.get("max_table_search_rows", 200000)))
    config["max_chart_groups"] = min(500, max(5, int(config.get("max_chart_groups", 60))))
    config["scheduler_tick_seconds"] = max(1, int(config.get("scheduler_tick_seconds", 3)))
    return config


CONFIG = load_config()
STORAGE_DIR = (BASE_DIR / CONFIG.get("storage_dir", "data")).resolve()
PARQUET_DIR = STORAGE_DIR / "parquet"
CSV_DIR = STORAGE_DIR / "csv"
PARQUET_DIR.mkdir(parents=True, exist_ok=True)
CSV_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SourceFingerprint:
    etag: str | None = None
    last_modified: str | None = None
    local_signature: str | None = None


@dataclass
class DatasetState:
    id: str
    name: str
    kind: str = "physical"  # physical, discovered, demo, append, join
    source: str | None = None
    poll_seconds: int = 60
    enabled: bool = True
    discovered: bool = False
    definition: dict[str, Any] = field(default_factory=dict)
    status: str = "starting"
    mode: str = "live"
    message: str = "Waiting for first refresh"
    last_refresh_utc: str | None = None
    last_attempt_utc: str | None = None
    last_attempt_monotonic: float = 0.0
    version: int = 0
    rows: int = 0
    columns: int = 0
    source_fingerprint: SourceFingerprint = field(default_factory=SourceFingerprint)
    dependency_signature: str = ""
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    refresh_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def parquet_path(self) -> Path:
        return PARQUET_DIR / f"{self.id}.parquet"

    @property
    def csv_path(self) -> Path:
        return CSV_DIR / f"{self.id}.csv"

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "mode": self.mode,
            "status": self.status,
            "message": self.message,
            "source": source_display(self.source) if self.source else derived_source_display(self),
            "pollSeconds": self.poll_seconds if self.kind in {"physical", "discovered"} else None,
            "rows": self.rows,
            "columns": self.columns,
            "version": self.version,
            "lastRefreshUtc": self.last_refresh_utc,
            "lastAttemptUtc": self.last_attempt_utc,
            "downloadUrl": f"/download/{self.id}.csv",
            "refreshable": self.kind in {"physical", "discovered"},
        }


DATASETS: dict[str, DatasetState] = {}
LAST_DISCOVERY_SCAN = 0.0


def source_display(source: str | None) -> str:
    if not source:
        return "—"
    if source.lower().startswith(("http://", "https://")):
        parsed = urlparse(source)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return str(Path(source).expanduser())


def derived_source_display(ds: DatasetState) -> str:
    if ds.kind == "append":
        return "Append: " + ", ".join(ds.definition.get("members", []))
    if ds.kind == "join":
        return f"Join: {ds.definition.get('left')} + {ds.definition.get('right')}"
    if ds.kind == "demo":
        return "Built-in demo dataset"
    return "Derived dataset"


def register_dataset(ds: DatasetState, replace: bool = False) -> DatasetState:
    with REGISTRY_LOCK:
        if ds.id in DATASETS and not replace:
            return DATASETS[ds.id]
        DATASETS[ds.id] = ds
        return ds


def configured_source_is_placeholder(source: str) -> bool:
    upper = source.upper()
    return "YOUR-APACHE-SERVER" in upper or "REPLACE_WITH" in upper or "EXAMPLE.COM" in upper


def load_configured_datasets() -> None:
    for item in CONFIG.get("datasets", []):
        if not item.get("enabled", True):
            continue
        source = str(item.get("source", "")).strip()
        if not source or configured_source_is_placeholder(source):
            continue
        dataset_id = safe_id(str(item.get("id") or Path(urlparse(source).path).stem or "dataset"))
        register_dataset(
            DatasetState(
                id=dataset_id,
                name=str(item.get("name") or dataset_id.replace("-", " ").title()),
                source=source,
                poll_seconds=max(10, int(item.get("poll_seconds", CONFIG.get("default_poll_seconds", 60)))),
                kind="physical",
                mode="live",
            )
        )


def load_derived_definitions() -> None:
    derived = CONFIG.get("derived", {})
    for item in derived.get("append", []):
        if not item.get("enabled", True):
            continue
        dataset_id = safe_id(str(item.get("id", "append")))
        register_dataset(
            DatasetState(
                id=dataset_id,
                name=str(item.get("name") or dataset_id.replace("-", " ").title()),
                kind="append",
                mode="derived",
                definition={"members": [safe_id(str(x)) for x in item.get("members", [])]},
                status="waiting",
                message="Waiting for member datasets",
            ),
            replace=True,
        )
    for item in derived.get("join", []):
        if not item.get("enabled", True):
            continue
        dataset_id = safe_id(str(item.get("id", "join")))
        on = item.get("on", [])
        if isinstance(on, str):
            on = [on]
        register_dataset(
            DatasetState(
                id=dataset_id,
                name=str(item.get("name") or dataset_id.replace("-", " ").title()),
                kind="join",
                mode="derived",
                definition={
                    "left": safe_id(str(item.get("left", ""))),
                    "right": safe_id(str(item.get("right", ""))),
                    "on": [str(x) for x in on],
                    "how": str(item.get("how", "left")).lower(),
                },
                status="waiting",
                message="Waiting for joined datasets",
            ),
            replace=True,
        )


def discovery_folder() -> Path | None:
    discovery = CONFIG.get("discovery", {})
    if not discovery.get("enabled", True):
        return None
    folder_value = str(discovery.get("folder", "")).strip()
    if not folder_value or configured_source_is_placeholder(folder_value):
        return None
    folder = Path(folder_value).expanduser()
    if not folder.is_absolute():
        folder = (BASE_DIR / folder).resolve()
    return folder


def scan_discovery(force: bool = False) -> None:
    global LAST_DISCOVERY_SCAN
    discovery = CONFIG.get("discovery", {})
    interval = max(5, int(discovery.get("rescan_seconds", 30)))
    now = time.monotonic()
    if not force and now - LAST_DISCOVERY_SCAN < interval:
        return
    LAST_DISCOVERY_SCAN = now

    folder = discovery_folder()
    if folder is None or not folder.exists() or not folder.is_dir():
        return

    pattern = str(discovery.get("pattern", "*.sbdf"))
    recursive = bool(discovery.get("recursive", False))
    paths = folder.rglob("*") if recursive else folder.glob("*")
    found_ids: set[str] = set()
    for path in paths:
        if not path.is_file() or not fnmatch.fnmatch(path.name.lower(), pattern.lower()):
            continue
        base_id = safe_id(path.stem)
        dataset_id = base_id
        counter = 2
        with REGISTRY_LOCK:
            while dataset_id in DATASETS and DATASETS[dataset_id].source not in {None, str(path.resolve())}:
                dataset_id = f"{base_id}-{counter}"
                counter += 1
            found_ids.add(dataset_id)
            existing = DATASETS.get(dataset_id)
            if existing:
                existing.source = str(path.resolve())
                existing.enabled = True
                if existing.status == "missing":
                    existing.status = "starting"
                    existing.message = "Source rediscovered"
                continue
            DATASETS[dataset_id] = DatasetState(
                id=dataset_id,
                name=path.stem.replace("_", " ").replace("-", " ").title(),
                kind="discovered",
                source=str(path.resolve()),
                poll_seconds=max(10, int(discovery.get("poll_seconds", CONFIG.get("default_poll_seconds", 60)))),
                discovered=True,
                mode="live",
            )

    with REGISTRY_LOCK:
        for ds in DATASETS.values():
            if ds.discovered and ds.id not in found_ids:
                ds.status = "missing"
                ds.message = "Discovered SBDF file is no longer present; cached Parquet is retained"


def write_dataframe_storage(df: pd.DataFrame, ds: DatasetState) -> None:
    ds.parquet_path.parent.mkdir(parents=True, exist_ok=True)
    ds.csv_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_tmp = ds.parquet_path.with_suffix(".parquet.tmp")
    csv_tmp = ds.csv_path.with_suffix(".csv.tmp")

    con = duckdb.connect()
    try:
        con.register("incoming_df", df)
        con.execute(f"COPY incoming_df TO {sql_string(parquet_tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        con.close()
    df.to_csv(csv_tmp, index=False, encoding="utf-8-sig")
    os.replace(parquet_tmp, ds.parquet_path)
    os.replace(csv_tmp, ds.csv_path)


def read_sbdf_to_dataframe(path: Path) -> pd.DataFrame:
    if sbdf is None:
        detail = f" ({SPOTFIRE_IMPORT_ERROR})" if SPOTFIRE_IMPORT_ERROR else ""
        raise RuntimeError("The 'spotfire' Python package is not available" + detail)
    frame = sbdf.import_data(str(path))
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(frame)
    return frame


def convert_local_file(ds: DatasetState, force: bool) -> tuple[pd.DataFrame | None, str]:
    assert ds.source
    path = Path(ds.source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"SBDF source does not exist: {path}")
    stat = path.stat()
    signature = f"{stat.st_mtime_ns}:{stat.st_size}"
    if not force and signature == ds.source_fingerprint.local_signature:
        return None, "Source unchanged"
    df = read_sbdf_to_dataframe(path)
    ds.source_fingerprint.local_signature = signature
    return df, f"Converted {path.name}"


def convert_remote_file(ds: DatasetState, force: bool) -> tuple[pd.DataFrame | None, str]:
    assert ds.source
    headers = dict(CONFIG.get("request_headers", {}))
    fp = ds.source_fingerprint
    if not force:
        if fp.etag:
            headers["If-None-Match"] = fp.etag
        if fp.last_modified:
            headers["If-Modified-Since"] = fp.last_modified

    response = requests.get(
        ds.source,
        headers=headers,
        timeout=CONFIG["request_timeout_seconds"],
        verify=bool(CONFIG.get("verify_tls", True)),
        stream=True,
    )
    if response.status_code == 304:
        return None, "Source unchanged"
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(prefix=f"{ds.id}_", suffix=".sbdf", delete=False) as tmp:
        temp_name = tmp.name
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                tmp.write(chunk)
    try:
        df = read_sbdf_to_dataframe(Path(temp_name))
    finally:
        try:
            os.remove(temp_name)
        except OSError:
            pass

    fp.etag = response.headers.get("ETag")
    fp.last_modified = response.headers.get("Last-Modified")
    filename = Path(urlparse(ds.source).path).name or "remote.sbdf"
    return df, f"Downloaded and converted {filename}"


def refresh_physical_dataset(ds: DatasetState, force: bool = False) -> dict[str, Any]:
    if ds.kind not in {"physical", "discovered"}:
        return {"changed": False, "message": "Derived/demo datasets do not refresh from SBDF directly"}
    if not ds.refresh_lock.acquire(blocking=False):
        return {"changed": False, "message": "Refresh already running"}
    try:
        with ds.lock:
            ds.last_attempt_utc = utc_now_iso()
            ds.last_attempt_monotonic = time.monotonic()
        if not ds.source:
            raise RuntimeError("Dataset has no source")
        if ds.source.lower().startswith(("http://", "https://")):
            df, message = convert_remote_file(ds, force)
        else:
            df, message = convert_local_file(ds, force)
        if df is None:
            with ds.lock:
                if ds.parquet_path.exists() and ds.status != "missing":
                    ds.status = "ok"
                    ds.message = message
            return {"changed": False, "message": message}

        write_dataframe_storage(df, ds)
        with ds.lock:
            ds.rows = int(len(df))
            ds.columns = int(len(df.columns))
            ds.status = "ok"
            ds.mode = "live"
            ds.message = message
            ds.last_refresh_utc = utc_now_iso()
            ds.version += 1
        refresh_virtual_metadata()
        return {"changed": True, "message": message, "rows": ds.rows, "columns": ds.columns}
    except Exception as exc:
        with ds.lock:
            ds.status = "error"
            ds.message = str(exc)
        return {"changed": False, "error": str(exc)}
    finally:
        ds.refresh_lock.release()


def resolved_append_members(ds: DatasetState) -> list[str]:
    requested = [str(x) for x in ds.definition.get("members", [])]
    with REGISTRY_LOCK:
        ids = list(DATASETS.keys())
    resolved: list[str] = []
    for item in requested:
        if any(ch in item for ch in "*?["):
            matches = sorted(x for x in ids if x != ds.id and fnmatch.fnmatch(x, item))
            for match in matches:
                if match not in resolved:
                    resolved.append(match)
        elif item != ds.id and item not in resolved:
            resolved.append(item)
    return resolved


def dataset_dependencies(dataset_id: str, visited: set[str] | None = None) -> list[str]:
    visited = visited or set()
    if dataset_id in visited:
        raise RuntimeError(f"Circular derived dataset definition involving '{dataset_id}'")
    visited.add(dataset_id)
    ds = DATASETS.get(dataset_id)
    if not ds:
        return [dataset_id]
    if ds.kind == "append":
        deps: list[str] = []
        for member in resolved_append_members(ds):
            deps.extend(dataset_dependencies(member, visited.copy()))
        return deps
    if ds.kind == "join":
        return dataset_dependencies(ds.definition.get("left", ""), visited.copy()) + dataset_dependencies(ds.definition.get("right", ""), visited.copy())
    return [dataset_id]


def dataset_source_sql(dataset_id: str, visited: set[str] | None = None) -> str:
    visited = visited or set()
    if dataset_id in visited:
        raise RuntimeError(f"Circular derived dataset definition involving '{dataset_id}'")
    visited.add(dataset_id)
    ds = DATASETS.get(dataset_id)
    if not ds:
        raise KeyError(f"Unknown dataset '{dataset_id}'")

    if ds.kind in {"physical", "discovered", "demo"}:
        if not ds.parquet_path.exists():
            raise RuntimeError(f"Dataset '{ds.name}' has no converted Parquet yet")
        return f"SELECT * FROM read_parquet({sql_string(ds.parquet_path)})"

    if ds.kind == "append":
        members = resolved_append_members(ds)
        if not members:
            raise RuntimeError(f"Append dataset '{ds.name}' has no resolved members")
        parts = [f"SELECT * FROM ({dataset_source_sql(member, visited.copy())})" for member in members]
        return " UNION ALL BY NAME ".join(parts)

    if ds.kind == "join":
        left_id = ds.definition.get("left")
        right_id = ds.definition.get("right")
        keys = ds.definition.get("on", [])
        how = ds.definition.get("how", "left")
        allowed_how = {"left": "LEFT", "right": "RIGHT", "inner": "INNER", "full": "FULL"}
        join_word = allowed_how.get(how, "LEFT")
        if not left_id or not right_id or not keys:
            raise RuntimeError(f"Join dataset '{ds.name}' needs left, right and on keys")
        left_sql = dataset_source_sql(left_id, visited.copy())
        right_sql = dataset_source_sql(right_id, visited.copy())
        conditions = " AND ".join([f"l.{quote_ident(key)} = r.{quote_ident(key)}" for key in keys])
        # Keep all left columns; add right non-key columns with DuckDB's duplicate-name handling.
        right_exclude = ", ".join(quote_ident(k) for k in keys)
        right_select = "r.*" if not right_exclude else f"r.* EXCLUDE ({right_exclude})"
        return f"SELECT l.*, {right_select} FROM ({left_sql}) l {join_word} JOIN ({right_sql}) r ON {conditions}"

    raise RuntimeError(f"Unsupported dataset kind: {ds.kind}")


def dependency_signature(ds: DatasetState) -> str:
    deps = dataset_dependencies(ds.id)
    items = []
    for dep_id in deps:
        dep = DATASETS.get(dep_id)
        if not dep:
            items.append(f"{dep_id}:missing")
        else:
            items.append(f"{dep_id}:{dep.version}:{dep.status}")
    return "|".join(items)


def refresh_virtual_metadata() -> None:
    with REGISTRY_LOCK:
        virtuals = [ds for ds in DATASETS.values() if ds.kind in {"append", "join"}]
    for ds in virtuals:
        sig = dependency_signature(ds)
        if sig == ds.dependency_signature and ds.status == "ok":
            continue
        try:
            source_sql = dataset_source_sql(ds.id)
            con = duckdb.connect()
            try:
                rows = con.execute(f"SELECT COUNT(*) FROM ({source_sql}) q").fetchone()[0]
                cols = len(con.execute(f"DESCRIBE SELECT * FROM ({source_sql}) q").fetchall())
            finally:
                con.close()
            with ds.lock:
                ds.rows = int(rows)
                ds.columns = int(cols)
                ds.status = "ok"
                ds.mode = "derived"
                ds.message = "Derived dataset ready"
                ds.last_refresh_utc = utc_now_iso()
                ds.dependency_signature = sig
                ds.version += 1
        except Exception as exc:
            with ds.lock:
                ds.status = "waiting"
                ds.message = str(exc)
                ds.dependency_signature = sig


def dataframe_to_demo_storage(dataset_id: str, name: str, df: pd.DataFrame) -> DatasetState:
    ds = DatasetState(id=dataset_id, name=name, kind="demo", mode="demo", status="ok", message="Built-in demo data")
    write_dataframe_storage(df, ds)
    ds.rows = len(df)
    ds.columns = len(df.columns)
    ds.last_refresh_utc = utc_now_iso()
    ds.version = 1
    register_dataset(ds, replace=True)
    return ds


def initialize_demo_if_needed() -> None:
    with REGISTRY_LOCK:
        has_real = any(ds.kind in {"physical", "discovered"} for ds in DATASETS.values())
    if has_real:
        return

    a = pd.DataFrame([
        {"Date": "2026-09-20", "Shift": "A", "Area": "EOL", "LotNumber": "LOT-1001", "Machine": "EOL-01", "Device": "QFN-A", "Output": 1240, "Rejects": 18, "YieldPct": 98.55, "CycleTimeMin": 42.1},
        {"Date": "2026-09-21", "Shift": "A", "Area": "EOL", "LotNumber": "LOT-1002", "Machine": "EOL-02", "Device": "QFN-A", "Output": 1315, "Rejects": 14, "YieldPct": 98.94, "CycleTimeMin": 40.8},
        {"Date": "2026-09-22", "Shift": "A", "Area": "TEST", "LotNumber": "LOT-1003", "Machine": "TEST-03", "Device": "QFN-B", "Output": 1188, "Rejects": 21, "YieldPct": 98.23, "CycleTimeMin": 45.3},
        {"Date": "2026-09-23", "Shift": "A", "Area": "EOL", "LotNumber": "LOT-1004", "Machine": "EOL-01", "Device": "QFN-B", "Output": 1462, "Rejects": 12, "YieldPct": 99.18, "CycleTimeMin": 39.9},
    ])
    b = pd.DataFrame([
        {"Date": "2026-09-20", "Shift": "B", "Area": "EOL", "LotNumber": "LOT-2001", "Machine": "EOL-02", "Device": "QFN-A", "Output": 1288, "Rejects": 17, "YieldPct": 98.68, "CycleTimeMin": 43.2},
        {"Date": "2026-09-21", "Shift": "B", "Area": "TEST", "LotNumber": "LOT-2002", "Machine": "TEST-02", "Device": "QFN-C", "Output": 1521, "Rejects": 9, "YieldPct": 99.41, "CycleTimeMin": 38.7},
        {"Date": "2026-09-22", "Shift": "B", "Area": "EOL", "LotNumber": "LOT-2003", "Machine": "EOL-01", "Device": "QFN-C", "Output": 1277, "Rejects": 16, "YieldPct": 98.75, "CycleTimeMin": 44.0},
        {"Date": "2026-09-23", "Shift": "B", "Area": "TEST", "LotNumber": "LOT-2004", "Machine": "TEST-03", "Device": "QFN-B", "Output": 1498, "Rejects": 13, "YieldPct": 99.13, "CycleTimeMin": 41.4},
    ])
    defects = pd.DataFrame([
        {"LotNumber": "LOT-1001", "DefectCode": "BURR", "DefectQty": 7},
        {"LotNumber": "LOT-1001", "DefectCode": "MARK", "DefectQty": 4},
        {"LotNumber": "LOT-1002", "DefectCode": "CRACK", "DefectQty": 5},
        {"LotNumber": "LOT-1003", "DefectCode": "MARK", "DefectQty": 9},
        {"LotNumber": "LOT-2001", "DefectCode": "BURR", "DefectQty": 6},
        {"LotNumber": "LOT-2002", "DefectCode": "CRACK", "DefectQty": 3},
        {"LotNumber": "LOT-2003", "DefectCode": "MARK", "DefectQty": 8},
        {"LotNumber": "LOT-2004", "DefectCode": "BURR", "DefectQty": 5},
    ])
    dataframe_to_demo_storage("production-a", "Production — Shift A", a)
    dataframe_to_demo_storage("production-b", "Production — Shift B", b)
    dataframe_to_demo_storage("defects", "Defects", defects)

    register_dataset(DatasetState(
        id="production-all", name="Production — All Shifts", kind="append", mode="demo-derived",
        definition={"members": ["production-a", "production-b"]}, status="waiting", message="Building append view"
    ), replace=True)
    register_dataset(DatasetState(
        id="production-quality", name="Production + Defects", kind="join", mode="demo-derived",
        definition={"left": "production-all", "right": "defects", "on": ["LotNumber"], "how": "left"},
        status="waiting", message="Building join view"
    ), replace=True)
    refresh_virtual_metadata()


def initialize() -> None:
    load_configured_datasets()
    scan_discovery(force=True)
    load_derived_definitions()
    initialize_demo_if_needed()
    refresh_virtual_metadata()


def physical_refresh_due(ds: DatasetState) -> bool:
    if ds.kind not in {"physical", "discovered"} or not ds.enabled:
        return False
    return time.monotonic() - ds.last_attempt_monotonic >= ds.poll_seconds


def scheduler_loop() -> None:
    # Staggered independent refreshes; discovery is re-scanned periodically.
    while not STOP_EVENT.is_set():
        scan_discovery()
        with REGISTRY_LOCK:
            physicals = [ds for ds in DATASETS.values() if ds.kind in {"physical", "discovered"}]
        for ds in physicals:
            if physical_refresh_due(ds):
                refresh_physical_dataset(ds)
        refresh_virtual_metadata()
        STOP_EVENT.wait(CONFIG["scheduler_tick_seconds"])


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def get_dataset_or_404(dataset_id: str) -> DatasetState | None:
    with REGISTRY_LOCK:
        return DATASETS.get(safe_id(dataset_id))


def duckdb_schema(dataset_id: str) -> list[dict[str, Any]]:
    source_sql = dataset_source_sql(dataset_id)
    con = duckdb.connect()
    try:
        rows = con.execute(f"DESCRIBE SELECT * FROM ({source_sql}) q").fetchall()
    finally:
        con.close()
    numeric_tokens = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "DECIMAL", "FLOAT", "DOUBLE", "REAL")
    datetime_tokens = ("DATE", "TIMESTAMP", "TIME")
    result = []
    for row in rows:
        name, dtype = str(row[0]), str(row[1]).upper()
        result.append({
            "name": name,
            "dtype": dtype,
            "numeric": any(token in dtype for token in numeric_tokens),
            "datetime": any(token in dtype for token in datetime_tokens),
        })
    return result


def parse_filters(schema_names: set[str]) -> list[dict[str, str]]:
    raw = request.args.get("filters", "")
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except Exception:
        return []
    filters = []
    for item in values[:5] if isinstance(values, list) else []:
        column = str(item.get("column", ""))
        value = str(item.get("value", "")).strip()
        if column in schema_names and value:
            filters.append({"column": column, "value": value})
    return filters


def where_from_filters(filters: list[dict[str, str]], params: list[Any]) -> str:
    conditions = []
    for item in filters:
        conditions.append(f"LOWER(COALESCE(CAST({quote_ident(item['column'])} AS VARCHAR), '')) LIKE ?")
        params.append(f"%{item['value'].lower()}%")
    return (" WHERE " + " AND ".join(conditions)) if conditions else ""


initialize()
app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/api/status")
def api_status():
    with REGISTRY_LOCK:
        datasets = sorted([ds.public() for ds in DATASETS.values()], key=lambda x: (x["kind"] in {"append", "join"}, x["name"].lower()))
    return jsonify({
        "appTitle": CONFIG.get("app_title", "SBDF Multi-Data Explorer"),
        "datasetCount": len(datasets),
        "datasets": datasets,
        "converterReady": sbdf is not None,
        "storage": "DuckDB + Parquet",
        "discoveryFolder": source_display(str(discovery_folder())) if discovery_folder() else "Not configured / demo mode",
    })


@app.get("/api/datasets")
def api_datasets():
    refresh_virtual_metadata()
    with REGISTRY_LOCK:
        return jsonify({"datasets": [ds.public() for ds in sorted(DATASETS.values(), key=lambda d: d.name.lower())]})


@app.get("/api/datasets/<dataset_id>/status")
def api_dataset_status(dataset_id: str):
    ds = get_dataset_or_404(dataset_id)
    if not ds:
        return jsonify({"error": "Dataset not found"}), 404
    if ds.kind in {"append", "join"}:
        refresh_virtual_metadata()
    return jsonify(ds.public())


@app.get("/api/datasets/<dataset_id>/schema")
def api_dataset_schema(dataset_id: str):
    ds = get_dataset_or_404(dataset_id)
    if not ds:
        return jsonify({"error": "Dataset not found"}), 404
    try:
        return jsonify({"columns": duckdb_schema(ds.id), "version": ds.version})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 409


@app.get("/api/datasets/<dataset_id>/rows")
def api_dataset_rows(dataset_id: str):
    ds = get_dataset_or_404(dataset_id)
    if not ds:
        return jsonify({"error": "Dataset not found"}), 404
    offset = max(0, request.args.get("offset", default=0, type=int) or 0)
    limit = min(200, max(5, request.args.get("limit", default=25, type=int) or 25))
    search = (request.args.get("search") or "").strip().lower()
    try:
        schema = duckdb_schema(ds.id)
        names = [x["name"] for x in schema]
        params: list[Any] = []
        filters = parse_filters(set(names))
        where = where_from_filters(filters, params)
        source_sql = dataset_source_sql(ds.id)
        base_sql = f"SELECT * FROM ({source_sql}) src{where}"

        search_truncated = False
        searched_rows = ds.rows
        if search and names:
            max_search = CONFIG["max_table_search_rows"]
            limited = f"SELECT * FROM ({base_sql}) base LIMIT {int(max_search)}"
            clauses = [f"LOWER(COALESCE(CAST({quote_ident(name)} AS VARCHAR), '')) LIKE ?" for name in names]
            search_params = params.copy() + [f"%{search}%"] * len(names)
            query_sql = f"SELECT * FROM ({limited}) candidate WHERE {' OR '.join(clauses)}"
            count_sql = f"SELECT COUNT(*) FROM ({query_sql}) q"
            data_sql = f"SELECT * FROM ({query_sql}) q LIMIT {limit} OFFSET {offset}"
            searched_rows = min(ds.rows, max_search)
            search_truncated = ds.rows > max_search
            final_params = search_params
        else:
            count_sql = f"SELECT COUNT(*) FROM ({base_sql}) q"
            data_sql = f"SELECT * FROM ({base_sql}) q LIMIT {limit} OFFSET {offset}"
            final_params = params

        con = duckdb.connect()
        try:
            total = int(con.execute(count_sql, final_params).fetchone()[0])
            frame = con.execute(data_sql, final_params).fetchdf()
        finally:
            con.close()
        rows = [{str(k): json_safe(v) for k, v in row.items()} for row in frame.to_dict(orient="records")]
        return jsonify({
            "columns": names, "rows": rows, "total": total, "offset": offset, "limit": limit,
            "searchedRows": int(searched_rows), "searchTruncated": search_truncated, "version": ds.version,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 409


@app.get("/api/datasets/<dataset_id>/chart")
def api_dataset_chart(dataset_id: str):
    ds = get_dataset_or_404(dataset_id)
    if not ds:
        return jsonify({"error": "Dataset not found"}), 404
    x = request.args.get("x")
    y = request.args.get("y")
    agg = (request.args.get("agg") or "count").lower()
    requested_limit = request.args.get("limit", default=20, type=int) or 20
    limit = min(CONFIG["max_chart_groups"], max(5, requested_limit))
    sort_mode = (request.args.get("sort") or "value_desc").lower()
    try:
        schema = duckdb_schema(ds.id)
        by_name = {item["name"]: item for item in schema}
        if not x or x not in by_name:
            return jsonify({"error": "Choose a valid X/category column"}), 400
        params: list[Any] = []
        filters = parse_filters(set(by_name))
        where = where_from_filters(filters, params)
        source_sql = dataset_source_sql(ds.id)
        xq = quote_ident(x)

        if agg == "count" or not y:
            value_expr = "COUNT(*)"
            metric_label = "Count"
        else:
            if y not in by_name or not by_name[y]["numeric"]:
                return jsonify({"error": "The Y metric must be numeric for this aggregation"}), 400
            operations = {"sum": "SUM", "avg": "AVG", "average": "AVG", "mean": "AVG", "min": "MIN", "max": "MAX"}
            op = operations.get(agg)
            if not op:
                return jsonify({"error": "Unsupported aggregation"}), 400
            value_expr = f"{op}({quote_ident(y)})"
            metric_label = f"{op} of {y}"

        order_sql = {
            "label_asc": "label ASC",
            "label_desc": "label DESC",
            "value_asc": "value ASC NULLS LAST",
            "value_desc": "value DESC NULLS LAST",
        }.get(sort_mode, "value DESC NULLS LAST")
        sql = f"""
            SELECT COALESCE(CAST({xq} AS VARCHAR), '(blank)') AS label,
                   {value_expr} AS value
            FROM ({source_sql}) src
            {where}
            GROUP BY {xq}
            ORDER BY {order_sql}
            LIMIT {limit}
        """
        con = duckdb.connect()
        try:
            frame = con.execute(sql, params).fetchdf()
        finally:
            con.close()
        points = [{"label": str(row["label"]), "value": json_safe(row["value"])} for _, row in frame.iterrows()]
        return jsonify({
            "dataset": ds.id, "x": x, "y": y, "aggregation": agg, "metricLabel": metric_label,
            "points": points, "groupsReturned": len(points), "version": ds.version,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 409


@app.post("/api/datasets/<dataset_id>/refresh")
def api_dataset_refresh(dataset_id: str):
    ds = get_dataset_or_404(dataset_id)
    if not ds:
        return jsonify({"error": "Dataset not found"}), 404
    if ds.kind not in {"physical", "discovered"}:
        refresh_virtual_metadata()
        return jsonify({"changed": False, "message": "This is a derived/demo dataset; refresh its source datasets instead"})
    result = refresh_physical_dataset(ds, force=True)
    return jsonify(result), (502 if "error" in result else 200)


@app.post("/api/refresh-all")
def api_refresh_all():
    def run_all() -> None:
        scan_discovery(force=True)
        with REGISTRY_LOCK:
            items = [ds for ds in DATASETS.values() if ds.kind in {"physical", "discovered"}]
        for item in items:
            refresh_physical_dataset(item, force=True)
        refresh_virtual_metadata()
    threading.Thread(target=run_all, name="manual-refresh-all", daemon=True).start()
    return jsonify({"started": True, "message": "Refresh-all started"}), 202


@app.get("/download/<dataset_id>.csv")
def download_dataset_csv(dataset_id: str):
    ds = get_dataset_or_404(dataset_id)
    if not ds:
        return jsonify({"error": "Dataset not found"}), 404
    try:
        if ds.kind in {"physical", "discovered", "demo"} and ds.csv_path.exists():
            return send_file(ds.csv_path, as_attachment=True, download_name=f"{ds.id}.csv", mimetype="text/csv")

        source_sql = dataset_source_sql(ds.id)
        temp_path = ds.csv_path.with_suffix(".csv.tmp")
        con = duckdb.connect()
        try:
            con.execute(f"COPY ({source_sql}) TO {sql_string(temp_path)} (HEADER, DELIMITER ',')")
        finally:
            con.close()
        os.replace(temp_path, ds.csv_path)
        return send_file(ds.csv_path, as_attachment=True, download_name=f"{ds.id}.csv", mimetype="text/csv")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 409


@app.get("/health")
def health():
    with REGISTRY_LOCK:
        statuses = [ds.status for ds in DATASETS.values()]
    return jsonify({
        "ok": bool(DATASETS) and any(s == "ok" for s in statuses),
        "datasets": len(statuses),
        "converterReady": sbdf is not None,
        "storage": "duckdb-parquet",
    })


def start_scheduler() -> None:
    thread = threading.Thread(target=scheduler_loop, name="multi-sbdf-scheduler", daemon=True)
    thread.start()


if __name__ == "__main__":
    start_scheduler()
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
