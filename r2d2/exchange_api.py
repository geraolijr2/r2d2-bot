from typing import List, Dict, Any, Optional
from r2d2.utils.logger import get_logger

log = get_logger("exchange")

class ExchangeAPI:
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def place_order(self, symbol: str, side: str, qty: float,
                    price: Optional[float] = None, type_: str = "market") -> Dict[str, Any]:
        raise NotImplementedError

    def cancel_all(self, symbol: str) -> None:
        pass

    def point_value(self, symbol: str) -> float:
        # exemplo: mini dólar = 10, mas em cripto geralmente 1
        return 1.0
