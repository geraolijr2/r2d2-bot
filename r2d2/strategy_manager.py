from typing import Dict, Any
from r2d2.strategy.trend_following import TrendFollowingStrategy
from r2d2.strategy.scalping import ScalpingStrategy

class StrategyManager:
    def __init__(self, name: str, params: Dict[str, Any]):
        self.name = name
        self.params = dict(params)
        self.instance = self._create(self.name, self.params)

    def _create(self, name: str, params: Dict[str, Any]):
        if name == "trend_following":
            return TrendFollowingStrategy(params)
        if name == "scalping":
            return ScalpingStrategy(params)
        raise ValueError(f"strategy inválida: {name}")

    def get(self):
        """Retorna a instância atual da estratégia"""
        return self.instance

    def apply_overrides(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica overrides de parâmetros (ex: IA ajustando)"""
        if not overrides:
            return {}
        changed = {}
        for k, v in overrides.items():
            if k in self.params and self.params[k] != v:
                self.params[k] = v
                changed[k] = v
        if changed:
            self.instance.params.update(changed)
        return changed