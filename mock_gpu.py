"""
mock_gpu.py - Mock GPU data generator for testing without NVIDIA hardware.
Simulates 4 GPUs with realistic power/temp/utilization patterns.
"""

import random
import time
import math

# Mock GPU definitions
MOCK_GPUS = [
    {"id": 0, "name": "Mock H100 SXM5", "min_power": 100, "max_power": 700, "memory_total": 80 * 1024},
    {"id": 1, "name": "Mock A100 SXM4", "min_power": 100, "max_power": 400, "memory_total": 40 * 1024},
    {"id": 2, "name": "Mock RTX 4090",  "min_power": 100, "max_power": 450, "memory_total": 24 * 1024},
    {"id": 3, "name": "Mock MI300X",    "min_power": 100, "max_power": 750, "memory_total": 192 * 1024},
]

# Internal state: power caps per GPU (starts at max)
_power_caps = {gpu["id"]: gpu["max_power"] for gpu in MOCK_GPUS}
_start_time = time.time()


def get_gpu_count() -> int:
    return len(MOCK_GPUS)


def get_gpu_info(gpu_id: int) -> dict:
    """Return simulated telemetry for a single GPU."""
    if gpu_id >= len(MOCK_GPUS):
        raise IndexError(f"GPU {gpu_id} not found")

    gpu_def = MOCK_GPUS[gpu_id]
    elapsed = time.time() - _start_time

    # Simulate realistic sinusoidal workload patterns with noise
    base_util = 55 + 35 * math.sin(elapsed / 60 + gpu_id * 1.3)
    utilization = int(max(5, min(100, base_util + random.gauss(0, 5))))

    # Power draw proportional to utilization and capped by power cap
    cap = _power_caps[gpu_id]
    power_draw = cap * (utilization / 100) * random.uniform(0.85, 1.0)
    power_draw = round(min(power_draw, cap), 1)

    # Temperature proportional to power draw
    temp_base = 38 + (power_draw / gpu_def["max_power"]) * 45
    temperature = int(temp_base + random.gauss(0, 2))

    # Memory usage
    mem_used = int(gpu_def["memory_total"] * (0.3 + 0.6 * (utilization / 100)) + random.gauss(0, 200))
    mem_used = max(0, min(mem_used, gpu_def["memory_total"]))

    return {
        "id": gpu_id,
        "name": gpu_def["name"],
        "power_draw_w": power_draw,
        "power_cap_w": cap,
        "min_power_w": gpu_def["min_power"],
        "max_power_w": gpu_def["max_power"],
        "temperature_c": temperature,
        "utilization_pct": utilization,
        "memory_used_mb": mem_used,
        "memory_total_mb": gpu_def["memory_total"],
        "is_mock": True,
    }


def set_power_cap(gpu_id: int, power_cap_w: int) -> bool:
    """Simulate setting power cap. Returns True on success."""
    if gpu_id >= len(MOCK_GPUS):
        return False
    gpu_def = MOCK_GPUS[gpu_id]
    clamped = max(gpu_def["min_power"], min(gpu_def["max_power"], power_cap_w))
    _power_caps[gpu_id] = clamped
    return True


def get_power_cap(gpu_id: int) -> int:
    return _power_caps.get(gpu_id, MOCK_GPUS[gpu_id]["max_power"])


def get_all_gpus() -> list[dict]:
    return [get_gpu_info(i) for i in range(get_gpu_count())]
