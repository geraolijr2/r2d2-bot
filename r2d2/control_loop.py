# r2d2/control_loop.py
from typing import List, Dict, Any, Callable
from r2d2.reporter import build_snapshot
from r2d2.ai_client import AIClient

class ControlLoop:
    def __init__(
        self,
        get_bars_fn: Callable[[], List[Dict[str, Any]]],
        get_equity_fn: Callable[[], float],
        get_trade_stats_fn: Callable[[], Dict[str, Any]],
        strat_name: str,
        strat_params_ref: Dict[str, Any],
        apply_overrides_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        interval_bars: int = 60,
        ai_client: AIClient = None,
    ):
        self.get_bars = get_bars_fn
        self.get_equity = get_equity_fn
        self.get_stats = get_trade_stats_fn
        self.strat_name = strat_name
        self.params_ref = strat_params_ref
        self.apply_overrides = apply_overrides_fn
        self.interval_bars = interval_bars
        self.ai = ai_client or AIClient(dry_run=True)
        self._last_applied_at = 0

    def maybe_update(self, i_bar_index: int) -> Dict[str, Any]:
        if i_bar_index - self._last_applied_at + 1 < self.interval_bars:
            return {}
        bars = self.get_bars()
        equity = self.get_equity()
        stats = self.get_stats()
        snap = build_snapshot(bars, equity, stats, self.strat_name, self.params_ref, lookback=self.interval_bars)
        overrides = self.ai.suggest_overrides(snap)
        applied = self.apply_overrides(overrides)
        self._last_applied_at = i_bar_index
        if applied:
            return {"applied": applied, "snapshot": snap}
        return {}