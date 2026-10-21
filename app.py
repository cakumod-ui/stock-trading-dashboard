import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bot import PaperTradingRiskManager

st.set_page_config(page_title="ICICI Paper Trading Dashboard", layout="wide")
st.title("📊 ICICI Breeze Paper Trading Dashboard")
st.caption("Real-time portfolio view for paper trades, live P&L, and position monitoring")


@st.cache_resource
def initialize_risk_manager():
    """Create a paper trading manager and seed a few demo positions."""
    mgr = PaperTradingRiskManager(initial_capital=100000.0, max_daily_loss=1500.0)
    mgr.execute_paper_order("TCS", 20, 3800.0, "BUY")
    mgr.execute_paper_order("INFY", 25, 1450.0, "BUY")
    mgr.execute_paper_order("ITC", 80, 450.0, "BUY")
    return mgr


@st.cache_data(ttl=5)
def fetch_live_market(symbols):
    """Return mock live prices for the current positions. This replaces a real market feed in demo mode."""
    base_prices = {
        "TCS": 3800.0,
        "INFY": 1450.0,
        "ITC": 450.0,
        "RELIND": 965.0,
        "HDFCBANK": 1635.0,
    }
    rows = []
    for symbol in symbols:
        base = base_prices.get(symbol, 100.0)
        drift = ((hash(symbol) % 31) / 10.0) - 1.0
        live_price = round(base * (1 + drift / 100), 2)
        rows.append({
            "symbol": symbol,
            "price": live_price,
            "day_change_pct": round(((live_price - base) / base) * 100, 2),
        })
    return pd.DataFrame(rows)


def build_position_table(risk_manager, latest_prices):
    """Compute and format open position analytics."""
    rows = []
    total_unrealized = 0.0
    for symbol, pos in risk_manager.positions.items():
        qty = pos["qty"]
        avg_price = pos["entry_price"]
        current_price = float(latest_prices.get(symbol, avg_price))
        pnl = (current_price - avg_price) * qty
        total_unrealized += pnl
        rows.append({
            "symbol": symbol,
            "qty": qty,
            "entry": avg_price,
            "current": current_price,
            "pnl": pnl,
            "sl": pos["sl"],
            "tp": pos["tp"],
        })
    return pd.DataFrame(rows), total_unrealized


risk_manager = initialize_risk_manager()

if "equity_curve" not in st.session_state:
    st.session_state.equity_curve = [100000.0]

with st.sidebar:
    st.subheader("Portfolio Controls")
    st.metric("Cash Balance", f"₹{risk_manager.capital:,.2f}")
    st.metric("Daily Max Loss", f"₹{risk_manager.max_daily_loss:,.2f}")
    st.metric("Trading Active", "Yes" if risk_manager.active else "No")
    refresh_seconds = st.slider("Refresh interval (seconds)", 1, 10, 2)
    if st.button("Refresh now"):
        st.rerun()

# Fetch mock live prices based on open holdings.
market = fetch_live_market(list(risk_manager.positions.keys()) or ["TCS", "INFY", "ITC"])
latest_prices = {row["symbol"]: row["price"] for _, row in market.iterrows()}
position_df, unrealized_pnl = build_position_table(risk_manager, latest_prices)

current_portfolio_value = risk_manager.capital + sum(position_df["pnl"]) + risk_manager.realized_pnl if not position_df.empty else risk_manager.capital + risk_manager.realized_pnl
st.session_state.equity_curve.append(current_portfolio_value)
if len(st.session_state.equity_curve) > 30:
    st.session_state.equity_curve = st.session_state.equity_curve[-30:]

# KPI cards
kpis = st.columns(5)
with kpis[0]:
    st.metric("Portfolio Value", f"₹{current_portfolio_value:,.2f}")
with kpis[1]:
    st.metric("Cash Balance", f"₹{risk_manager.capital:,.2f}")
with kpis[2]:
    st.metric("Realized P&L", f"₹{risk_manager.realized_pnl:,.2f}")
with kpis[3]:
    st.metric("Unrealized P&L", f"₹{unrealized_pnl:,.2f}")
with kpis[4]:
    st.metric("Net P&L", f"₹{risk_manager.realized_pnl + unrealized_pnl:,.2f}")

# Main charts
chart_col, side_col = st.columns([2, 1])

with chart_col:
    eq_data = pd.DataFrame({
        "step": list(range(len(st.session_state.equity_curve))),
        "value": st.session_state.equity_curve,
    })
    equity_fig = go.Figure()
    equity_fig.add_trace(go.Scatter(x=eq_data["step"], y=eq_data["value"], mode="lines+markers", line={"color": "#00C2FF"}, name="Portfolio Value"))
    equity_fig.update_layout(title="Portfolio Equity Curve", template="plotly_dark", height=360, xaxis_title="Sample", yaxis_title="Value (₹)")
    st.plotly_chart(equity_fig, use_container_width=True)

    if not position_df.empty:
        pnl_fig = go.Figure(go.Bar(
            x=position_df["symbol"],
            y=position_df["pnl"],
            marker_color=["#2ecc71" if v >= 0 else "#e74c3c" for v in position_df["pnl"]]
        ))
        pnl_fig.update_layout(title="Position-wise P&L", template="plotly_dark", height=280, xaxis_title="Ticker", yaxis_title="P&L (₹)")
        st.plotly_chart(pnl_fig, use_container_width=True)

with side_col:
    st.subheader("Open Positions")
    if not position_df.empty:
        display_df = position_df[["symbol", "qty", "entry", "current", "pnl", "sl", "tp"]].copy()
        display_df.columns = ["Ticker", "Qty", "Entry", "Current", "P&L", "SL", "TP"]
        st.dataframe(display_df.style.format({
            "Entry": "₹{:.2f}",
            "Current": "₹{:.2f}",
            "P&L": "₹{:.2f}",
            "SL": "₹{:.2f}",
            "TP": "₹{:.2f}",
        }), use_container_width=True)
    else:
        st.info("No open positions.")

    st.subheader("Live Market")
    st.dataframe(market.style.format({"price": "₹{:.2f}", "day_change_pct": "+{:.2f}%"}), use_container_width=True)

# Trade simulation controls
st.subheader("Quick Trade Simulation")
trade_col1, trade_col2, trade_col3 = st.columns(3)
with trade_col1:
    trade_symbol = st.selectbox("Ticker", ["TCS", "INFY", "ITC", "RELIND", "HDFCBANK"])
with trade_col2:
    trade_qty = st.number_input("Quantity", min_value=1, max_value=500, value=10)
with trade_col3:
    trade_price = st.number_input("Price", min_value=1.0, max_value=10000.0, value=1000.0, step=1.0)

if st.button("Simulate BUY"):
    risk_manager.execute_paper_order(trade_symbol, trade_qty, trade_price, "BUY")
    st.success(f"Bought {trade_qty} {trade_symbol} @ ₹{trade_price:,.2f}")
    st.rerun()

if st.button("Simulate SELL"):
    risk_manager.execute_paper_order(trade_symbol, trade_qty, trade_price, "SELL")
    st.warning(f"Sold {trade_qty} {trade_symbol} @ ₹{trade_price:,.2f}")
    st.rerun()

# Minimal polling delay to emulate live refresh.
time.sleep(refresh_seconds)
