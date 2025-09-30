import os
import ccxt
from typing import List, Dict, Any, Optional
from r2d2.exchange_api import ExchangeAPI
from r2d2.utils.logger import get_logger

log = get_logger("bybit")

class BybitCCXT(ExchangeAPI):
    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = True):
        self.testnet = testnet
        self.client = ccxt.bybit({
            "apiKey": api_key or os.getenv("BYBIT_API_KEY", ""),
            "secret": api_secret or os.getenv("BYBIT_API_SECRET", ""),
            "enableRateLimit": True,
        })
        if self.testnet:
            self.client.set_sandbox_mode(True)
            log.info("BybitCCXT inicializada em modo TESTNET")
        else:
            log.info("BybitCCXT inicializada em modo REAL")

        # Futuros perpétuos USDT
        self.client.options["defaultType"] = "linear"
        self.client.load_markets()

    def ensure_symbol_config(self, symbol: str, leverage: int = 5, margin_mode: str = "isolated"):
        try:
            try:
                self.client.set_leverage(leverage, symbol)
                log.info(f"Leverage configurado: {leverage}x para {symbol}")
            except Exception as e:
                log.warning(f"Falha set_leverage({leverage}): {e}")
            try:
                self.client.set_margin_mode(margin_mode, symbol)
                log.info(f"Margin mode configurado: {margin_mode} para {symbol}")
            except Exception as e:
                log.warning(f"Falha set_margin_mode({margin_mode}): {e}")
        except Exception as e:
            log.error(f"ensure_symbol_config erro: {e}")

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        try:
            return float(self.client.amount_to_precision(symbol, amount))
        except Exception:
            return amount

    def price_to_precision(self, symbol: str, price: float) -> float:
        try:
            return float(self.client.price_to_precision(symbol, price))
        except Exception:
            return price

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> List[Dict[str, Any]]:
        data = self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
        out = []
        for ts, o, h, l, c, v in data:
            out.append({"ts": ts, "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)})
        return out

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        type_: str = "market",
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        p = dict(params or {})
        # por via das dúvidas, sinalize a categoria linear
        p.setdefault("category", "linear")
        amount = self.amount_to_precision(symbol, qty)
        prc = None if type_ == "market" else self.price_to_precision(symbol, float(price))

        def _create(_params: Dict[str, Any]):
            return self.client.create_order(
                symbol=symbol,
                type=type_,
                side=side.lower(),
                amount=amount,
                price=prc,
                params=_params,
            )

        try:
            order = _create(p)
            log.info(f"Ordem enviada: {order}")
            return order
        except Exception as e:
            msg = str(e)
            log.error(f"Erro ao enviar ordem Bybit (primeira tentativa): {msg}")

            # Muitos erros de 'Invalid buying/selling price' vêm de anexar SL/TP na criação.
            # Tente novamente removendo chaves de TP/SL:
            if "price" in msg.lower() or "buying price" in msg.lower() or "selling price" in msg.lower():
                for k in ("takeProfitPrice", "takeProfit", "stopLossPrice", "stopLoss"):
                    p.pop(k, None)
                try:
                    order = _create(p)
                    log.warning(f"Retry sem TP/SL: ordem enviada: {order}")
                    return order
                except Exception as e2:
                    log.error(f"Retry falhou: {e2}")
                    return {"status": "error", "error": str(e2)}
            return {"status": "error", "error": msg}

    def point_value(self, symbol: str) -> float:
        return 1.0
