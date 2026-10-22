import csv
import os
from datetime import time as dtime
from typing import List, Set

DEFAULT_NSE_UNIVERSE = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC",
    "LTIM", "HCLTECH", "WIPRO", "TATAMOTORS", "AXISBANK", "KOTAKBANK",
    "BAJFINANCE", "SUNPHARMA", "NTPC", "POWERGRID", "ULTRACEMCO",
    "ASIANPAINT", "M&M", "JSWSTEEL", "TATASTEEL", "BHARTIARTL",
    "TECHM", "MARUTI", "INDUSINDBK", "NESTLEIND", "ONGC", "HEROMOTOCO",
    "GRASIM", "CIPLA", "DRREDDY", "IOC", "TITAN", "HINDUNILVR",
    "BRITANNIA", "APOLLOHOSP", "EICHERMOT", "LT", "SHREECEM", "DIVISLAB",
    "BAJAJ-AUTO", "HINDALCO", "ICICIPRULI", "UPL", "TATACONSUM",
    "COALINDIA", "BEL", "GAIL", "VEDL", "BPCL", "CANBK", "IDFCFIRSTB",
    "SIEMENS", "ADANIGREEN", "ADANIPORTS", "INDIGO", "ZOMATO", "TRENT",
    "PAYTM", "SBI", "PNB", "YESBANK", "BANKBARODA", "AUBANK"
]

DEFAULT_FUTURE_UNIVERSE = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN",
    "ITC", "TATAMOTORS", "LTIM", "AXISBANK", "KOTAKBANK",
    "BAJFINANCE", "SUNPHARMA", "ASIANPAINT", "TATASTEEL", "MARUTI"
]

NEWS_KEYWORDS = {
    "positive": [
        "growth", "profit", "surge", "recovery", "expansion", "dividend",
        "deal", "win", "momentum", "demand", "upgrade", "outperformance"
    ],
    "negative": [
        "decline", "loss", "fine", "penalty", "headwind", "uncertainty",
        "drop", "cut", "pressure", "weakness", "downgrade", "risk"
    ],
}

MARKET_OPEN_IST = dtime(9, 20)
DECISION_TIME_IST = dtime(9, 30)

DEFAULT_CAPITAL = float(os.getenv("TRADING_CAPITAL", "100000"))
DEFAULT_STOPLOSS_PCT = float(os.getenv("STOPLOSS_PCT", "0.010"))
DEFAULT_TARGET_PCT = float(os.getenv("TARGET_PCT", "0.022"))
DEFAULT_MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "1500"))
MAX_EXPOSURE_PCT = float(os.getenv("MAX_EXPOSURE_PCT", "0.30"))
MAX_RISK_PER_TRADE_PCT = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "0.10"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
INTRADAY_PICK_COUNT = int(os.getenv("INTRADAY_PICK_COUNT", "2"))
FUTURE_PICK_COUNT = int(os.getenv("FUTURE_PICK_COUNT", "1"))

CASH_UNIVERSE_PATH = os.getenv("CASH_UNIVERSE_PATH", "data/cash_universe.csv")
FO_UNIVERSE_PATH = os.getenv("FO_UNIVERSE_PATH", "data/fo_universe.csv")

def load_csv_symbols(path: str) -> List[str]:
    if not path or not os.path.exists(path):
        return []
    symbols: Set[str] = set()
    try:
        with open(path, "r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                symbol = (row.get("symbol") or "").strip().upper()
                if symbol:
                    symbols.add(symbol)
    except Exception:
        return []
    return sorted(symbols)

def get_cash_universe() -> List[str]:
    symbols = load_csv_symbols(CASH_UNIVERSE_PATH)
    if symbols:
        return symbols
    return list(DEFAULT_NSE_UNIVERSE)

def get_fo_universe() -> List[str]:
    symbols = load_csv_symbols(FO_UNIVERSE_PATH)
    if symbols:
        return symbols
    return list(DEFAULT_FUTURE_UNIVERSE)
