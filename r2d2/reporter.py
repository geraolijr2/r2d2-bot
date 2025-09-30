# r2d2/reporter.py
from typing import List, Dict, Any
import statistics as stats

def rolling_metrics(bars: List[Dict[str, Any]], lookback: int = 60) -> Dict[str, Any]:
    if not bars:
        return {}
    window = bars[-lookback:] if len(bars) >= lookback else bars[:]
    closes = [b["close"] for b in window]
    highs  = [b["high"] for b in window]
    lows   = [b["low"]  for b in window]

    vol = (max(closes) - min(closes)) if len(closes) >= 2 else 0.0
    spread_est = stats.fmean([(h - l) for h, l in zip(highs, lows)]) if highs else 0.0
    slope = (closes[-1] - closes[0]) / max(1, len(closes) - 1)
    mean_range = stats.fmean([abs(h - l) for h, l in zip(highs, lows)]) if highs else 0.0

    return {
        "lookback": len(window),
        "close_now": closes[-1],
        "vol_range": vol,
        "slope": slope,
        "mean_range": mean_range,
        "spread_est": spread_est,
    }

def build_snapshot(
    bars: List[Dict[str, Any]],
    equity: float,
    trades_stats: Dict[str, Any],
    strat_name: str,
    strat_params: Dict[str, Any],
    lookback: int = 60
) -> Dict[str, Any]:
    rm = rolling_metrics(bars, lookback=lookback)
    snap = {
        "equity": equity,
        "trades": {
            "count": trades_stats.get("trades", 0),
            "wins": trades_stats.get("wins", 0),
            "losses": trades_stats.get("losses", 0),
            "pnl": trades_stats.get("pnl", 0.0),
        },
        "market": rm,
        "strategy": {
            "name": strat_name,
            "params": dict(strat_params),
        },
    }
    return snap