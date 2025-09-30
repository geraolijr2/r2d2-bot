# r2d2/ai_client.py
from typing import Dict, Any

class AIClient:
    def __init__(self, provider: str = "openai", api_key: str = "", dry_run: bool = True):
        self.provider = provider
        self.api_key = api_key
        self.dry_run = dry_run

    def suggest_overrides(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        if self.dry_run:
            return self._heuristic(snapshot)
        # TODO: Implementar chamada real à OpenAI
        return {}

    def _heuristic(self, snap: Dict[str, Any]) -> Dict[str, Any]:
        mk = snap.get("market", {})
        params = snap.get("strategy", {}).get("params", {})
        mean_range = mk.get("mean_range", 0.0)
        slope = mk.get("slope", 0.0)

        overrides = {}

        if mean_range > params.get("min_atr_points", 10.0) * 1.5:
            overrides["keltner_mult"] = round(params.get("keltner_mult", 1.2) * 1.15, 2)
            overrides["sl_atr_mult"] = round(params.get("sl_atr_mult", 2.0) * 1.10, 2)

        if abs(slope) > params.get("min_ema_slope_points", 5.0):
            overrides["bars_confirm_break"] = max(1, int(params.get("bars_confirm_break", 2)) - 1)

        if abs(slope) < params.get("min_ema_slope_points", 5.0) * 0.5:
            overrides["filter_ema_slope"] = True
            overrides["min_ema_slope_points"] = max(
                params.get("min_ema_slope_points", 5.0), 5.0
            )

        capped = {}
        for k, v in overrides.items():
            if k == "keltner_mult":
                v = max(0.8, min(2.5, v))
            if k == "sl_atr_mult":
                v = max(0.5, min(4.0, v))
            if k == "bars_confirm_break":
                v = max(1, min(4, v))
            if k == "min_ema_slope_points":
                v = max(1.0, min(15.0, v))
            capped[k] = v
        return capped