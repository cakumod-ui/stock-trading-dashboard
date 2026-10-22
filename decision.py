from typing import Dict, List, Optional, Tuple

from .config import DEFAULT_FUTURE_UNIVERSE, FUTURE_PICK_COUNT, INTRADAY_PICK_COUNT
from .market_scan import safe_float


class DecisionAgent:
    def __init__(self, intraday_pick_count: int = INTRADAY_PICK_COUNT, future_pick_count: int = FUTURE_PICK_COUNT):
        self.intraday_pick_count = intraday_pick_count
        self.future_pick_count = future_pick_count

    def is_bullish_candidate(self, candidate: dict) -> bool:
        quote = candidate.get("quote", {})
        change_pct = safe_float(quote.get("day_change_pct"), 0.0)
        news_score = safe_float(candidate.get("news_score"), 0.0)
        score = candidate.get("score", 0.0)
        return change_pct >= 0 and score > 0 and news_score >= -0.2

    def select_intraday_candidates(self, ranked_candidates: List[dict]) -> List[dict]:
        candidates = [item for item in ranked_candidates if self.is_bullish_candidate(item)]
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[: self.intraday_pick_count]

    def select_future_candidate(self, ranked_candidates: List[dict], future_quote_map: Optional[Dict[str, dict]] = None) -> dict:
        future_quote_map = future_quote_map or {}
        preferred = [item for item in ranked_candidates if item["stock_code"] in DEFAULT_FUTURE_UNIVERSE]
        if not preferred:
            return {}

        preferred.sort(key=lambda item: item["score"], reverse=True)
        best = preferred[0]
        return {
            "stock_code": best["stock_code"],
            "score": best["score"],
            "ltp": best["ltp"],
            "quote": future_quote_map.get(best["stock_code"], best.get("quote", {})),
            "contract_expiry_days": 30,
            "strategy": "FUTURE",
        }

    def choose_daily_plan(self, ranked_candidates: List[dict], future_quote_map: Optional[Dict[str, dict]] = None) -> Tuple[List[dict], dict]:
        intraday = self.select_intraday_candidates(ranked_candidates)
        future = self.select_future_candidate(ranked_candidates, future_quote_map=future_quote_map)
        return intraday, future
