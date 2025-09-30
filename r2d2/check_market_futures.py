# r2d2/check_market_futures.py
import os
import ccxt
from r2d2.utils.logger import get_logger

log = get_logger("check_market_futures")

def main():
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")

    if not api_key or not api_secret:
        log.error("Defina BYBIT_API_KEY e BYBIT_API_SECRET no ambiente.")
        return

    try:
        bybit = ccxt.bybit({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })
        bybit.set_sandbox_mode(True)  # garante testnet
        bybit.options["defaultType"] = "linear"  # força futuros perpétuos USDT

        symbol = "BTC/USDT:USDT"  # contrato perpétuo linear
        timeframe = "1m"
        candles = bybit.fetch_ohlcv(symbol, timeframe, limit=5)

        for ts, o, h, l, c, v in candles:
            log.info(f"Candle FUTUROS: ts={ts}, O={o}, H={h}, L={l}, C={c}, V={v}")

    except Exception as e:
        log.error(f"Erro ao puxar candles de futuros: {e}")

if __name__ == "__main__":
    main()