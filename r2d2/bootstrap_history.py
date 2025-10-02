import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

# -------------------------------
# 1. Conexão Supabase
# -------------------------------
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------------
# 2. Funções auxiliares
# -------------------------------
def get_launch_time(symbol: str, category="linear"):
    url = "https://api.bybit.com/v5/market/instruments-info"
    params = {"category": category, "symbol": symbol}
    r = requests.get(url, params=params).json()
    info = r["result"]["list"][0]
    return int(info["launchTime"])  # em ms

def fetch_ohlcv_batch(symbol: str, start: int, end: int, category="linear"):
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": category,
        "symbol": symbol,
        "interval": "1",  # sempre 1m
        "start": start,
        "end": end,
        "limit": 200
    }
    r = requests.get(url, params=params).json()
    result = r.get("result", {}).get("list", [])
    data = []
    for item in result:
        data.append({
            "symbol": symbol,
            "exchange": "Bybit",
            "timestamp": datetime.fromtimestamp(int(item[0]) / 1000).isoformat(),
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": float(item[5]),
        })
    return data

def save_ohlcv_to_db(rows):
    if rows:
        supabase.table("ohlcv") \
            .upsert(rows, on_conflict="symbol,exchange,timestamp") \
            .execute()


# -------------------------------
# 3. Processo de bootstrap
# -------------------------------
def bootstrap_history(symbol: str, category="linear"):
    launch_time = get_launch_time(symbol, category)
    now = int(datetime.now().timestamp() * 1000)

    print(f"Carregando histórico completo de {symbol} desde {datetime.fromtimestamp(launch_time/1000)}")

    current = launch_time
    batch_size = 200 * 60 * 1000  # 200 candles de 1m em ms

    total_inserted = 0

    while current < now:
        end = min(current + batch_size, now)
        data = fetch_ohlcv_batch(symbol, current, end, category)
        if not data:
            print("⚠️ Nenhum dado retornado, parando...")
            break

        save_ohlcv_to_db(data)
        total_inserted += len(data)
        print(f"✅ Inseridos {len(data)} registros até {data[-1]['timestamp']} (total: {total_inserted})")

        # avançar 1ms depois do último candle, para não repetir
        last_ts = int(datetime.fromisoformat(data[-1]["timestamp"]).timestamp() * 1000)
        current = last_ts + 1

        time.sleep(0.2)  # respeitar rate limit

    print(f"🎉 Finalizado! Total de {total_inserted} candles gravados.")

# -------------------------------
# 4. Execução
# -------------------------------
if __name__ == "__main__":
    symbol = input("Digite o símbolo (ex: BTCUSDT): ").strip().upper()
    category = input("Digite a categoria (spot, linear ou inverse): ").strip().lower()
    bootstrap_history(symbol, category=category)
