"""
database.py - SQLite logging for telemetry snapshots and throttle events.
"""

import sqlite3
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "gridmind.db"
_lock = threading.Lock()


# ── Schema ─────────────────────────────────────────────────────────────────────

_CREATE_TELEMETRY = """
CREATE TABLE IF NOT EXISTS telemetry (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL,
    gpu_id        INTEGER NOT NULL,
    gpu_name      TEXT,
    power_draw_w  REAL,
    power_cap_w   REAL,
    temperature_c INTEGER,
    utilization   INTEGER,
    memory_used   INTEGER,
    grid_price    REAL
);
"""

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS throttle_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL,
    gpu_id        INTEGER NOT NULL,
    old_cap_w     REAL,
    new_cap_w     REAL,
    grid_price    REAL,
    reason        TEXT
);
"""

_CREATE_POWER_CAPS = """
CREATE TABLE IF NOT EXISTS original_caps (
    gpu_id   INTEGER PRIMARY KEY,
    cap_w    REAL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with _lock:
        conn = _connect()
        conn.execute(_CREATE_TELEMETRY)
        conn.execute(_CREATE_EVENTS)
        conn.execute(_CREATE_POWER_CAPS)
        conn.commit()
        conn.close()


# ── Telemetry ──────────────────────────────────────────────────────────────────

def log_telemetry(gpu_data: list[dict], grid_price: float):
    """Insert one telemetry row per GPU."""
    ts = datetime.utcnow().isoformat()
    rows = [
        (
            ts,
            g["id"],
            g["name"],
            g["power_draw_w"],
            g["power_cap_w"],
            g["temperature_c"],
            g["utilization_pct"],
            g["memory_used_mb"],
            grid_price,
        )
        for g in gpu_data
    ]
    with _lock:
        conn = _connect()
        conn.executemany(
            "INSERT INTO telemetry (timestamp,gpu_id,gpu_name,power_draw_w,power_cap_w,"
            "temperature_c,utilization,memory_used,grid_price) VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()


def get_telemetry_for_date(target_date: Optional[date] = None) -> list[dict]:
    """Fetch all telemetry rows for a given date (defaults to today, UTC)."""
    if target_date is None:
        target_date = datetime.utcnow().date()
    date_str = target_date.isoformat()
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "SELECT * FROM telemetry WHERE timestamp LIKE ? ORDER BY timestamp",
            (f"{date_str}%",),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    return rows


def get_recent_telemetry(minutes: int = 5) -> list[dict]:
    """Fetch telemetry rows from the last N minutes."""
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "SELECT * FROM telemetry WHERE timestamp >= ? ORDER BY timestamp",
            (cutoff,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    return rows


# ── Throttle events ────────────────────────────────────────────────────────────

def log_throttle_event(gpu_id: int, old_cap: float, new_cap: float, price: float, reason: str):
    ts = datetime.utcnow().isoformat()
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO throttle_events (timestamp,gpu_id,old_cap_w,new_cap_w,grid_price,reason) "
            "VALUES (?,?,?,?,?,?)",
            (ts, gpu_id, old_cap, new_cap, price, reason),
        )
        conn.commit()
        conn.close()


def get_throttle_events(limit: int = 100) -> list[dict]:
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "SELECT * FROM throttle_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    return rows


# ── Original power caps (for restore) ─────────────────────────────────────────

def save_original_cap(gpu_id: int, cap_w: float):
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO original_caps (gpu_id, cap_w) VALUES (?,?) "
            "ON CONFLICT(gpu_id) DO NOTHING",
            (gpu_id, cap_w),
        )
        conn.commit()
        conn.close()


def get_original_cap(gpu_id: int) -> Optional[float]:
    with _lock:
        conn = _connect()
        cur = conn.execute("SELECT cap_w FROM original_caps WHERE gpu_id=?", (gpu_id,))
        row = cur.fetchone()
        conn.close()
    return row["cap_w"] if row else None


# ── Energy statistics ──────────────────────────────────────────────────────────

def get_daily_stats(target_date: Optional[date] = None) -> dict:
    """Compute energy used, cost, and estimated savings for a day."""
    rows = get_telemetry_for_date(target_date)
    if not rows:
        return {"energy_kwh": 0.0, "cost_inr": 0.0, "savings_kwh": 0.0, "avg_util": 0.0}

    # Sum power × time interval (assume 2-second polling = 2/3600 hours per sample)
    interval_h = 2 / 3600
    energy_kwh = sum(r["power_draw_w"] / 1000 * interval_h for r in rows)

    # Cost: price at time of measurement
    cost_inr = sum(r["power_draw_w"] / 1000 * interval_h * r["grid_price"] for r in rows)

    # Savings = difference between cap and actual draw (opportunity not wasted)
    savings_kwh = sum(
        max(0, (r["power_cap_w"] - r["power_draw_w"]) / 1000 * interval_h) for r in rows
    )

    avg_util = sum(r["utilization"] for r in rows) / len(rows)

    return {
        "energy_kwh": round(energy_kwh, 3),
        "cost_inr": round(cost_inr, 2),
        "savings_kwh": round(savings_kwh, 3),
        "avg_util": round(avg_util, 1),
    }
