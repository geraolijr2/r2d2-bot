from dataclasses import dataclass
from typing import Optional, Literal
from r2d2.utils.logger import get_logger

log = get_logger("position")

Side = Literal["LONG", "SHORT"]

@dataclass
class Position:
    side: Optional[Side] = None
    qty: float = 0.0
    entry: float = 0.0
    stop: float = 0.0
    take: float = 0.0

class PositionManager:
    def __init__(self):
        self.pos = Position()

    def flat(self) -> bool:
        return self.pos.side is None or self.pos.qty <= 0.0

    def open(self, side: Side, qty: float, entry: float, stop: float, take: float):
        self.pos = Position(side=side, qty=qty, entry=entry, stop=stop, take=take)
        log.info(f"Open {side} qty={qty} entry={entry} SL={stop} TP={take}")

    def close(self, price: float) -> float:
        if self.flat():
            return 0.0
        pnl_per_unit = (price - self.pos.entry) if self.pos.side == "LONG" else (self.pos.entry - price)
        pnl = pnl_per_unit * self.pos.qty
        log.info(f"Close {self.pos.side} qty={self.pos.qty} exit={price} PnL={pnl:.2f}")
        self.pos = Position()
        return pnl

    def check_stops(self, price: float) -> Optional[float]:
        if self.flat():
            return None
        if self.pos.side == "LONG":
            if price <= self.pos.stop or price >= self.pos.take:
                return self.close(price)
        else:
            if price >= self.pos.stop or price <= self.pos.take:
                return self.close(price)
        return None

    def move_to_breakeven(self, price: float):
        if self.flat():
            return
        if self.pos.side == "LONG":
            if price > self.pos.entry:
                self.pos.stop = max(self.pos.stop, self.pos.entry)
        else:
            if price < self.pos.entry:
                self.pos.stop = min(self.pos.stop, self.pos.entry)




