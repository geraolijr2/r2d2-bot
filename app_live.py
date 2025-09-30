# app_live.py
from dotenv import load_dotenv
load_dotenv()
import os
import pandas as pd
import streamlit as st
import plotly.express as px
from supabase import create_client

st.set_page_config(page_title="R2D2 Live Monitor", layout="wide")

# --------- conexão supabase ----------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY"))
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------- funções auxiliares ----------
@st.cache_data(ttl=10)
def load_events(limit=20):
    res = supabase.table("r2d2_events").select("*").order("ts", desc=True).limit(limit).execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=10)
def load_orders(limit=20):
    res = supabase.table("r2d2_orders").select("*").order("ts", desc=True).limit(limit).execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=10)
def load_snapshots(limit=200):
    res = supabase.table("r2d2_snapshots").select("*").order("ts", desc=True).limit(limit).execute()
    return pd.DataFrame(res.data)

# --------- layout ----------
st.title("🚀 R2D2 – Live Monitor")

# snapshots → equity curve
snaps = load_snapshots()
if not snaps.empty:
    snaps["equity"] = snaps["snapshot"].apply(
        lambda x: x.get("equity") if isinstance(x, dict) else None
    )
    snaps = snaps.dropna(subset=["equity"]).sort_values("ts")

    fig = px.line(snaps, x="ts", y="equity", title="📈 Equity ao vivo")

    # marca trades (se o LiveTrader logar trades como ordens)
    for _, row in snaps.iterrows():
        pos = row["snapshot"].get("position") if isinstance(row["snapshot"], dict) else None
        if pos and pos.get("side"):
            fig.add_scatter(
                x=[row["ts"]],
                y=[row["equity"]],
                mode="markers",
                marker=dict(
                    color="green" if pos["side"] == "LONG" else "red",
                    size=10,
                    symbol="circle"
                ),
                name=f"Pos {pos['side']}"
            )

    st.plotly_chart(fig, width="stretch")

    last_equity = snaps["equity"].iloc[-1]
    st.metric("Equity Atual", f"{last_equity:.2f} USDT")

# ordens recentes
st.subheader("📑 Ordens Recentes")
orders = load_orders()
if not orders.empty:
    st.dataframe(orders[["ts", "raw"]], use_container_width=True)

# eventos recentes
st.subheader("📋 Eventos")
events = load_events()
if not events.empty:
    st.dataframe(events[["ts", "event", "data"]], use_container_width=True)