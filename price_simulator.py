"""
price_simulator.py - Mock IEX (Indian Energy Exchange) price generator.
Generates realistic day-ahead electricity prices in ₹/kWh with diurnal patterns.
"""

import math
import time
import random
import urllib.request
import ssl
import re
from datetime import datetime
from typing import Optional

# ── Price pattern parameters (₹/kWh) ─────────────────────────────────────────
BASE_PRICE    = 4.5    # baseline price
NIGHT_DIP     = -1.5   # cheaper at night (00:00–05:00)
MORNING_BUMP  = +1.2   # morning ramp (06:00–09:00)
AFTERNOON_LOW = -1.0   # solar generation dip (12:00–16:00)
EVENING_PEAK  = +3.5   # demand peak (18:00–22:00)

# Manual override (set to None to use simulator)
_manual_override: Optional[float] = None


def _diurnal_price(hour: float) -> float:
    """Compute price based on hour-of-day (0–24)."""
    # Smooth approximation using sinusoids
    # Main daily cycle
    cycle1 = -math.cos(2 * math.pi * hour / 24)           # low at noon, high at midnight
    # Evening peak enhancement (centred at 20:00)
    cycle2 = math.exp(-0.5 * ((hour - 20) / 2.5) ** 2)   # Gaussian peak at 20:00
    # Solar generation dip (centred at 14:00)
    cycle3 = -math.exp(-0.5 * ((hour - 14) / 2.0) ** 2)  # Gaussian dip at 14:00

    raw = BASE_PRICE + 1.2 * cycle1 + 2.8 * cycle2 + 1.5 * cycle3
    # Add slight random noise (±3%)
    noise = random.gauss(0, raw * 0.03)
    return max(1.5, round(raw + noise, 2))


_cached_real_time_price = None
_last_fetch_time = 0

def fetch_real_time_price() -> Optional[float]:
    global _cached_real_time_price, _last_fetch_time
    # Cache for 2 minutes to prevent ratelimits
    if time.time() - _last_fetch_time < 120 and _cached_real_time_price is not None:
        return _cached_real_time_price
        
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request('https://iexrtmprice.com/', headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, context=ctx, timeout=5).read().decode('utf-8')
        match = re.search(r'id=[\"\']lastPrice[\"\'][^>]*>([\d\.]+)<\/span>', html)
        if match:
            price = float(match.group(1))
            _cached_real_time_price = price
            _last_fetch_time = time.time()
            return price
    except Exception as e:
        print(f"Error fetching real time IEX data: {e}")
    return None


def get_current_price() -> float:
    """Return the current real-time grid price in ₹/kWh, falling back to simulation if unavailable."""
    if _manual_override is not None:
        return _manual_override
        
    # Attempt to fetch real time IEX data
    real_time_price = fetch_real_time_price()
    if real_time_price is not None:
        return real_time_price
        
    now = datetime.now()
    hour = now.hour + now.minute / 60.0
    return _diurnal_price(hour)


def set_manual_price(price: Optional[float]):
    """Override the simulated price. Pass None to restore simulation."""
    global _manual_override
    _manual_override = price


def get_price_category(price: float) -> str:
    """Return 'low', 'medium', or 'high' label."""
    if price < 5.0:
        return "low"
    elif price < 8.0:
        return "medium"
    return "high"


def get_forecast_24h() -> list[dict]:
    """Return 24-hour price forecast (hourly)."""
    forecast = []
    for h in range(24):
        price = _diurnal_price(h + 0.5)  # midpoint of each hour
        forecast.append({
            "hour": h,
            "label": f"{h:02d}:00",
            "price": price,
            "category": get_price_category(price),
        })
    return forecast


def is_manual_override() -> bool:
    return _manual_override is not None
