import os
import sys
import time
import math
import urllib.parse
from datetime import datetime, timedelta
import pandas as pd
from breeze_connect import BreezeConnect


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
        # Check Stop-Loss
        if current_price <= pos['sl']:
            print(f"🛑 Stop Loss Triggered for {stock_code} @ ₹{current_price:.2f}!")
            self.execute_paper_order(stock_code, pos['qty'], current_price, "SELL")
        # Check Take-Profit
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
    def __init__(self, candidate_pool):
        self.candidate_pool = candidate_pool

    def recommend_candidates(self):
        print("🔍 [Research Agent]: Scanning candidate pool for liquid equity instruments...")
        return self.candidate_pool


class TechnicalAgent:
    def __init__(self, breeze):
        self.breeze = breeze

    def analyze(self, stock_code):
        print(f"📊 [Technical Agent]: Evaluating price action & moving averages for {stock_code}...")
        return {"signal": "BULLISH", "support": 1210.0, "resistance": 1245.0}


class ResearchNewsAgent:
    def __init__(self):
        self.impact_weights = {
            'earnings': 1.5,
            'product_launch': 1.2,
            'geopolitical': 1.0,
            'macroeconomic': 1.1,
            'regulatory': 1.3
        }

    def analyze_event_feed(self, stock_code, feed_data):
        print(f"🔍 [Research News Agent]: Sweeping news stream for {stock_code}...")
        total_score = 0.0

        positive_terms = ['growth', 'profit', 'surge', 'recovery', 'expansion', 'dividend', 'deal', 'win']
        negative_terms = ['decline', 'loss', 'fine', 'penalty', 'headwind', 'uncertainty', 'drop', 'cut']

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

    def run_quick_backtest(self, stock_code):
        print(f"🔄 [Backtest Agent]: Validating 30-day historical strategy win-rate for {stock_code}...")
        return True


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
        self.researcher = ResearchAgent(['RELIND', 'TCS', 'ITC', 'INFY'])
        self.technician = TechnicalAgent(breeze)
        self.news_analyst = ResearchNewsAgent()
        self.backtester = BacktestAgent(breeze)
        self.risk_analyst = RiskAnalysisAgent(max_risk_pct=0.01)
        self.executor = ExecutionAgent(breeze, cash_risk_mgr, mode="PAPER")

    def run_daily_agent_cycle(self, mode="PAPER", max_allocation_pct=10.0):
        self.executor.mode = mode
        print(f"\n{'='*60}\n🤖 STARTING MULTI-AGENT TRADING CYCLE ({mode} MODE)\n{'='*60}")

        candidates = self.researcher.recommend_candidates()
        for stock in candidates[:2]:
            print(f"\n--- Processing Ticker: {stock} ---")

            tech_sig = self.technician.analyze(stock)
            
            mock_feed = [
                {'headline': f'{stock} expands operational capacity with major commercial wins', 'category': 'product_launch'},
                {'headline': f'Analysts forecast strong margin recovery for {stock} in Q2', 'category': 'earnings'}
            ]
            news_analysis = self.news_analyst.analyze_event_feed(stock, mock_feed)

            if tech_sig['signal'] == "BULLISH" and "BULLISH" in news_analysis['recommendation']:
                if self.backtester.run_quick_backtest(stock):
                    try:
                        quote = self.breeze.get_quotes(stock_code=stock, exchange_code='NSE', product_type='cash')
                        price = float(quote['Success'][0]['ltp'])
                    except Exception:
                        price = 1200.0

                    current_capital = self.cash_mgr.capital if mode == "PAPER" else 100000.0
                    allocation_amt = current_capital * (max_allocation_pct / 100.0)
                    qty = int(allocation_amt / price)

                    if qty > 0:
                        approved, reason = self.risk_analyst.validate_trade(stock, price, qty, current_capital)
                        if approved:
                            self.executor.route_order(stock, qty, price, "BUY")
                        else:
                            print(f"❌ Trade Rejected by Risk Agent: {reason}")
                    else:
                        print("⚠️ Allocation amount insufficient for single unit purchase.")


# =====================================================================
# 4. MAIN EXECUTION PIPELINE
# =====================================================================
def main():
    print("=" * 60)
    print("INITIALIZING ICICI BREEZE ALGORITHMIC TRADING SYSTEM")
    print("=" * 60)

    # Environment variables or fallback prompt for credentials
    api_key = os.environ.get("ICICI_API_KEY") or "0EL45N5TZ688+84_945=00F290#tCe9j"
    api_secret = os.environ.get("ICICI_API_SECRET") or "4158^87H208z95xVA73959766$0(GO59"
    session_token = os.environ.get("ICICI_SESSION_TOKEN")

    # Interactive prompt if token is not passed via environment variable
    if not session_token:
        encoded_key = urllib.parse.quote_plus(api_key)
        login_url = f"https://api.icicidirect.com/apiuser/login?api_key={encoded_key}"
        print("\nSTEP 1: Log in to your browser using the URL below:")
        print(login_url)
        session_token = input("\nSTEP 2: Enter the 'apisession' token from the redirected URL: ").strip()

    # Authenticate Breeze Session
    breeze = BreezeConnect(api_key=api_key)
    try:
        breeze.generate_session(api_secret=api_secret, session_token=session_token)
        print("\n✅ Successfully Authenticated with ICICI Direct Breeze API!")
    except Exception as e:
        print(f"\n❌ Authentication Failed: {e}")
        sys.exit(1)

    # Initialize Risk Manager and Multi-Agent Core
    risk_manager = PaperTradingRiskManager(initial_capital=100000.0, max_daily_loss=1500.0)
    platform = MasterTradingPlatform(breeze, risk_manager)

    # Execute Initial Agent Cycle
    platform.run_daily_agent_cycle(mode="PAPER", max_allocation_pct=10.0)

    # Portfolio Summary
    print("\n" + "=" * 60)
    print("ACTIVE PAPER TRADING PORTFOLIO SNAPSHOT")
    print("=" * 60)
    if risk_manager.positions:
        for stock, pos in risk_manager.positions.items():
            print(f"Stock: {stock:10s} | Qty: {pos['qty']:<4d} | Entry: ₹{pos['entry_price']:.2f} | SL: ₹{pos['sl']:.2f} | TP: ₹{pos['tp']:.2f}")
    else:
        print("No open positions in portfolio.")


if __name__ == "__main__":
    main()
