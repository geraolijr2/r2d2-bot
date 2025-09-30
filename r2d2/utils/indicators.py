# r2d2/utils/indicators.py
from typing import List, Tuple

def ema(values: List[float], period: int) -> List[float]:
    if period <= 1 or len(values) == 0:
        return values[:]
    k = 2.0 / (period + 1)
    out, prev = [], None
    for v in values:
        prev = v if prev is None else v * k + prev * (1 - k)
        out.append(prev)
    return out

def true_range(high, low, close):
    tr, prev_close = [], None
    for h, l, c in zip(high, low, close):
        if prev_close is None:
            tr.append(h - l)
        else:
            tr.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
        prev_close = c
    return tr

def atr(high, low, close, period):
    return ema(true_range(high, low, close), period)

def keltner_channels(close, high, low, ema_period, atr_period, mult) -> Tuple[List[float], List[float], List[float], List[float]]:
    mid = ema(close, ema_period)
    a = atr(high, low, close, atr_period)
    upper = [m + mult * av for m, av in zip(mid, a)]
    lower = [m - mult * av for m, av in zip(mid, a)]
    return upper, lower, mid, a
