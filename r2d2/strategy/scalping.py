from typing import Dict, Any, List
from .base_strategy import BaseStrategy, Signal

class ScalpingStrategy(BaseStrategy):
    def __init__(self, params: Dict[str, Any]):
        super().__init__(params)
        self.buffer: Dict[str, List[float]] = {"close": []}

    def on_bar(self, bar: Dict[str, float], ctx: Dict[str, Any]) -> str:
        self.buffer["close"].append(bar["close"])
        if len(self.buffer["close"]) < 5:
            return Signal.NONE

        c = self.buffer["close"][-1]
        p1 = self.buffer["close"][-2]
        p2 = self.buffer["close"][-3]

        if c > p1 > p2:
            return Signal.SELL
        if c < p1 < p2:
            return Signal.BUY

        if "position" in ctx and ctx["position"] != 0:
            if ctx["position"] > 0 and c < p1:
                return Signal.EXIT
            if ctx["position"] < 0 and c > p1:
                return Signal.EXIT

        return Signal.NONE
