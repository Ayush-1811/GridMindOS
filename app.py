"""
app.py - GridMind OS — Streamlit dashboard entry point.

Run with:
    streamlit run app.py
"""

import io
import csv
import time
import logging
import threading
from datetime import datetime, date

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

import database
import gpu_monitor
import price_simulator
import auto_scheduler

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Page config (MUST be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="GridMind OS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* ── Base theme overrides ── */
  [data-testid="stAppViewContainer"] { background: #0a0e1a; }
  [data-testid="stHeader"] { background: transparent; }

  /* ── Custom font ── */
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Syne', sans-serif; }
  code, pre, .mono { font-family: 'JetBrains Mono', monospace; }

  /* ── Metric cards ── */
  [data-testid="metric-container"] {
    background: linear-gradient(135deg, #111827 0%, #1a2235 100%);
    border: 1px solid #1e3a5f;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    box-shadow: 0 0 20px rgba(0,120,255,0.08);
  }
  [data-testid="stMetricValue"] { color: #60a5fa; font-size: 1.8rem !important; font-weight: 800; }
  [data-testid="stMetricLabel"] { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; }

  /* ── Section headers ── */
  .section-header {
    font-family: 'Syne', sans-serif;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #475569;
    margin: 1.5rem 0 0.5rem 0;
    border-bottom: 1px solid #1e2d45;
    padding-bottom: 0.3rem;
  }

  /* ── Price badge ── */
  .price-badge-low    { background:#064e3b; color:#34d399; padding:4px 14px; border-radius:20px; font-weight:700; font-size:1.1rem; }
  .price-badge-medium { background:#78350f; color:#fbbf24; padding:4px 14px; border-radius:20px; font-weight:700; font-size:1.1rem; }
  .price-badge-high   { background:#7f1d1d; color:#f87171; padding:4px 14px; border-radius:20px; font-weight:700; font-size:1.1rem; }

  /* ── GPU card ── */
  .gpu-card {
    background: linear-gradient(135deg, #0f172a, #1e293b);
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 1rem;
    margin-bottom: 0.6rem;
  }
  .gpu-name { color: #e2e8f0; font-weight: 700; font-size: 0.95rem; }
  .gpu-stat { color: #64748b; font-size: 0.8rem; }
  .gpu-stat span { color: #94a3b8; }

  /* ── Event log ── */
  .event-row-throttle { border-left: 3px solid #ef4444; padding-left: 8px; margin: 4px 0; font-size:0.8rem; color:#fca5a5; }
  .event-row-restore  { border-left: 3px solid #22c55e; padding-left: 8px; margin: 4px 0; font-size:0.8rem; color:#86efac; }

  /* ── Tab styling ── */
  [data-testid="stTab"] { color: #64748b; }
  [data-testid="stTab"][aria-selected="true"] { color: #60a5fa; border-bottom-color: #60a5fa; }

  /* ── Status pill ── */
  .status-ok  { color:#34d399; font-weight:700; }
  .status-warn{ color:#fbbf24; font-weight:700; }
  .status-bad { color:#f87171; font-weight:700; }

  /* ── Divider ── */
  hr { border-color: #1e2d45; }

  /* ── Mock mode banner ── */
  .mock-banner {
    background: linear-gradient(90deg, #1e1035, #2d1b69);
    border: 1px solid #7c3aed;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    color: #a78bfa;
    font-size: 0.85rem;
    margin-bottom: 1rem;
  }
</style>
""", unsafe_allow_html=True)


# ── Initialisation (once per session) ─────────────────────────────────────────

@st.cache_resource
def initialise():
    database.init_db()
    auto_scheduler.start()
    return True

initialise()

# ── Background telemetry logger (daemon thread) ────────────────────────────────

def _telemetry_logger():
    """Logs GPU telemetry to SQLite every 2 seconds."""
    while True:
        try:
            gpus  = gpu_monitor.get_all_gpus()
            price = price_simulator.get_current_price()
            database.log_telemetry(gpus, price)
        except Exception as e:
            logging.error(f"Telemetry log error: {e}")
        time.sleep(2)

if "telem_thread_started" not in st.session_state:
    t = threading.Thread(target=_telemetry_logger, daemon=True, name="TelemLogger")
    t.start()
    st.session_state["telem_thread_started"] = True


# ── Helpers ────────────────────────────────────────────────────────────────────

def price_badge(price: float) -> str:
    cat = price_simulator.get_price_category(price)
    icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}[cat]
    css_cls = f"price-badge-{cat}"
    return f'<span class="{css_cls}">{icon} ₹{price:.2f}/kWh</span>'


def util_color(pct: int) -> str:
    if pct < 40: return "#22c55e"
    if pct < 75: return "#fbbf24"
    return "#ef4444"


def temp_color(c: int) -> str:
    if c < 60: return "#22c55e"
    if c < 75: return "#fbbf24"
    return "#ef4444"


# ══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════════════════════

col_logo, col_price, col_time = st.columns([3, 2, 1])
with col_logo:
    st.markdown("## ⚡ GridMind OS")
    st.markdown('<p style="color:#475569;font-size:0.8rem;margin-top:-12px">Workload-to-Watt Orchestrator</p>', unsafe_allow_html=True)

with col_price:
    price_now = price_simulator.get_current_price()
    st.markdown(f"### {price_badge(price_now)}", unsafe_allow_html=True)
    cat = price_simulator.get_price_category(price_now)
    labels = {"low": "Grid price is low — full performance", "medium": "Grid price moderate — monitor", "high": "Grid price HIGH — consider throttling"}
    st.caption(labels[cat])

with col_time:
    st.metric("UTC Time", datetime.utcnow().strftime("%H:%M:%S"))

if gpu_monitor.is_mock_mode():
    st.markdown('<div class="mock-banner">🔮 <b>DEMO MODE</b> — No NVIDIA GPU detected. Running with simulated GPU data. Install NVIDIA drivers + pynvml for real hardware.</div>', unsafe_allow_html=True)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════════════════════

tab_dash, tab_sched, tab_reports = st.tabs(["📊 Dashboard", "🤖 Auto-Scheduler", "📋 Reports"])


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 1 — DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

with tab_dash:
    gpus = gpu_monitor.get_all_gpus()
    total_power_w = sum(g["power_draw_w"] for g in gpus)
    hourly_cost   = total_power_w / 1000 * price_now
    daily_stats   = database.get_daily_stats()

    # ── Top-level metrics ──
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Power Draw", f"{total_power_w/1000:.2f} kW",
              delta=f"{len(gpus)} GPU(s)")
    m2.metric("Est. Hourly Cost", f"₹{hourly_cost:.2f}",
              delta=f"@ ₹{price_now:.2f}/kWh")
    m3.metric("Energy Used Today", f"{daily_stats['energy_kwh']:.2f} kWh",
              delta=f"₹{daily_stats['cost_inr']:.0f} total cost")
    m4.metric("Savings Today", f"{daily_stats['savings_kwh']:.3f} kWh",
              delta="vs uncapped draw")

    # ── GPU Table ──
    st.markdown('<p class="section-header">GPU Cluster</p>', unsafe_allow_html=True)

    for gpu in gpus:
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 3])
            with c1:
                st.markdown(f'<div class="gpu-name">GPU {gpu["id"]} — {gpu["name"]}</div>', unsafe_allow_html=True)
                mem_pct = gpu["memory_used_mb"] / gpu["memory_total_mb"] * 100
                st.progress(int(mem_pct), text=f"VRAM {gpu['memory_used_mb']//1024:.1f}/{gpu['memory_total_mb']//1024:.0f} GB")
            with c2:
                st.metric("Power", f"{gpu['power_draw_w']:.0f} W",
                          delta=f"cap {gpu['power_cap_w']:.0f}W")
            with c3:
                st.metric("Temp",
                          f"{gpu['temperature_c']}°C")
            with c4:
                st.metric("Util", f"{gpu['utilization_pct']}%")
            with c5:
                new_cap = st.slider(
                    f"Power Cap — GPU {gpu['id']}",
                    min_value=int(gpu["min_power_w"]),
                    max_value=int(gpu["max_power_w"]),
                    value=int(gpu["power_cap_w"]),
                    step=10,
                    key=f"cap_slider_{gpu['id']}",
                    label_visibility="collapsed",
                )
                if new_cap != int(gpu["power_cap_w"]):
                    if gpu_monitor.set_power_cap(gpu["id"], new_cap):
                        st.toast(f"GPU {gpu['id']} cap → {new_cap}W", icon="⚡")

        st.divider()

    # ── Bulk throttle ──
    st.markdown('<p class="section-header">Bulk Power Control</p>', unsafe_allow_html=True)
    bcol1, bcol2, bcol3 = st.columns([2, 2, 2])
    with bcol1:
        bulk_cap = st.number_input("Set ALL GPUs to (W)", min_value=100, max_value=750,
                                   value=300, step=10, key="bulk_cap")
    with bcol2:
        if st.button("⚡ Apply to All GPUs", use_container_width=True):
            for gpu in gpus:
                gpu_monitor.set_power_cap(gpu["id"], bulk_cap)
            st.toast(f"All GPUs capped at {bulk_cap}W", icon="✅")
    with bcol3:
        if st.button("↩️ Restore Max Caps", use_container_width=True):
            for gpu in gpus:
                gpu_monitor.set_power_cap(gpu["id"], int(gpu["max_power_w"]))
            st.toast("All GPUs restored to max caps", icon="✅")

    # ── Power chart ──
    st.markdown('<p class="section-header">Power Draw — Last 5 Minutes</p>', unsafe_allow_html=True)

    recent = database.get_recent_telemetry(minutes=5)
    if recent:
        df_recent = pd.DataFrame(recent)
        df_recent["timestamp"] = pd.to_datetime(df_recent["timestamp"])
        fig = go.Figure()
        for gid in df_recent["gpu_id"].unique():
            sub = df_recent[df_recent["gpu_id"] == gid]
            gname = sub["gpu_name"].iloc[0]
            fig.add_trace(go.Scatter(
                x=sub["timestamp"], y=sub["power_draw_w"],
                name=f"GPU {gid} {gname}",
                mode="lines",
                line=dict(width=2),
                fill="tozeroy",
                fillcolor=f"rgba({50+gid*50},{100+gid*30},255,0.05)",
            ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", family="Syne"),
            xaxis=dict(gridcolor="#1e293b", title="Time (UTC)"),
            yaxis=dict(gridcolor="#1e293b", title="Power (W)"),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=0, r=0, t=20, b=0),
            height=280,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Collecting telemetry… refresh in a few seconds.")

    # ── 24h Price Forecast ──
    st.markdown('<p class="section-header">24-Hour Price Forecast (Simulated)</p>', unsafe_allow_html=True)
    forecast = price_simulator.get_forecast_24h()
    df_fc = pd.DataFrame(forecast)
    color_map = {"low": "#22c55e", "medium": "#fbbf24", "high": "#ef4444"}
    fig2 = go.Figure(go.Bar(
        x=df_fc["label"], y=df_fc["price"],
        marker_color=[color_map[c] for c in df_fc["category"]],
        text=[f"₹{p:.1f}" for p in df_fc["price"]],
        textposition="outside",
        textfont=dict(size=9, color="#94a3b8"),
    ))
    current_h = datetime.utcnow().hour
    fig2.add_vline(x=current_h, line_color="#60a5fa", line_dash="dash",
                   annotation_text="Now", annotation_font_color="#60a5fa")
    fig2.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8", family="Syne"),
        xaxis=dict(gridcolor="#1e293b"),
        yaxis=dict(gridcolor="#1e293b", title="₹/kWh"),
        margin=dict(l=0, r=0, t=10, b=0),
        height=250,
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Auto-refresh ──
    st.caption("⟳ Auto-refreshes every 2 seconds")
    time.sleep(2)
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 2 — SCHEDULER
# ─────────────────────────────────────────────────────────────────────────────

with tab_sched:
    status = auto_scheduler.get_status()

    st.markdown('<p class="section-header">Auto-Scheduler Configuration</p>', unsafe_allow_html=True)

    sc1, sc2 = st.columns([1, 2])
    with sc1:
        enabled_toggle = st.toggle(
            "Enable Auto-Scheduler",
            value=status["enabled"],
            key="sched_toggle",
        )
        auto_scheduler.set_enabled(enabled_toggle)

    with sc2:
        threshold = st.slider(
            "Max Acceptable Grid Price (₹/kWh)",
            min_value=2.0, max_value=20.0,
            value=float(status["threshold"]),
            step=0.5,
            key="sched_threshold",
        )
        auto_scheduler.set_threshold(threshold)

    # Manual price override
    st.markdown('<p class="section-header">Grid Price Override</p>', unsafe_allow_html=True)
    ov1, ov2, ov3 = st.columns([2, 1, 1])
    with ov1:
        manual_price = st.number_input(
            "Manual Price Override (₹/kWh)",
            min_value=1.0, max_value=30.0,
            value=price_simulator.get_current_price(),
            step=0.5, key="manual_price",
        )
    with ov2:
        if st.button("🔒 Lock Price", use_container_width=True):
            price_simulator.set_manual_price(manual_price)
            st.toast(f"Price locked at ₹{manual_price:.2f}/kWh", icon="🔒")
    with ov3:
        if st.button("🔓 Use Live IEX Data", use_container_width=True):
            price_simulator.set_manual_price(None)
            st.toast("Using live market prices", icon="📡")

    # Status display
    st.markdown('<p class="section-header">Current Status</p>', unsafe_allow_html=True)
    fresh_status = auto_scheduler.get_status()
    st.markdown(f"""
    <div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:10px;padding:1rem;font-family:'JetBrains Mono',monospace;font-size:0.9rem;color:#94a3b8;">
        {fresh_status['status_msg']}
        &nbsp;&nbsp;|&nbsp;&nbsp; Threshold: ₹{fresh_status['threshold']:.2f}/kWh
        &nbsp;&nbsp;|&nbsp;&nbsp; Throttled: {'YES 🔴' if fresh_status['throttled'] else 'NO 🟢'}
    </div>
    """, unsafe_allow_html=True)

    # ── What-If Calculator ──
    st.markdown('<p class="section-header">💡 What-If Calculator</p>', unsafe_allow_html=True)
    wi1, wi2 = st.columns(2)
    with wi1:
        wi_pct = st.slider("Throttle all GPUs by (%)", 5, 50, 15, key="wi_pct")
    with wi2:
        wi_price = st.number_input("At grid price (₹/kWh)", 1.0, 30.0,
                                   price_simulator.get_current_price(), 0.5, key="wi_price")

    savings = auto_scheduler.whatif_savings(wi_pct, wi_price)
    wc1, wc2, wc3 = st.columns(3)
    wc1.metric("Current Draw", f"{savings['current_draw_w']:.0f} W")
    wc2.metric("Power Reduction", f"{savings['reduction_w']:.0f} W")
    wc3.metric("Hourly Savings", f"₹{savings['saved_inr_hour']:.2f}",
               delta=f"{savings['saved_kwh_hour']:.3f} kWh/hr")

    # ── Event Log ──
    st.markdown('<p class="section-header">Throttle Event Log</p>', unsafe_allow_html=True)
    events = database.get_throttle_events(limit=50)
    if events:
        df_ev = pd.DataFrame(events)
        df_ev["timestamp"] = pd.to_datetime(df_ev["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        df_ev["Δ cap (W)"] = df_ev["new_cap_w"] - df_ev["old_cap_w"]
        df_ev.rename(columns={
            "timestamp": "Time (UTC)",
            "gpu_id": "GPU",
            "old_cap_w": "Old Cap (W)",
            "new_cap_w": "New Cap (W)",
            "grid_price": "Price (₹/kWh)",
            "reason": "Reason",
        }, inplace=True)
        st.dataframe(
            df_ev[["Time (UTC)", "GPU", "Old Cap (W)", "New Cap (W)", "Δ cap (W)", "Price (₹/kWh)", "Reason"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No throttle events logged yet.")


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 3 — REPORTS
# ─────────────────────────────────────────────────────────────────────────────

with tab_reports:
    st.markdown('<p class="section-header">Energy Report</p>', unsafe_allow_html=True)

    report_date = st.date_input("Select Date", value=date.today(), key="report_date")
    stats = database.get_daily_stats(report_date)

    rp1, rp2, rp3, rp4 = st.columns(4)
    rp1.metric("Total Energy",     f"{stats['energy_kwh']:.3f} kWh")
    rp2.metric("Total Cost",       f"₹{stats['cost_inr']:.2f}")
    rp3.metric("Est. Savings",     f"{stats['savings_kwh']:.3f} kWh")
    rp4.metric("Avg GPU Util",     f"{stats['avg_util']:.1f}%")

    # Chart: power draw over the day
    day_rows = database.get_telemetry_for_date(report_date)
    if day_rows:
        df_day = pd.DataFrame(day_rows)
        df_day["timestamp"] = pd.to_datetime(df_day["timestamp"])

        # Power per GPU
        st.markdown('<p class="section-header">Power Draw — Full Day</p>', unsafe_allow_html=True)
        fig3 = go.Figure()
        for gid in df_day["gpu_id"].unique():
            sub = df_day[df_day["gpu_id"] == gid]
            gname = sub["gpu_name"].iloc[0]
            fig3.add_trace(go.Scatter(
                x=sub["timestamp"], y=sub["power_draw_w"],
                name=f"GPU {gid}", mode="lines",
                line=dict(width=1.5),
            ))
        fig3.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", family="Syne"),
            xaxis=dict(gridcolor="#1e293b"),
            yaxis=dict(gridcolor="#1e293b", title="Power (W)"),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=0, r=0, t=10, b=0),
            height=250,
        )
        st.plotly_chart(fig3, use_container_width=True)

        # Grid price over the day
        st.markdown('<p class="section-header">Grid Price — Full Day</p>', unsafe_allow_html=True)
        df_price = df_day.groupby("timestamp")["grid_price"].mean().reset_index()
        fig4 = px.area(df_price, x="timestamp", y="grid_price",
                       color_discrete_sequence=["#fbbf24"])
        fig4.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", family="Syne"),
            xaxis=dict(gridcolor="#1e293b", title="Time (UTC)"),
            yaxis=dict(gridcolor="#1e293b", title="₹/kWh"),
            margin=dict(l=0, r=0, t=10, b=0),
            height=220,
        )
        st.plotly_chart(fig4, use_container_width=True)

        # ── CSV Export ──
        st.markdown('<p class="section-header">Export Data</p>', unsafe_allow_html=True)

        def make_csv(rows: list[dict]) -> bytes:
            if not rows:
                return b""
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
            return buf.getvalue().encode()

        csv_bytes = make_csv(day_rows)
        st.download_button(
            label="⬇️ Download Telemetry CSV",
            data=csv_bytes,
            file_name=f"gridmind_telemetry_{report_date.isoformat()}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        events_rows = database.get_throttle_events(limit=10000)
        if events_rows:
            ev_csv = make_csv(events_rows)
            st.download_button(
                label="⬇️ Download Throttle Events CSV",
                data=ev_csv,
                file_name=f"gridmind_events_{report_date.isoformat()}.csv",
                mime="text/csv",
                use_container_width=True,
            )
    else:
        st.info(f"No telemetry data found for {report_date}. Data appears after the dashboard starts collecting.")
