# r2d2/check_market.py
from r2d2.bybit_exchange import BybitCCXT
from r2d2.utils.logger import get_logger
from r2d2.config import CONFIG

log = get_logger("check_market")

def main():
    ex = BybitCCXT(testnet=True)
    bars = ex.get_ohlcv(CONFIG.symbol, CONFIG.timeframe, limit=5)
    for b in bars:
        log.info(b)

if __name__ == "__main__":
    main()
