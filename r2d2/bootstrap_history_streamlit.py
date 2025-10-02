import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client
import time

# -------------------------------
# 1. Conexão Supabase
# -------------------------------
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # use sempre a SERVICE_KEY
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------------
# 2. Helpers Bybit API
# -------------------------------
def get_symbols_info(category="linear"):
    """Busca instrumentos de uma categoria, com paginação"""
    url = "https://api.bybit.com/v5/market/instruments-info"
    params = {"category": category}
    all_data = []
    cursor = None
    while True:
        if cursor:
            params["cursor"] = cursor
        r = requests.get(url, params=params).json()
        data = r.get("result", {}).get("list", [])
        all_data.extend(data)
        cursor = r.get("result", {}).get("nextPageCursor")
        if not cursor:
            break
    for item in all_data:
        item["category"] = category
    return all_data

def get_symbols_tickers(category="linear"):
    """Busca tickers de uma categoria (24h volume, lastPrice etc)"""
    url = "https://api.bybit.com/v5/market/tickers"
    params = {"category": category}
    all_data = []
    cursor = None
    while True:
        if cursor:
            params["cursor"] = cursor
        r = requests.get(url, params=params).json()
        data = r.get("result", {}).get("list", [])
        all_data.extend(data)
        cursor = r.get("result", {}).get("nextPageCursor")
        if not cursor:
            break
    for item in all_data:
        item["category"] = category
    return all_data

def get_first_candle_time(symbol: str, category="linear"):
    """Busca o timestamp do primeiro candle disponível na Bybit"""
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": category,
        "symbol": symbol,
        "interval": "1",
        "limit": 1,
        "start": 1420070400000  # 2015-01-01 em ms
    }
    r = requests.get(url, params=params).json()
    result = r.get("result", {}).get("list", [])
    if not result:
        return None
    return int(result[0][0])  # timestamp em ms do primeiro candle

def fetch_ohlcv_batch(symbol: str, start: int=None, end: int=None, category="linear"):
    """Busca candles OHLCV (sempre 1m)"""
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": category,
        "symbol": symbol,
        "interval": "1",
        "limit": 200
    }
    if start is not None:
        params["start"] = start
    if end is not None:
        params["end"] = end

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
        supabase.table("ohlcv").upsert(
            rows,
            on_conflict="symbol,exchange,timestamp"
        ).execute()

def bootstrap_history(symbol: str, category="linear", start_ms=None, end_ms=None):
    """Baixa histórico completo ou parcial do ativo, a partir do primeiro candle real"""
    # Descobre o primeiro candle real
    first_candle = get_first_candle_time(symbol, category)
    if not first_candle:
        st.error(f"⚠️ Nenhum candle encontrado para {symbol} ({category})")
        return

    start_ms = start_ms or first_candle
    end_ms = end_ms or int(datetime.now().timestamp() * 1000)

    st.write(f"📥 Baixando {symbol} ({category}) de {datetime.fromtimestamp(start_ms/1000)} até {datetime.fromtimestamp(end_ms/1000)}")

    current = start_ms
    batch_size = 200 * 60 * 1000
    total_inserted = 0
    progress = st.progress(0)

    while current < end_ms:
        end = min(current + batch_size, end_ms)
        data = fetch_ohlcv_batch(symbol, current, end, category)
        if not data:
            st.warning("⚠️ Nenhum dado retornado, parando…")
            break

        save_ohlcv_to_db(data)
        total_inserted += len(data)

        st.write(f"✅ Inseridos {len(data)} registros até {data[-1]['timestamp']} (total: {total_inserted})")

        last_ts = int(datetime.fromisoformat(data[-1]["timestamp"]).timestamp() * 1000)
        current = last_ts + 1

        pct = min(int((current-start_ms)/(end_ms-start_ms)*100), 100)
        progress.progress(pct)
        time.sleep(0.2)

    st.success(f"🎉 Finalizado! Total de {total_inserted} candles gravados.")

# -------------------------------
# 3. Interface Streamlit
# -------------------------------
st.title("📥 Bootstrap Histórico - Bybit")

category = st.selectbox("Categoria", ["spot", "linear", "inverse"])
symbols_info = get_symbols_info(category)
tickers_info = get_symbols_tickers(category)

if not symbols_info:
    st.error("Nenhum símbolo encontrado nessa categoria.")
else:
    df_symbols = pd.DataFrame([
        {
            "symbol": item["symbol"],
            "baseCoin": item.get("baseCoin"),
            "quoteCoin": item.get("quoteCoin"),
            "status": item.get("status"),
            "category": item.get("category"),
            "launchTime": datetime.fromtimestamp(int(item["launchTime"]) / 1000) 
                          if item.get("launchTime") else None
        }
        for item in symbols_info
    ])

    df_tickers = pd.DataFrame([
        {
            "symbol": t["symbol"],
            "category": t.get("category"),
            "lastPrice": float(t["lastPrice"]),
            "volume24h": float(t.get("volume24h", 0)) if "volume24h" in t else None,
            "turnover24h": float(t.get("turnover24h", 0)) if "turnover24h" in t else None,
        }
        for t in tickers_info
    ])

    df = pd.merge(df_symbols, df_tickers, on=["symbol","category"], how="left")

    only_trading = st.checkbox("Mostrar apenas ativos em Trading", value=True)
    if only_trading:
        df = df[df["status"] == "Trading"]

    if "volume24h" in df.columns:
        df = df.sort_values(by="volume24h", ascending=False)

    df["display"] = df.apply(lambda row: f"{row['symbol']} ({row['baseCoin']})", axis=1)

    st.dataframe(df[["display","status","category","launchTime","lastPrice","volume24h"]])

    symbol_display = st.selectbox("Escolha o símbolo disponível", df["display"].tolist())
    match = df[df["display"] == symbol_display].iloc[0]
    real_cat = match["category"]

    modo = st.radio("Modo de download:", ["Histórico completo", "Intervalo customizado"])

    start_ms = None
    end_ms = None
    if modo == "Intervalo customizado":
        start_date = st.date_input("Data inicial", datetime.now() - timedelta(days=365))
        end_date = st.date_input("Data final", datetime.now())
        start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
        end_ms = int(datetime.combine(end_date, datetime.min.time()).timestamp() * 1000)

    if st.button("Baixar dados"):
        bootstrap_history(match["symbol"], real_cat, start_ms=start_ms, end_ms=end_ms)
