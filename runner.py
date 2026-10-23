import argparse
import os
import time
from datetime import datetime

from auth import BreezeSessionManager
from config import DEFAULT_FUTURE_UNIVERSE, DEFAULT_NSE_UNIVERSE, DECISION_TIME_IST, MARKET_OPEN_IST
from config import get_cash_universe, get_fo_universe
from decision import DecisionAgent
from execution import ExecutionAgent, RiskManager, TradePlan
from market_scan import scan_market
from research import ResearchAgent


def wait_until_time(target_hour: int, target_minute: int, sleep_seconds: int = 5):
    while True:
        now = datetime.now()
        if now.hour > target_hour or (now.hour == target_hour and now.minute >= target_minute):
            break
        time.sleep(sleep_seconds)


def run_daily_cycle(mode: str = "PAPER"):
    mode = (mode or "PAPER").upper()
    breeze = None
    if mode == "LIVE":
        session_manager = BreezeSessionManager()
        breeze = session_manager.get_client()

    wait_until_time(MARKET_OPEN_IST.hour, MARKET_OPEN_IST.minute)

    cash_symbols = get_cash_universe()
    fo_symbols = get_fo_universe()

    market_data = scan_market(breeze, cash_symbols, fo_symbols)

    research = ResearchAgent(cash_symbols)
    ranked_candidates = research.rank_candidates(market_data["quotes"], market_data["news"])

    decision = DecisionAgent()
    intraday_candidates, future_candidate = decision.choose_daily_plan(ranked_candidates, future_quote_map=market_data["futures"])

    risk_manager = RiskManager()
    execution_agent = ExecutionAgent(breeze=breeze, mode=mode, risk_manager=risk_manager)
    trade_results = []

    for candidate in intraday_candidates[:2]:
        quote = candidate.get("quote", {})
        ltp = float(quote.get("ltp") or 0.0)
        if ltp <= 0:
            continue
        qty = risk_manager.allocate_quantity(candidate["stock_code"], ltp, strategy="INTRADAY")
        plan = TradePlan.create(candidate["stock_code"], "INTRADAY", ltp, qty)
        result = execution_agent.route_order(plan)
        trade_results.append({"symbol": candidate["stock_code"], "plan": plan, "result": result})

    if future_candidate:
        ltp = float(future_candidate.get("ltp") or 0.0)
        if ltp > 0:
            qty = risk_manager.allocate_quantity(future_candidate["stock_code"], ltp, strategy="FUTURE")
            plan = TradePlan.create(future_candidate["stock_code"], "FUTURE", ltp, qty)
            result = execution_agent.route_order(plan)
            trade_results.append({"symbol": future_candidate["stock_code"], "plan": plan, "result": result})

    return {
        "mode": mode,
        "market_data": market_data,
        "ranked_candidates": ranked_candidates,
        "intraday_candidates": intraday_candidates,
        "future_candidate": future_candidate,
        "trade_results": trade_results,
        "risk_manager": risk_manager,
    }


def main():
    parser = argparse.ArgumentParser(description="Run ICICI trading agents with strict paper/live risk gating.")
    parser.add_argument("--mode", choices=["PAPER", "LIVE"], default=os.getenv("TRADING_MODE", "PAPER").upper())
    args = parser.parse_args()

    print("[tradingagents] Starting ICICI market-open cycle")
    result = run_daily_cycle(mode=args.mode)
    print("[tradingagents] Mode:", result["mode"])
    print("[tradingagents] Intraday picks:")
    for item in result["intraday_candidates"]:
        print("  -", item["stock_code"], "score=", round(item["score"], 4))
    if result["future_candidate"]:
        print("[tradingagents] Future pick:", result["future_candidate"]["stock_code"], "score=", round(result["future_candidate"]["score"], 4))
    print("[tradingagents] Trade results:")
    for item in result["trade_results"]:
        print("  -", item["symbol"], item["result"])


if __name__ == "__main__":
    main()
