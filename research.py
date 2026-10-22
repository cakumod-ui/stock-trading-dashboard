from typing import Dict, List, Optional

from .config import DEFAULT_NSE_UNIVERSE
from .market_scan import safe_float


class ResearchAgent:
    def __init__(self, candidate_pool=None):
        self.candidate_pool = candidate_pool or DEFAULT_NSE_UNIVERSE

    def evaluate_stock(self, stock_code: str, quote: dict, news: Optional[dict] = None) -> dict:
        quote = quote or {}
        ltp = safe_float(quote.get("ltp"), 0.0)
        change_pct = safe_float(quote.get("day_change_pct"), 0.0)
        volume = safe_float(quote.get("volume"), 0.0)
        previous_close = safe_float(quote.get("previous_close") or quote.get("close"), ltp)

        price_trend = 0.0
        if previous_close > 0:
            price_trend = ((ltp - previous_close) / previous_close) * 100.0

        news_score = 0.0
        if news:
            news_score = safe_float(news.get("sentiment_score"), 0.0)

        score = (
            (change_pct * 4.0)
            + (volume / 1_000_000.0)
            + max(0.0, price_trend * 2.0)
            + max(0.0, news_score)
        )

        return {
            "stock_code": stock_code,
            "ltp": ltp,
            "change_pct": change_pct,
            "volume": volume,
            "news_score": news_score,
            "score": score,
            "quote": quote,
            "news": news or {},
        }

    def rank_candidates(self, quote_map: Dict[str, dict], news_map: Optional[dict] = None, active_positions=None) -> List[dict]:
        active_positions = active_positions or set()
        news_map = news_map or {}

        ranked = []
        for stock in self.candidate_pool:
            if stock in active_positions:
                continue
            quote = quote_map.get(stock)
            if not quote:
                continue
            ranked.append(self.evaluate_stock(stock, quote, news_map.get(stock)))

        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked
