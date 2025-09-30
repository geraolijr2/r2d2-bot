# r2d2/check_keys.py
import os
import ccxt
from r2d2.utils.logger import get_logger

log = get_logger("check_keys")

def main():
    api_key = "LEyYjMYRcSa3Xc7T5W"
    api_secret = "iImyzKWmNFFXlnmyeUBddr9j66nJ8jbD3xqm"

    if not api_key or not api_secret:
        log.error("Variáveis BYBIT_API_KEY ou BYBIT_API_SECRET não definidas!")
        return

    try:
        bybit = ccxt.bybit({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })
        bybit.set_sandbox_mode(True)  # força uso do testnet
        print("Endpoint atual:", bybit.urls["api"])
        balance = bybit.fetch_balance()
        log.info("Conexão bem sucedida com a Bybit Testnet!")
        log.info(f"Saldos: {balance.get('total', {})}")

    except Exception as e:
        log.error(f"Falha ao conectar na Bybit: {e}")

if __name__ == "__main__":
    main()
