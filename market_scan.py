import os
from typing import Dict, Iterable, List
import xml.etree.ElementTree as ET

import requests

from .config import DEFAULT_FUTURE_UNIVERSE, DEFAULT_NSE_UNIVERSE, NEWS_KEYWORDS


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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

    previous_close = item.get("prev_close") or item.get("close") or price
    return {
        "ltp": float(price),
        "day_change": float(change or 0.0),
        "day_change_pct": float(change_pct or 0.0),
        "volume": float(volume or 0.0),
        "day_high": float(item.get("day_high") or 0.0),
        "day_low": float(item.get("day_low") or 0.0),
        "close": float(previous_close),
        "previous_close": float(previous_close),
    }


def fetch_quotes_from_breeze(breeze, symbols: Iterable[str], exchange_code: str = "NSE", product_type: str = "cash") -> Dict[str, dict]:
    quote_map = {}
    for symbol in symbols:
        try:
            payload = breeze.get_quotes(stock_code=symbol, exchange_code=exchange_code, product_type=product_type)
            snapshot = normalize_quote_snapshot(payload)
            if snapshot and safe_float(snapshot.get("ltp"), 0.0) > 0:
                quote_map[symbol] = snapshot
        except Exception:
            continue
    return quote_map


def synthetic_quote(symbol: str) -> dict:
    base = 120.0 + (sum(ord(ch) for ch in symbol) % 3200)
    drift = ((sum(ord(ch) for ch in symbol) % 17) - 8) * 0.55
    volume = 150000 + (sum(ord(ch) for ch in symbol) % 850000)
    return {
        "ltp": round(base, 2),
        "day_change": round(drift, 2),
        "day_change_pct": round((drift / max(base, 1.0)) * 100.0, 2),
        "volume": float(volume),
        "day_high": round(base * 1.02, 2),
        "day_low": round(base * 0.98, 2),
        "close": round(base, 2),
        "previous_close": round(base, 2),
    }


def fetch_news_items(symbol: str) -> List[str]:
    api_key = os.getenv("NEWS_API_KEY")
    if api_key:
        try:
            response = requests.get(
                "https://newsapi.org/v2/everything",
                params={"q": f"{symbol} stock OR {symbol} company", "language": "en", "pageSize": 5, "apiKey": api_key},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
            articles = payload.get("articles", [])
            return [article.get("title", "") for article in articles if article.get("title")]
        except Exception:
            pass

    try:
        response = requests.get(
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}.NS&region=US&lang=en-US",
            timeout=12,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        titles = []
        for item in root.findall(".//item"):
            title = item.findtext("title")
            if title:
                titles.append(title)
        return titles[:5]
    except Exception:
        return []


def sentiment_score_from_news(headlines: List[str]) -> float:
    if not headlines:
        return 0.0

    total = 0.0
    for headline in headlines:
        text = headline.lower()
        positive_hits = sum(1 for word in NEWS_KEYWORDS["positive"] if word in text)
        negative_hits = sum(1 for word in NEWS_KEYWORDS["negative"] if word in text)
        total += (positive_hits - negative_hits)
    return float(total)


def scan_market(breeze=None, stock_symbols=None, future_symbols=None):
    cash_symbols = list(stock_symbols or DEFAULT_NSE_UNIVERSE)
    future_symbols = list(future_symbols or DEFAULT_FUTURE_UNIVERSE)

    quotes = fetch_quotes_from_breeze(breeze, cash_symbols, exchange_code="NSE", product_type="cash") if breeze else {}
    if not quotes:
        quotes = {symbol: synthetic_quote(symbol) for symbol in cash_symbols[:60]}

    futures = fetch_quotes_from_breeze(breeze, future_symbols, exchange_code="NSE", product_type="cash") if breeze else {}
    if not futures:
        futures = {symbol: synthetic_quote(symbol) for symbol in future_symbols[:20]}

    news = {}
    for symbol in cash_symbols:
        headlines = fetch_news_items(symbol)
        news[symbol] = {
            "headlines": headlines,
            "sentiment_score": sentiment_score_from_news(headlines),
        }

    return {"quotes": quotes, "futures": futures, "news": news}
