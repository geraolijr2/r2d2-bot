from typing import Dict, Any, List
from .base_strategy import BaseStrategy, Signal
from r2d2.utils.indicators import keltner_channels

class TrendFollowingStrategy(BaseStrategy):
    def __init__(self, params: Dict[str, Any]):
        super().__init__(params)
        self.buffer: Dict[str, List[float]] = {"close": [], "high": [], "low": []}
        self.break_count_up = 0
        self.break_count_dn = 0

    def on_bar(self, bar: Dict[str, float], ctx: Dict[str, Any]) -> str:
        p = self.params
        self.buffer["close"].append(bar["close"])
        self.buffer["high"].append(bar["high"])
        self.buffer["low"].append(bar["low"])

        n = len(self.buffer["close"])
        min_len = max(p["ema_period"], p["atr_period"]) + 5
        if n < min_len:
            return Signal.NONE

        upper, lower, mid, a = keltner_channels(
            self.buffer["close"], self.buffer["high"], self.buffer["low"],
            p["ema_period"], p["atr_period"], p["keltner_mult"]
        )

        c = self.buffer["close"][-1]
        ema_slope = mid[-1] - mid[-2]

        # filtro de inclinação da média
        if p["filter_ema_slope"] and abs(ema_slope) < p["min_ema_slope_points"]:
            return Signal.NONE
        # filtro de volatilidade mínima
        if a[-1] < p["min_atr_points"]:
            return Signal.NONE

        # confirmações de rompimento
        if c > upper[-1]:
            self.break_count_up += 1
            self.break_count_dn = 0
        elif c < lower[-1]:
            self.break_count_dn += 1
            self.break_count_up = 0
        else:
            self.break_count_up = max(0, self.break_count_up - 1)
            self.break_count_dn = max(0, self.break_count_dn - 1)

        if self.break_count_up >= p["bars_confirm_break"]:
            return Signal.BUY
        if self.break_count_dn >= p["bars_confirm_break"]:
            return Signal.SELL

        # saída básica: se já tem posição e preço voltar pro meio da banda
        if "position" in ctx and ctx["position"] != 0:
            if ctx["position"] > 0 and c < mid[-1]:
                return Signal.EXIT
            if ctx["position"] < 0 and c > mid[-1]:
                return Signal.EXIT

        return Signal.NONE
