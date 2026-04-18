# ⚡ GridMind OS

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://streamlit.io)

> **Workload-to-Watt Orchestrator** — Transform your GPU cluster into an Active Grid Asset by optimising power consumption based on real-time electricity prices.

**Status:** MVP / Production Ready  
**Author:** GridMind Contributors  
**Contributions:** Welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## What It Does

GridMind OS sits between your AI workloads and the power grid. It:

1. **Monitors** all NVIDIA GPUs in real time (power, temperature, utilisation, VRAM)
2. **Throttles** GPU power caps automatically when electricity prices spike
3. **Fetches** live, real-time Indian Energy Exchange (IEX) Day-Ahead Market pricing (with fallback simulation)
4. **Logs** every action to SQLite and lets you export telemetry as CSV
5. **Works without a GPU** — runs in mock/demo mode automatically

---

## Requirements

| Component | Requirement |
|-----------|-------------|
| OS | Ubuntu 22.04 (or any Linux with NVIDIA drivers) |
| Python | 3.10 or newer |
| NVIDIA GPU | Optional — mock mode works without one |
| NVIDIA Driver | ≥ 520 recommended (for pynvml) |
| Root / sudo | Required **only** for setting GPU power caps on real hardware |

---

## Quick Start

### 1. Clone / unzip

```bash
unzip gridmind-mvp.zip
cd gridmind-mvp
```

### 2. Create a virtual environment (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `pynvml` is listed but optional. If NVIDIA drivers are not present, the app automatically switches to mock mode. No error.

### 4. Run the dashboard

```bash
streamlit run app.py
```

Open your browser at **http://localhost:8501**

---

## Running with Real NVIDIA GPUs

Setting GPU power caps requires elevated privileges on Linux.

### Option A — Run as root (simplest)

```bash
sudo $(which streamlit) run app.py
```

### Option B — Grant capabilities to Python binary

```bash
sudo setcap cap_sys_admin+ep $(readlink -f $(which python3))
streamlit run app.py
```

### Verify throttling is working

In a separate terminal:

```bash
watch -n1 nvidia-smi --query-gpu=index,power.draw,power.limit --format=csv
```

When you move a slider or the auto-scheduler triggers, you should see `power.limit` change.

---

## File Structure

```
gridmind-mvp/
├── app.py              # Main Streamlit dashboard (UI + tabs)
├── gpu_monitor.py      # NVML wrapper; falls back to mock_gpu.py
├── mock_gpu.py         # Simulates 4 GPUs (H100, A100, RTX 4090, MI300X)
├── price_simulator.py  # Live IEX price scraper with diurnal simulation fallback
├── auto_scheduler.py   # Background thread: price-based throttling logic
├── database.py         # SQLite helpers: telemetry, events, stats
├── get_iex.py          # Standalone test script to verify IEX real-time price scraping
├── requirements.txt
└── README.md
```

---

## Dashboard Tabs

### 📊 Dashboard
- **Header bar:** Live grid price with colour indicator (🟢 low / 🟡 medium / 🔴 high)
- **Metrics row:** Total kW draw · Hourly cost (₹) · Daily energy (kWh) · Savings
- **GPU cards:** Per-GPU power, temperature, utilisation, VRAM + manual power-cap slider
- **Bulk controls:** Set all GPUs to a fixed watt cap or restore max caps
- **Charts:** Rolling 5-minute power draw · 24-hour price forecast

### 🤖 Auto-Scheduler
- Enable/disable the background price-watcher
- Set your **maximum acceptable price threshold** (₹/kWh slider)
- Lock the grid price manually (useful for testing)
- **What-If Calculator:** "If I throttle all GPUs by X%, I save ₹Y/hour"
- Throttle event log with timestamps

### 📋 Reports
- Date picker → daily energy (kWh), cost (₹), savings, avg utilisation
- Full-day power draw and grid-price charts
- **Download** telemetry + events as CSV

---

## How Auto-Scheduling Works

```
Every 10 seconds:
  price = get_current_price()
  if price > threshold AND not already throttled:
      for each GPU:
          new_cap = original_cap × 0.85   # 15% reduction
          set_power_cap(gpu, new_cap)
          log_event(...)
  elif price ≤ threshold AND currently throttled:
      for each GPU:
          restore original_cap
          log_event(...)
```

---

## Configuration

All key parameters are in-code constants (easy to move to a `.env` file):

| File | Constant | Default | Meaning |
|------|----------|---------|---------|
| `auto_scheduler.py` | `POLL_INTERVAL` | `10` | Seconds between price checks |
| `auto_scheduler.py` | `THROTTLE_PCT` | `0.15` | Fraction to reduce caps by |
| `auto_scheduler.py` | `DEFAULT_THRESHOLD` | `7.0` | Starting price threshold (₹/kWh) |
| `price_simulator.py` | `BASE_PRICE` | `4.5` | Baseline electricity price |

---

## Live IEX Data Fetching

App now actively fetches real-time Day-Ahead Market (DAM) price data via an IEX price aggregator website using regular expressions. To prevent rate-limiting, fetched prices are cached for 2 minutes.

If network access fails or the aggregator is unavailable, GridMind gracefully falls back to a mathematical diurnal simulation so that testing and auto-scheduling can continue uninterrupted.

---

## Testing Checklist

- [x] App runs without NVIDIA GPU (mock mode banner shown)
- [x] With NVIDIA GPU, reads real power data via NVML
- [x] Throttle slider changes GPU power cap (verify with `nvidia-smi`)
- [x] Auto-scheduler throttles when price exceeds threshold
- [x] Throttle events logged to SQLite and shown in UI
- [x] CSV export works for both telemetry and events
- [x] What-If calculator shows savings estimate

---

## License

MIT — use freely, credit appreciated.
