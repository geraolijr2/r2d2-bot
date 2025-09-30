# app_backtests.py
from dotenv import load_dotenv
load_dotenv()
import os
import pandas as pd
import streamlit as st
import plotly.express as px
from supabase import create_client

st.set_page_config(page_title="R2D2 Backtests", layout="wide")

# --------- conexão supabase ----------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY"))
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------- funções auxiliares ----------
@st.cache_data(ttl=60)
def load_backtests():
    res = supabase.table("backtests").select("*").order("created_at", desc=True).execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=60)
def load_trades(backtest_id):
    res = supabase.table("backtest_trades").select("*").eq("backtest_id", backtest_id).order("id").execute()
    return pd.DataFrame(res.data)

# --------- layout ----------
st.title("🤖 R2D2 – Histórico de Backtests")

df = load_backtests()
if df.empty:
    st.warning("Nenhum backtest encontrado ainda.")
    st.stop()

# resumo em cards
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Backtests", len(df))
col2.metric("Total Trades", int(df["trades"].sum()))
col3.metric("Winrate Médio", f"{(df['wins'].sum()/df['trades'].sum()*100):.1f}%")
col4.metric("PnL Médio", f"{df['pnl'].mean():.2f} USDT")

# tabela de backtests
st.subheader("📊 Lista de Backtests")
st.dataframe(
    df[["id", "created_at", "strategy", "symbol", "timeframe", "initial_balance",
        "final_balance", "pnl", "trades", "wins", "losses"]].set_index("id"),
    use_container_width=True,
)

# selecionar um backtest
st.subheader("🔍 Detalhes")
selected = st.selectbox("Escolha um backtest", df["id"].tolist())

if selected:
    details = df[df["id"] == selected].iloc[0]
    st.write(f"**Estratégia:** {details['strategy']} | **Símbolo:** {details['symbol']} | "
             f"**Timeframe:** {details['timeframe']} | **Data:** {details['created_at']}")

    trades_df = load_trades(selected)
    if trades_df.empty:
        st.warning("Nenhum trade registrado.")
    else:
        # curva de equity
        fig = px.line(trades_df, x="id", y="equity", title="📈 Curva de Equity", markers=True)
        st.plotly_chart(fig, width="stretch")

        # tabela de trades
        st.subheader("📑 Trades")
        st.dataframe(
            trades_df[["id", "side", "entry_price", "exit_price", "qty", "pnl", "equity"]],
            use_container_width=True,
        )

        # estatísticas rápidas
        col1, col2, col3 = st.columns(3)
        col1.metric("Trades", details["trades"])
        col2.metric("Winrate", f"{(details['wins']/details['trades']*100):.1f}%")
        col3.metric("PnL Total", f"{details['pnl']:.2f} USDT")