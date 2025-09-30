from dataclasses import dataclass
from typing import Optional
from r2d2.config import RiskConfig
from r2d2.utils.logger import get_logger

log = get_logger("risk")

@dataclass
class DayState:
    starting_equity: float
    max_intraday_drawdown: float = 0.0
    trades_count: int = 0
    day_closed: bool = False

class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self.day: Optional[DayState] = None

    def start_day(self, equity: float):
        self.day = DayState(starting_equity=equity)
        log.info(f"RiskManager: início do dia | equity={equity:.2f}")

    def can_trade(self) -> bool:
        if self.day is None or self.day.day_closed:
            return False
        if self.day.trades_count >= self.cfg.max_trades_per_day:
            return False
        if self.day.max_intraday_drawdown >= self.cfg.max_daily_loss_money:
            return False
        return True

    def register_trade(self, pnl: float):
        if self.day is None:
            return
        self.day.trades_count += 1
        if pnl < 0:
            self.day.max_intraday_drawdown += abs(pnl)
        if self.day.max_intraday_drawdown >= self.cfg.max_daily_loss_money:
            self.day.day_closed = True
            log.warning("RiskManager: limite diário atingido, encerrando negociações.")

    def size_from_risk(self, price: float, stop_points: float,
                       equity: float, point_value: float) -> float:
        if stop_points <= 0:
            return self.cfg.fixed_lots
        capital = equity if self.cfg.use_equity_for_risk else self.day.starting_equity
        risk_money = capital * (self.cfg.risk_per_trade_pct / 100.0)
        qty = risk_money / (stop_points * point_value)
        if self.cfg.lot_per_money and self.cfg.lot_per_money > 0:
            qty_by_money = max(1.0, capital / self.cfg.lot_per_money)
            qty = min(qty, qty_by_money)
        return max(0.01, round(qty, 3))
