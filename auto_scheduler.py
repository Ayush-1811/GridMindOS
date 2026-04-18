"""
auto_scheduler.py - Price-based GPU power throttling scheduler.
Runs in a background thread; checks price every POLL_INTERVAL seconds.
"""

import threading
import time
import logging
from typing import Optional

import gpu_monitor
import price_simulator
import database

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
POLL_INTERVAL   = 10          # seconds between price checks
THROTTLE_PCT    = 0.15        # reduce cap by 15% when price is high
DEFAULT_THRESHOLD = 7.0       # ₹/kWh default max acceptable price

# ── Shared state (thread-safe via lock) ───────────────────────────────────────
_lock           = threading.Lock()
_enabled        = False
_threshold      = DEFAULT_THRESHOLD
_throttled      = False         # are we currently in throttle mode?
_status_msg     = "Scheduler disabled"
_scheduler_thread: Optional[threading.Thread] = None
_stop_event     = threading.Event()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _save_original_caps():
    """Persist original GPU caps so we can restore them later."""
    for gpu in gpu_monitor.get_all_gpus():
        if database.get_original_cap(gpu["id"]) is None:
            database.save_original_cap(gpu["id"], gpu["power_cap_w"])


def _apply_throttle(price: float):
    """Reduce all GPU power caps by THROTTLE_PCT."""
    global _throttled
    for gpu in gpu_monitor.get_all_gpus():
        orig = database.get_original_cap(gpu["id"]) or gpu["max_power_w"]
        new_cap = int(orig * (1 - THROTTLE_PCT))
        old_cap = gpu["power_cap_w"]
        if gpu_monitor.set_power_cap(gpu["id"], new_cap):
            database.log_throttle_event(
                gpu_id=gpu["id"],
                old_cap=old_cap,
                new_cap=new_cap,
                price=price,
                reason=f"Price ₹{price:.2f}/kWh > threshold ₹{_threshold:.2f}/kWh",
            )
            logger.info(f"GPU {gpu['id']}: throttled {old_cap}W → {new_cap}W (price={price})")
    _throttled = True


def _restore_caps(price: float):
    """Restore all GPU power caps to their original values."""
    global _throttled
    for gpu in gpu_monitor.get_all_gpus():
        orig = database.get_original_cap(gpu["id"]) or gpu["max_power_w"]
        old_cap = gpu["power_cap_w"]
        if gpu_monitor.set_power_cap(gpu["id"], int(orig)):
            database.log_throttle_event(
                gpu_id=gpu["id"],
                old_cap=old_cap,
                new_cap=orig,
                price=price,
                reason=f"Price ₹{price:.2f}/kWh ≤ threshold ₹{_threshold:.2f}/kWh — restored",
            )
            logger.info(f"GPU {gpu['id']}: restored {old_cap}W → {orig}W (price={price})")
    _throttled = False


# ── Scheduler loop ─────────────────────────────────────────────────────────────

def _scheduler_loop():
    global _status_msg, _throttled

    _save_original_caps()
    logger.info("Auto-scheduler started.")

    while not _stop_event.is_set():
        with _lock:
            enabled   = _enabled
            threshold = _threshold

        if enabled:
            price = price_simulator.get_current_price()
            if price > threshold:
                if not _throttled:
                    _apply_throttle(price)
                _status_msg = (
                    f"🔴 THROTTLING — Price ₹{price:.2f}/kWh > ₹{threshold:.2f}/kWh"
                )
            else:
                if _throttled:
                    _restore_caps(price)
                _status_msg = (
                    f"🟢 Monitoring — Price ₹{price:.2f}/kWh ≤ ₹{threshold:.2f}/kWh"
                )
        else:
            _status_msg = "⚪ Scheduler disabled"

        _stop_event.wait(POLL_INTERVAL)

    logger.info("Auto-scheduler stopped.")


# ── Public API ─────────────────────────────────────────────────────────────────

def start():
    """Start the background scheduler thread."""
    global _scheduler_thread
    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True, name="GridMindScheduler")
    _scheduler_thread.start()


def stop():
    """Stop the background scheduler thread gracefully."""
    _stop_event.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=15)


def set_enabled(enabled: bool):
    global _enabled
    with _lock:
        _enabled = enabled


def set_threshold(threshold_inr: float):
    global _threshold
    with _lock:
        _threshold = threshold_inr


def get_status() -> dict:
    with _lock:
        return {
            "enabled": _enabled,
            "threshold": _threshold,
            "throttled": _throttled,
            "status_msg": _status_msg,
        }


def whatif_savings(throttle_pct: float, price_inr: float) -> dict:
    """
    Calculate estimated savings if all GPUs are throttled by throttle_pct%.
    Returns hourly savings in W, kWh, and ₹.
    """
    gpus = gpu_monitor.get_all_gpus()
    total_current_w = sum(g["power_draw_w"] for g in gpus)
    total_cap_w     = sum(g["power_cap_w"]  for g in gpus)
    reduction_w     = total_cap_w * (throttle_pct / 100)
    saved_kwh_hour  = reduction_w / 1000
    saved_inr_hour  = saved_kwh_hour * price_inr
    return {
        "current_draw_w": round(total_current_w, 1),
        "reduction_w":    round(reduction_w, 1),
        "saved_kwh_hour": round(saved_kwh_hour, 3),
        "saved_inr_hour": round(saved_inr_hour, 2),
    }
