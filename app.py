import hashlib
import os
import sqlite3
import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from breeze_connect import BreezeConnect

DB_PATH = "paper_trading.db"
DEFAULT_CASH = 100000.0
DEMO_USERNAME = "demo_user"
DEMO_PASSWORD = "demo_pass"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            cash_balance REAL NOT NULL DEFAULT 100000.0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            executed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            avg_price REAL NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, symbol),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def ensure_demo_user():
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (DEMO_USERNAME,)).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, cash_balance) VALUES (?, ?, ?)",
            (DEMO_USERNAME, hash_password(DEMO_PASSWORD), DEFAULT_CASH),
        )
        user_id = conn.execute("SELECT id FROM users WHERE username = ?", (DEMO_USERNAME,)).fetchone()["id"]

        seed_trades = [
            (user_id, "TCS", "BUY", 20, 3800.0),
            (user_id, "INFY", "BUY", 25, 1450.0),
            (user_id, "ITC", "BUY", 80, 450.0),
        ]
        conn.executemany(
            "INSERT INTO trades (user_id, symbol, side, quantity, price) VALUES (?, ?, ?, ?, ?)",
            seed_trades,
        )
        conn.commit()
    conn.close()


def login_user(username: str, password: str):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password_hash = ?",
        (username, hash_password(password)),
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def rebuild_positions_for_user(user_id: int):
    conn = get_db_connection()
    trades = conn.execute(
        "SELECT symbol, side, quantity, price FROM trades WHERE user_id = ? ORDER BY executed_at ASC",
        (user_id,),
    ).fetchall()

    position_map = {}
    for trade in trades:
        symbol = trade["symbol"]
        side = trade["side"]
        qty = int(trade["quantity"])
        price = float(trade["price"])

        if symbol not in position_map:
            position_map[symbol] = {"qty": 0, "cost": 0.0}

        if side == "BUY":
            position_map[symbol]["qty"] += qty
            position_map[symbol]["cost"] += qty * price
        else:
            position_map[symbol]["qty"] -= qty
            position_map[symbol]["cost"] = max(0.0, position_map[symbol]["cost"] - (qty * price))

    conn.execute("DELETE FROM positions WHERE user_id = ?", (user_id,))
    for symbol, payload in position_map.items():
        qty = payload["qty"]
        if qty <= 0:
            continue
        avg_price = payload["cost"] / qty if payload["cost"] else 0.0
        conn.execute(
            "INSERT INTO positions (user_id, symbol, quantity, avg_price, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, symbol, qty, avg_price, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
        )

    conn.commit()
    conn.close()


def update_cash_balance_for_trade(user_id: int, side: str, quantity: int, price: float):
    conn = get_db_connection()
    user = conn.execute("SELECT cash_balance FROM users WHERE id = ?", (user_id,)).fetchone()
    current_cash = float(user["cash_balance"]) if user else DEFAULT_CASH
    delta = float(quantity) * float(price)
    if side == "BUY":
        new_cash = current_cash - delta
    else:
        new_cash = current_cash + delta
    conn.execute("UPDATE users SET cash_balance = ? WHERE id = ?", (new_cash, user_id))
    conn.commit()
    conn.close()


def record_trade(user_id: int, symbol: str, side: str, quantity: int, price: float):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO trades (user_id, symbol, side, quantity, price) VALUES (?, ?, ?, ?, ?)",
        (user_id, symbol.upper(), side.upper(), int(quantity), float(price)),
    )
    conn.commit()
    conn.close()
    update_cash_balance_for_trade(user_id, side.upper(), int(quantity), float(price))
    rebuild_positions_for_user(user_id)


def get_user_positions(user_id: int):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT symbol, quantity, avg_price FROM positions WHERE user_id = ? ORDER BY symbol ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_trade_history(user_id: int, limit: int = 20):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT symbol, side, quantity, price, executed_at FROM trades WHERE user_id = ? ORDER BY executed_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_cash(user_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT cash_balance FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return float(row["cash_balance"]) if row else DEFAULT_CASH


def get_live_market(symbols):
    api_key = os.getenv("ICICI_API_KEY") or ""
    api_secret = os.getenv("ICICI_API_SECRET") or ""
    session_token = os.getenv("ICICI_SESSION_TOKEN") or ""

    if api_key and api_secret and session_token:
        try:
            breeze = BreezeConnect(api_key=api_key)
            breeze.generate_session(api_secret=api_secret, session_token=session_token)
            result = {}
            for symbol in symbols:
                quote = breeze.get_quotes(stock_code=symbol, exchange_code="NSE", product_type="cash")
                ltp = float(quote["Success"][0]["ltp"]) if quote.get("Success") else 0.0
                result[symbol] = ltp
            return result
        except Exception as exc:
            st.warning(f"Using mock market feed because Breeze connection failed: {exc}")

    base_prices = {
        "TCS": 3800.0,
        "INFY": 1450.0,
        "ITC": 450.0,
        "RELIND": 965.0,
        "HDFCBANK": 1635.0,
    }
    market = {}
    for symbol in symbols:
        base = base_prices.get(symbol, 100.0)
        drift = ((hash(symbol) % 31) / 10.0) - 1.0
        market[symbol] = round(base * (1 + drift / 100), 2)
    return market


def compute_dashboard_metrics(user_id: int):
    positions = get_user_positions(user_id)
    cash_balance = get_user_cash(user_id)
    live_prices = get_live_market([item["symbol"] for item in positions] or ["TCS", "INFY", "ITC"])

    portfolio_value = cash_balance
    position_rows = []
    total_unrealized = 0.0

    for item in positions:
        symbol = item["symbol"]
        qty = int(item["quantity"])
        avg_price = float(item["avg_price"])
        ltp = float(live_prices.get(symbol, avg_price))
        current_value = qty * ltp
        pnl = (ltp - avg_price) * qty
        total_unrealized += pnl
        portfolio_value += current_value
        position_rows.append({
            "symbol": symbol,
            "quantity": qty,
            "avg_price": avg_price,
            "ltp": ltp,
            "market_value": current_value,
            "unrealized_pnl": pnl,
        })

    realized_pnl = 0.0
    for trade in get_trade_history(user_id, 1000):
        if trade["side"] == "SELL":
            realized_pnl += float(trade["price"]) * int(trade["quantity"])
        else:
            realized_pnl -= float(trade["price"]) * int(trade["quantity"])

    net_pnl = realized_pnl + total_unrealized
    return {
        "cash_balance": cash_balance,
        "portfolio_value": portfolio_value,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": total_unrealized,
        "net_pnl": net_pnl,
        "positions": position_rows,
        "live_prices": live_prices,
    }


init_db()
ensure_demo_user()

st.set_page_config(page_title="ICICI Paper Trading Dashboard", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🔐 ICICI Paper Trading Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        user = login_user(username, password)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Invalid username or password")

    st.caption("Demo credentials: demo_user / demo_pass")
    st.stop()

user = st.session_state.user
user_id = user["id"]
username = user["username"]

st.title(f"📊 ICICI Paper Trading Dashboard — {username}")

with st.sidebar:
    st.subheader("Controls")
    st.write(f"User: {username}")
    if st.button("Logout"):
        st.session_state.user = None
        st.rerun()
    refresh_seconds = st.slider("Refresh interval (seconds)", 1, 10, 2)
    if st.button("Refresh now"):
        st.rerun()

metrics = compute_dashboard_metrics(user_id)
positions_df = pd.DataFrame(metrics["positions"])
trade_history = get_trade_history(user_id, 10)

if not positions_df.empty:
    positions_df["market_value"] = positions_df["market_value"].round(2)
    positions_df["unrealized_pnl"] = positions_df["unrealized_pnl"].round(2)
    positions_df["ltp"] = positions_df["ltp"].round(2)

kpi_cols = st.columns(5)
with kpi_cols[0]:
    st.metric("Cash Balance", f"₹{metrics['cash_balance']:,.2f}")
with kpi_cols[1]:
    st.metric("Portfolio Value", f"₹{metrics['portfolio_value']:,.2f}")
with kpi_cols[2]:
    st.metric("Realized P&L", f"₹{metrics['realized_pnl']:,.2f}")
with kpi_cols[3]:
    st.metric("Unrealized P&L", f"₹{metrics['unrealized_pnl']:,.2f}")
with kpi_cols[4]:
    st.metric("Net P&L", f"₹{metrics['net_pnl']:,.2f}")

chart_col, side_col = st.columns([2, 1])

with chart_col:
    if not positions_df.empty:
        pnl_fig = go.Figure(
            go.Bar(
                x=positions_df["symbol"],
                y=positions_df["unrealized_pnl"],
                marker_color=["#2ecc71" if v >= 0 else "#e74c3c" for v in positions_df["unrealized_pnl"]],
            )
        )
        pnl_fig.update_layout(title="Unrealized P&L by Position", template="plotly_dark", height=320, xaxis_title="Ticker", yaxis_title="P&L (₹)")
        st.plotly_chart(pnl_fig, use_container_width=True)

    equity_series = [100000.0]
    for _ in range(10):
        equity_series.append(metrics["portfolio_value"])
    eq_df = pd.DataFrame({"step": list(range(len(equity_series))), "value": equity_series})
    equity_fig = go.Figure()
    equity_fig.add_trace(go.Scatter(x=eq_df["step"], y=eq_df["value"], mode="lines+markers", line={"color": "#00C2FF"}, name="Portfolio Value"))
    equity_fig.update_layout(title="Portfolio Equity Trend", template="plotly_dark", height=320, xaxis_title="Sample", yaxis_title="Value (₹)")
    st.plotly_chart(equity_fig, use_container_width=True)

with side_col:
    st.subheader("Open Positions")
    if positions_df.empty:
        st.info("No open positions for this user.")
    else:
        display_positions = positions_df[["symbol", "quantity", "avg_price", "ltp", "market_value", "unrealized_pnl"]].copy()
        display_positions.columns = ["Ticker", "Qty", "Avg Cost", "LTP", "Market Value", "P&L"]
        st.dataframe(display_positions.style.format({
            "Avg Cost": "₹{:.2f}",
            "LTP": "₹{:.2f}",
            "Market Value": "₹{:.2f}",
            "P&L": "₹{:.2f}",
        }), use_container_width=True)

    st.subheader("Live Market Feed")
    if positions_df.empty:
        st.write("No active symbols to quote.")
    else:
        live_df = pd.DataFrame([
            {"symbol": row["symbol"], "ltp": row["ltp"]} for _, row in positions_df.iterrows()
        ])
        st.dataframe(live_df.style.format({"ltp": "₹{:.2f}"}), use_container_width=True)

st.subheader("Quick Trade Entry")
trade_col1, trade_col2, trade_col3 = st.columns(3)
with trade_col1:
    trade_symbol = st.selectbox("Ticker", ["TCS", "INFY", "ITC", "RELIND", "HDFCBANK"])
with trade_col2:
    trade_qty = st.number_input("Quantity", min_value=1, max_value=500, value=10)
with trade_col3:
    price_value = st.number_input("Price", min_value=1.0, max_value=10000.0, value=1000.0, step=1.0)

trade_action_col1, trade_action_col2 = st.columns(2)
with trade_action_col1:
    if st.button("BUY"):
        record_trade(user_id, trade_symbol, "BUY", int(trade_qty), float(price_value))
        st.success(f"BUY order saved: {trade_qty} {trade_symbol} @ ₹{price_value:,.2f}")
        st.rerun()
with trade_action_col2:
    if st.button("SELL"):
        record_trade(user_id, trade_symbol, "SELL", int(trade_qty), float(price_value))
        st.warning(f"SELL order saved: {trade_qty} {trade_symbol} @ ₹{price_value:,.2f}")
        st.rerun()

st.subheader("Recent Trades")
recent_trades = pd.DataFrame(trade_history)
if recent_trades.empty:
    st.info("No trades yet for this user.")
else:
    recent_trades.columns = ["Ticker", "Side", "Qty", "Price", "Executed At"]
    st.dataframe(recent_trades.style.format({"Price": "₹{:.2f}"}), use_container_width=True)

# keep dashboard refresh behavior lightweight
if "refresh_seconds" in locals():
    time.sleep(refresh_seconds)
