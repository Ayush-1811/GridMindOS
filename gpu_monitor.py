"""
gpu_monitor.py - NVML wrapper for GPU data collection.
Falls back to mock_gpu.py if NVIDIA drivers / pynvml are not available.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Try to import pynvml; fall back to mock mode ──────────────────────────────
try:
    import pynvml
    pynvml.nvmlInit()
    _GPU_COUNT = pynvml.nvmlDeviceGetCount()
    if _GPU_COUNT == 0:
        raise RuntimeError("No NVIDIA GPUs detected by NVML.")
    REAL_GPU = True
    logger.info(f"NVML initialized. Detected {_GPU_COUNT} GPU(s).")
except Exception as e:
    logger.warning(f"NVML unavailable ({e}). Switching to MOCK mode.")
    import mock_gpu as _mock
    REAL_GPU = False
    _GPU_COUNT = _mock.get_gpu_count()


# ── Public API ─────────────────────────────────────────────────────────────────

def is_mock_mode() -> bool:
    return not REAL_GPU


def get_gpu_count() -> int:
    return _GPU_COUNT


def get_gpu_info(gpu_id: int) -> dict:
    """Return telemetry dict for a single GPU."""
    if not REAL_GPU:
        return _mock.get_gpu_info(gpu_id)

    handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
    name   = pynvml.nvmlDeviceGetName(handle)
    if isinstance(name, bytes):
        name = name.decode()

    power_draw = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0   # mW → W
    temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
    util_rates  = pynvml.nvmlDeviceGetUtilizationRates(handle)
    utilization = util_rates.gpu
    mem_info    = pynvml.nvmlDeviceGetMemoryInfo(handle)
    mem_used_mb = mem_info.used  // (1024 * 1024)
    mem_total_mb= mem_info.total // (1024 * 1024)

    # Power cap
    try:
        power_cap_w = pynvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000.0
        min_cap_w   = pynvml.nvmlDeviceGetPowerManagementLimitConstraints(handle)[0] / 1000.0
        max_cap_w   = pynvml.nvmlDeviceGetPowerManagementLimitConstraints(handle)[1] / 1000.0
    except pynvml.NVMLError:
        power_cap_w = power_draw
        min_cap_w   = 100
        max_cap_w   = 500

    return {
        "id": gpu_id,
        "name": name,
        "power_draw_w": round(power_draw, 1),
        "power_cap_w": round(power_cap_w, 1),
        "min_power_w": round(min_cap_w, 1),
        "max_power_w": round(max_cap_w, 1),
        "temperature_c": temperature,
        "utilization_pct": utilization,
        "memory_used_mb": mem_used_mb,
        "memory_total_mb": mem_total_mb,
        "is_mock": False,
    }


def set_power_cap(gpu_id: int, power_cap_w: int) -> bool:
    """
    Set GPU power cap. Returns True on success, False on failure.
    NOTE: Requires root / sufficient Linux capabilities on real hardware.
    """
    if not REAL_GPU:
        return _mock.set_power_cap(gpu_id, power_cap_w)

    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
        pynvml.nvmlDeviceSetPowerManagementLimit(handle, int(power_cap_w * 1000))  # W → mW
        logger.info(f"GPU {gpu_id}: power cap set to {power_cap_w}W")
        return True
    except pynvml.NVMLError as e:
        logger.error(f"GPU {gpu_id}: failed to set power cap ({e})")
        return False


def get_power_cap(gpu_id: int) -> float:
    if not REAL_GPU:
        return _mock.get_power_cap(gpu_id)
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
        return pynvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000.0
    except Exception:
        return 300.0


def get_all_gpus() -> list[dict]:
    return [get_gpu_info(i) for i in range(_GPU_COUNT)]


def shutdown():
    """Call on app exit to release NVML resources."""
    if REAL_GPU:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
