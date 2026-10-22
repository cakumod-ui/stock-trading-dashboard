from dataclasses import dataclass

from .config import (
    DEFAULT_CAPITAL,
    DEFAULT_MAX_DAILY_LOSS,
    DEFAULT_STOPLOSS_PCT,
    DEFAULT_TARGET_PCT,
    MAX_EXPOSURE_PCT,
    MAX_OPEN_POSITIONS,
    MAX_RISK_PER_TRADE_PCT,
)


@dataclass
class TradePlan:
    symbol: str
    strategy: str
    qty: int
    entry_price: float
    stop_loss: float
    target: float
    exchange: str = "NSE"
    product_type: str = "cash"
    action: str = "BUY"

    @staticmethod
    def create(symbol: str, strategy: str, entry_price: float, qty: int):
        return TradePlan(
            symbol=symbol,
            strategy=strategy,
            qty=qty,
            entry_price=entry_price,
            stop_loss=entry_price * (1 - DEFAULT_STOPLOSS_PCT),
            target=entry_price * (1 + DEFAULT_TARGET_PCT),
            exchange="NFO" if strategy == "FUTURE" else "NSE",
            product_type="futures" if strategy == "FUTURE" else "cash",
        )


class RiskManager:
    def __init__(
        self,
        capital: float = DEFAULT_CAPITAL,
        max_daily_loss: float = DEFAULT_MAX_DAILY_LOSS,
        max_risk_per_trade_pct: float = MAX_RISK_PER_TRADE_PCT,
        max_exposure_pct: float = MAX_EXPOSURE_PCT,
        max_open_positions: int = MAX_OPEN_POSITIONS,
    ):
        self.capital = float(capital)
        self.max_daily_loss = float(max_daily_loss)
        self.max_risk_per_trade_pct = float(max_risk_per_trade_pct)
        self.max_exposure_pct = float(max_exposure_pct)
        self.max_open_positions = int(max_open_positions)
        self.realized_pnl = 0.0
        self.open_positions = {}
        self.trades = []

    def trade_value(self, price: float, qty: int) -> float:
        return float(price) * int(qty)

    def validate_trade(self, symbol: str, entry_price: float, qty: int, strategy: str = "INTRADAY") -> tuple[bool, str]:
        trade_value = self.trade_value(entry_price, qty)

        if trade_value <= 0:
            return False, "Trade value must be positive"
        if trade_value > self.capital:
            return False, "Trade value exceeds available capital"
        if trade_value > self.capital * self.max_exposure_pct:
            return False, "Trade exceeds configured max exposure"
        if len(self.open_positions) >= self.max_open_positions:
            return False, "Maximum open positions reached"
        if symbol in self.open_positions:
            return False, "Symbol already in open positions"
        if self.realized_pnl <= -self.max_daily_loss:
            return False, "Daily loss limit reached; trading halted"
        if strategy == "FUTURE" and trade_value > self.capital * 0.10:
            return False, "F&O trade exceeds 10% capital cap"

        return True, "PASS"

    def allocate_quantity(self, symbol: str, entry_price: float, strategy: str = "INTRADAY") -> int:
        if strategy == "FUTURE":
            risk_cap = self.capital * 0.10
        else:
            risk_cap = self.capital * self.max_exposure_pct
        return max(1, int(risk_cap / max(entry_price, 1.0)))

    def apply_execution(self, symbol: str, qty: int, price: float, strategy: str) -> dict:
        trade_value = self.trade_value(price, qty)
        self.capital -= trade_value
        self.open_positions[symbol] = {
            "qty": qty,
            "entry_price": price,
            "strategy": strategy,
            "stop_loss": price * (1 - DEFAULT_STOPLOSS_PCT),
            "target": price * (1 + DEFAULT_TARGET_PCT),
        }
        self.trades.append({"symbol": symbol, "qty": qty, "price": price, "strategy": strategy})
        return {"status": "EXECUTED", "symbol": symbol, "qty": qty, "price": price, "strategy": strategy}

    def apply_exit(self, symbol: str, qty: int, exit_price: float, pnl: float) -> dict:
        self.realized_pnl += pnl
        self.capital += (qty * exit_price)
        self.open_positions.pop(symbol, None)
        return {"status": "EXITED", "symbol": symbol, "qty": qty, "exit_price": exit_price, "pnl": pnl}


class ExecutionAgent:
    def __init__(self, breeze=None, mode: str = "PAPER", risk_manager: RiskManager = None):
        self.breeze = breeze
        self.mode = mode
        self.risk_manager = risk_manager or RiskManager()

    def route_order(self, plan: TradePlan):
        approved, reason = self.risk_manager.validate_trade(plan.symbol, plan.entry_price, plan.qty, plan.strategy)
        if not approved:
            return {"status": "REJECTED", "symbol": plan.symbol, "reason": reason}

        if self.mode == "PAPER":
            return self.risk_manager.apply_execution(plan.symbol, plan.qty, plan.entry_price, plan.strategy)

        try:
            if self.breeze is None:
                raise RuntimeError("Breeze client not configured in LIVE mode")
            result = self.breeze.place_order(
                stock_code=plan.symbol,
                exchange_code=plan.exchange,
                product_type=plan.product_type,
                quantity=plan.qty,
                price=plan.entry_price,
                action=plan.action,
                order_type="BUY",
                validity="DAY",
            )
            return {"status": "LIVE", "symbol": plan.symbol, "result": result}
        except Exception as exc:
            return {"status": "FAILED", "symbol": plan.symbol, "error": str(exc)}

    def exit_order(self, plan: TradePlan, exit_price: float):
        current = self.risk_manager.open_positions.get(plan.symbol)
        if current is None:
            return {"status": "SKIPPED", "symbol": plan.symbol, "reason": "No open position"}

        qty = current["qty"]
        pnl = (exit_price - current["entry_price"]) * qty
        if self.mode == "PAPER":
            return self.risk_manager.apply_exit(plan.symbol, qty, exit_price, pnl)

        try:
            if self.breeze is None:
                raise RuntimeError("Breeze client not configured in LIVE mode")
            result = self.breeze.place_order(
                stock_code=plan.symbol,
                exchange_code=plan.exchange,
                product_type=plan.product_type,
                quantity=qty,
                action="SELL",
                order_type="SELL",
                validity="DAY",
            )
            self.risk_manager.apply_exit(plan.symbol, qty, exit_price, pnl)
            return {"status": "LIVE_EXIT", "symbol": plan.symbol, "result": result}
        except Exception as exc:
            return {"status": "FAILED_EXIT", "symbol": plan.symbol, "error": str(exc)}

    def should_exit(self, plan: TradePlan, current_price: float) -> str:
        if current_price <= plan.stop_loss:
            return "STOP_LOSS"
        if current_price >= plan.target:
            return "TARGET"
        return "HOLD"
