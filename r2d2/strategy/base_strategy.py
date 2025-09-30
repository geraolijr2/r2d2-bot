from abc import ABC, abstractmethod
from typing import Dict, Any

class Signal:
    NONE = "NONE"
    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"

class BaseStrategy(ABC):
    def __init__(self, params: Dict[str, Any]):
        self.params = params or {}

    @abstractmethod
    def on_bar(self, bar: Dict[str, float], ctx: Dict[str, Any]) -> str:
        """
        Processa uma barra (candle) e retorna sinal:
        - "BUY", "SELL", "EXIT" ou "NONE".
        bar: {"ts": int, "open": float, "high": float, "low": float, 
"close": float}
        ctx: dicionário mutável com estado
        """
        ...
