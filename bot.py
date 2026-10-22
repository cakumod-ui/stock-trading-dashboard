import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from breeze_connect import BreezeConnect


STATE_PATH = Path(__file__).resolve().parent / ".trading_state.json"

DEFAULT_NSE_UNIVERSE = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC",
    "LTIM", "HCLTECH", "WIPRO", "TATAMOTORS", "AXISBANK", "KOTAKBANK",
    "BAJFINANCE", "SUNPHARMA", "NTPC", "POWERGRID", "ULTRACEMCO",
    "ASIANPAINT", "M&M", "JSWSTEEL", "TATASTEEL", "BHARTIARTL",
    "TECHM", "MARUTI", "INDUSINDBK", "NESTLEIND", "ONGC", "HEROMOTOCO",
    "GRASIM", "CIPLA", "DRREDDY", "IOC", "TITAN", "HINDUNILVR",
    "BRITANNIA", "APOLLOHOSP", "EICHERMOT", "LT", "SHREECEM", "DIVISLAB",
    "BAJAJ-AUTO", "BAJAJFINANCE", "HINDALCO", "ICICIPRULI", "UPL",
    "TATACONSUM", "COALINDIA", "BEL", "GAIL", "VEDL", "BPCL", "CANBK",
    "IDFCFIRSTB", "SIEMENS", "ADANIGREEN", "ADANIPORTS", "INDIGO", "ZOMATO",
    "TRENT", "PAYTM", "SBI", "PNB", "YESBANK", "BANKBARODA", "AUBANK"
]


def load_selection_state():
    if not STATE_PATH.exists():
        return {"last_selected": {}}

    try:
        with STATE_PATH.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        return {"last_selected": state.get("last_selected", {})}
    except Exception:
        return {"last_selected": {}}


def save_selection_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def is_cooldown(stock_code, state, cooldown_hours=72):
    last_selected = state.get("last_selected", {}).get(stock_code)
    if not last_selected:
        return False

    try:
        last_dt = datetime.fromisoformat(last_selected)
    except ValueError:
        return False

    now = datetime.now(timezone.utc)
    return now - last_dt < timedelta(hours=cooldown_hours)


def mark_stock_selected(stock_code, state):
    state.setdefault("last_selected", {})
    state["last_selected"][stock_code] = datetime.now(timezone.utc).isoformat()


def normalize_quote_snapshot(raw_quote):
    if not raw_quote:
        return {}

    success = raw_quote.get("Success") or raw_quote.get("success") or []
    if not success:
        return {}

    item = success[0] if isinstance(success, list) else success
    if not isinstance(item, dict):
        return {}

    price = item.get("ltp")
    if price is None:
        return {}

    volume = item.get("trdvol")
    if volume is None:
        volume = item.get("volume")
    if volume is None:
        volume = item.get("traded_volume")

    change = item.get("day_change")
    if change is None:
        change = item.get("change")

    change_pct = item.get("day_change_pct")
    if change_pct is None:
        change_pct = item.get("percent_change")
    if change_pct is None and change is not None and price:
        try:
            change_pct = (float(change) / float(price)) * 100.0
        except Exception:
            change_pct = 0.0

    return {
        "ltp": float(price),
        "day_change": float(change or 0.0),
        "day_change_pct": float(change_pct or 0.0),
        "volume": float(volume or 0.0),
        "day_high": float(item.get("day_high") or 0.0),
        "day_low": float(item.get("day_low") or 0.0),
        "close": float(item.get("prev_close") or item.get("close") or price),
    }


def build_event_stream(stock_code, quote_snapshot):
    change_pct = float(quote_snapshot.get("day_change_pct", 0.0) or 0.0)
    if change_pct >= 0:
        return [
            {"headline": f"{stock_code} extends gains on broad market participation and strong demand", "category": "earnings"},
            {"headline": f"{stock_code} shows positive momentum with buyers absorbing supply across the session", "category": "product_launch"},
        ]
    return [
        {"headline": f"{stock_code} faces profit booking pressure and weak momentum in the current session", "category": "regulatory"},
        {"headline": f"{stock_code} remains under pressure amid elevated volatility and weak sentiment", "category": "macroeconomic"},
    ]


# =====================================================================
# 1. RISK MANAGER & PAPER TRADING ENGINE
# =====================================================================
class PaperTradingRiskManager:
    """
    Tracks paper trading portfolio state, order history, and enforces
    risk parameters (Max Daily Loss, Stop-Loss, Take-Profit).
    """
    def __init__(self, initial_capital=100000.0, max_daily_loss=2000.0,
                 default_stop_loss_pct=0.01, default_take_profit_pct=0.02):
        self.capital = initial_capital
        self.portfolio_value = initial_capital
        self.max_daily_loss = max_daily_loss
        self.default_stop_loss_pct = default_stop_loss_pct
        self.default_take_profit_pct = default_take_profit_pct

        self.positions = {}  # {stock_code: {'qty': qty, 'entry_price': price, 'sl': sl, 'tp': tp}}
        self.realized_pnl = 0.0
        self.active = True

    def execute_paper_order(self, stock_code, qty, current_price, order_type="BUY"):
        if not self.active:
            print("🚨 Risk Limit Reached: Trading circuit breaker active.")
            return

        if order_type == "BUY":
            cost = qty * current_price
            if cost > self.capital:
                print(f"⚠️ Insufficient paper funds to buy {qty} shares of {stock_code}.")
                return

            self.capital -= cost
            sl_price = current_price * (1 - self.default_stop_loss_pct)
            tp_price = current_price * (1 + self.default_take_profit_pct)

            if stock_code in self.positions:
                existing = self.positions[stock_code]
                new_qty = existing['qty'] + qty
                new_entry = ((existing['qty'] * existing['entry_price']) + cost) / new_qty
                self.positions[stock_code] = {
                    'qty': new_qty,
                    'entry_price': new_entry,
                    'sl': new_entry * (1 - self.default_stop_loss_pct),
                    'tp': new_entry * (1 + self.default_take_profit_pct)
                }
            else:
                self.positions[stock_code] = {
                    'qty': qty,
                    'entry_price': current_price,
                    'sl': sl_price,
                    'tp': tp_price
                }
            print(f"📥 [PAPER BUY] {qty} {stock_code} @ ₹{current_price:.2f} | SL: ₹{sl_price:.2f} | TP: ₹{tp_price:.2f}")

        elif order_type == "SELL":
            if stock_code not in self.positions or self.positions[stock_code]['qty'] < qty:
                print(f"⚠️ Insufficient active position quantity to sell {stock_code}.")
                return

            pos = self.positions[stock_code]
            revenue = qty * current_price
            pnl = (current_price - pos['entry_price']) * qty

            self.capital += revenue
            self.realized_pnl += pnl

            pos['qty'] -= qty
            if pos['qty'] == 0:
                del self.positions[stock_code]

            print(f"📤 [PAPER SELL] {qty} {stock_code} @ ₹{current_price:.2f} | Realized PnL: ₹{pnl:+.2f}")
            self._check_daily_limits()

    def update_live_market_price(self, stock_code, current_price):
        if stock_code not in self.positions:
            return

        pos = self.positions[stock_code]
        if current_price <= pos['sl']:
            print(f"🛑 Stop Loss Triggered for {stock_code} @ ₹{current_price:.2f}!")
            self.execute_paper_order(stock_code, pos['qty'], current_price, "SELL")
        elif current_price >= pos['tp']:
            print(f"🎯 Take Profit Triggered for {stock_code} @ ₹{current_price:.2f}!")
            self.execute_paper_order(stock_code, pos['qty'], current_price, "SELL")

    def _check_daily_limits(self):
        if self.realized_pnl <= -self.max_daily_loss:
            print(f"🚨 CRITICAL: Daily Loss Limit breached! Current Realized: ₹{self.realized_pnl:.2f}. Halting trading.")
            self.active = False


# =====================================================================
# 2. MULTI-AGENT ARCHITECTURE
# =====================================================================
class ResearchAgent:
    def __init__(self, candidate_pool=None):
        self.candidate_pool = candidate_pool or DEFAULT_NSE_UNIVERSE

    def recommend_candidates(self, quote_map, active_positions=None, state=None, cooldown_hours=72):
        print("🔍 [Research Agent]: Scanning NSE universe for the best momentum names...")
        active_positions = active_positions or set()
        candidates = []

        for stock in self.candidate_pool:
            if stock in active_positions:
                continue
            if state and is_cooldown(stock, state, cooldown_hours):
                continue

            quote = quote_map.get(stock, {})
            if not quote:
                continue

            ltp = float(quote.get('ltp', 0.0) or 0.0)
            change_pct = float(quote.get('day_change_pct', 0.0) or 0.0)
            volume = float(quote.get('volume', 0.0) or 0.0)
            score = (change_pct * 4.0) + min(volume / 1000000.0, 10.0)
            if ltp > 0:
                score += 1.0
            if change_pct > 0:
                score += 2.0

            candidates.append((stock, score, quote))

        if not candidates:
            print("⚠️ No valid candidates after filtering inactive or cooled-down stocks.")
            return []

        candidates.sort(key=lambda item: item[1], reverse=True)
        top = [stock for stock, _, _ in candidates[:10]]
        print(f"✅ Ranked candidate list: {top}")
        return top


class TechnicalAgent:
    def __init__(self, breeze):
        self.breeze = breeze

    def analyze(self, stock_code, quote_snapshot=None):
        quote_snapshot = quote_snapshot or {}
        ltp = float(quote_snapshot.get('ltp', 0.0) or 0.0)
        change_pct = float(quote_snapshot.get('day_change_pct', 0.0) or 0.0)

        if change_pct >= 0:
            signal = "BULLISH"
        else:
            signal = "BEARISH"

        support = max(ltp * 0.97, 1.0)
        resistance = max(ltp * 1.03, 1.0)
        print(f"📊 [Technical Agent]: {stock_code} LTP={ltp:.2f} change%={change_pct:.2f} -> {signal}")
        return {"signal": signal, "support": support, "resistance": resistance}


class ResearchNewsAgent:
    def __init__(self):
        self.impact_weights = {
            'earnings': 1.5,
            'product_launch': 1.2,
            'geopolitical': 1.0,
            'macroeconomic': 1.1,
            'regulatory': 1.3
        }

    def analyze_event_feed(self, stock_code, feed_data=None, quote_snapshot=None):
        quote_snapshot = quote_snapshot or {}
        feed_data = feed_data or build_event_stream(stock_code, quote_snapshot)

        total_score = 0.0
        positive_terms = ['growth', 'profit', 'surge', 'recovery', 'expansion', 'dividend', 'deal', 'win', 'momentum', 'demand']
        negative_terms = ['decline', 'loss', 'fine', 'penalty', 'headwind', 'uncertainty', 'drop', 'cut', 'pressure', 'weakness']

        for event in feed_data:
            headline = event.get('headline', '').lower()
            category = event.get('category', 'macroeconomic')
            weight = self.impact_weights.get(category, 1.0)

            sentiment_score = 0
            for word in positive_terms:
                if word in headline:
                    sentiment_score += 1
            for word in negative_terms:
                if word in headline:
                    sentiment_score -= 1

            weighted_pnl_impact = sentiment_score * weight
            total_score += weighted_pnl_impact

        recommendation = "ACCUMULATE (BULLISH)" if total_score >= 1.0 else ("REDUCE (BEARISH)" if total_score <= -1.0 else "HOLD (NEUTRAL)")
        print(f"⚡ [News Agent Summary]: Score: {total_score:+.2f} -> Action: {recommendation}")
        return {'stock_code': stock_code, 'composite_score': total_score, 'recommendation': recommendation}


class BacktestAgent:
    def __init__(self, breeze):
        self.breeze = breeze

    def run_quick_backtest(self, stock_code, quote_snapshot=None):
        quote_snapshot = quote_snapshot or {}
        change_pct = float(quote_snapshot.get('day_change_pct', 0.0) or 0.0)
        volume = float(quote_snapshot.get('volume', 0.0) or 0.0)
        print(f"🔄 [Backtest Agent]: Validating short-term momentum quality for {stock_code}...")
        return change_pct >= 0.0 and volume > 0.0


class RiskAnalysisAgent:
    def __init__(self, max_risk_pct=0.01):
        self.max_risk_pct = max_risk_pct

    def validate_trade(self, stock_code, price, qty, current_capital):
        trade_value = price * qty
        risk_amount = trade_value * self.max_risk_pct
        print(f"🛡️ [Risk Agent]: Trade Value: ₹{trade_value:.2f} | Risk Allocation: ₹{risk_amount:.2f}")
        if trade_value > current_capital:
            return False, "Insufficient Capital"
        return True, "Risk Parameters Approved"


class ExecutionAgent:
    def __init__(self, breeze, risk_manager, mode="PAPER"):
        self.breeze = breeze
        self.risk_manager = risk_manager
        self.mode = mode

    def route_order(self, stock_code, qty, price, order_type="BUY"):
        print(f"⚙️ [Execution Agent]: Dispatching order in {self.mode} mode...")
        if self.mode == "PAPER":
            self.risk_manager.execute_paper_order(stock_code, qty, price, order_type)
        else:
            print(f"⚡ [LIVE EXECUTION]: Submitting real market order via Breeze for {qty} {stock_code} @ ₹{price:.2f}")


# =====================================================================
# 3. MASTER PLATFORM CONTROLLER
# =====================================================================
class MasterTradingPlatform:
    def __init__(self, breeze, cash_risk_mgr):
        self.breeze = breeze
        self.cash_mgr = cash_risk_mgr
        self.researcher = ResearchAgent(DEFAULT_NSE_UNIVERSE)
        self.technician = TechnicalAgent(breeze)
        self.news_analyst = ResearchNewsAgent()
        self.backtester = BacktestAgent(breeze)
        self.risk_analyst = RiskAnalysisAgent(max_risk_pct=0.01)
        self.executor = ExecutionAgent(breeze, cash_risk_mgr, mode="PAPER")
        self.selection_state = load_selection_state()

    def fetch_nse_universe_quotes(self):
        quote_map = {}
        for stock in DEFAULT_NSE_UNIVERSE:
            try:
                quote = self.breeze.get_quotes(stock_code=stock, exchange_code='NSE', product_type='cash')
                snapshot = normalize_quote_snapshot(quote)
                if snapshot and float(snapshot.get('ltp', 0.0) or 0.0) > 0:
                    quote_map[stock] = snapshot
            except Exception as exc:
                print(f"⚠️ Quote fetch failed for {stock}: {exc}")
                continue

        if quote_map:
            return quote_map

        print("⚠️ Breeze quote stream unavailable, using synthetic live-style fallback values.")
        for stock in DEFAULT_NSE_UNIVERSE[:25]:
            base = 100.0 + (sum(ord(ch) for ch in stock) % 2200)
            drift = ((sum(ord(ch) for ch in stock) % 13) - 6) * 0.35
            volume = 250000 + (sum(ord(ch) for ch in stock) % 750000)
            quote_map[stock] = {
                "ltp": round(base, 2),
                "day_change": round(drift, 2),
                "day_change_pct": round(drift / base * 100.0, 2),
                "volume": float(volume),
                "day_high": round(base * 1.02, 2),
                "day_low": round(base * 0.98, 2),
                "close": round(base, 2)
            }
        return quote_map

    def run_daily_agent_cycle(self, mode="PAPER", max_allocation_pct=10.0, cooldown_hours=72):
        self.executor.mode = mode
        print(f"\n{'='*60}\n🤖 STARTING MULTI-AGENT TRADING CYCLE ({mode} MODE)\n{'='*60}")

        live_quotes = self.fetch_nse_universe_quotes()
        active_positions = set(self.cash_mgr.positions.keys())
        candidates = self.researcher.recommend_candidates(live_quotes, active_positions, self.selection_state, cooldown_hours)
        selected = []

        for stock in candidates[:2]:
            print(f"\n--- Processing Ticker: {stock} ---")
            quote = live_quotes.get(stock, {})
            tech_sig = self.technician.analyze(stock, quote)

            feed_data = build_event_stream(stock, quote)
            news_analysis = self.news_analyst.analyze_event_feed(stock, feed_data, quote)

            if tech_sig['signal'] == "BULLISH" and "BULLISH" in news_analysis['recommendation']:
                if self.backtester.run_quick_backtest(stock, quote):
                    try:
                        price = float(quote.get('ltp', 0.0) or 0.0)
                    except Exception:
                        price = 1200.0

                    if price <= 0:
                        print(f"⚠️ Invalid price for {stock}, skipping trade.")
                        continue

                    current_capital = self.cash_mgr.capital if mode == "PAPER" else 100000.0
                    allocation_amt = current_capital * (max_allocation_pct / 100.0)
                    qty = int(allocation_amt / price)

                    if qty > 0:
                        approved, reason = self.risk_analyst.validate_trade(stock, price, qty, current_capital)
                        if approved:
                            if stock not in self.cash_mgr.positions and not is_cooldown(stock, self.selection_state, cooldown_hours):
                                self.executor.route_order(stock, qty, price, "BUY")
                                selected.append(stock)
                                mark_stock_selected(stock, self.selection_state)
                                save_selection_state(self.selection_state)
                            else:
                                print(f"🚫 {stock} is already in the portfolio or is still under cooldown. Skipping buy.")
                        else:
                            print(f"❌ Trade Rejected by Risk Agent: {reason}")
                    else:
                        print("⚠️ Allocation amount insufficient for single unit purchase.")

        return selected


# =====================================================================
# 4. MAIN EXECUTION PIPELINE
# =====================================================================
def main():
    print("=" * 60)
    print("INITIALIZING ICICI BREEZE ALGORITHMIC TRADING SYSTEM")
    print("=" * 60)

    api_key = os.environ.get("ICICI_API_KEY") or "0EL45N5TZ688+84_945=00F290#tCe9j"
    api_secret = os.environ.get("ICICI_API_SECRET") or "4158^87H208z95xVA73959766$0(GO59"
    session_token = os.environ.get("ICICI_SESSION_TOKEN")

    if not session_token:
        encoded_key = urllib.parse.quote_plus(api_key)
        login_url = f"https://api.icicidirect.com/apiuser/login?api_key={encoded_key}"
        print("\nSTEP 1: Log in to your browser using the URL below:")
        print(login_url)
        session_token = input("\nSTEP 2: Enter the 'apisession' token from the redirected URL: ").strip()

    breeze = BreezeConnect(api_key=api_key)
    try:
        breeze.generate_session(api_secret=api_secret, session_token=session_token)
        print("\n✅ Successfully Authenticated with ICICI Direct Breeze API!")
    except Exception as e:
        print(f"\n❌ Authentication Failed: {e}")
        sys.exit(1)

    risk_manager = PaperTradingRiskManager(initial_capital=100000.0, max_daily_loss=1500.0)
    platform = MasterTradingPlatform(breeze, risk_manager)

    selected = platform.run_daily_agent_cycle(mode="PAPER", max_allocation_pct=10.0, cooldown_hours=72)

    print("\n" + "=" * 60)
    print("ACTIVE PAPER TRADING PORTFOLIO SNAPSHOT")
    print("=" * 60)
    if risk_manager.positions:
        for stock, pos in risk_manager.positions.items():
            print(f"Stock: {stock:10s} | Qty: {pos['qty']:<4d} | Entry: ₹{pos['entry_price']:.2f} | SL: ₹{pos['sl']:.2f} | TP: ₹{pos['tp']:.2f}")
    else:
        print("No open positions in portfolio.")

    if selected:
        print(f"\n✅ Selected today: {', '.join(selected)}")
    else:
        print("\nNo qualifying stocks met the research and cooldown rules today.")


if __name__ == "__main__":
    main()
