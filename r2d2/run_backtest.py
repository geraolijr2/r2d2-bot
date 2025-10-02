import ccxt
import time
import argparse
from datetime import datetime, timezone
from r2d2.config import CONFIG
from r2d2.strategy_manager import StrategyManager
from r2d2.backtester import Backtester
from r2d2.bybit_exchange import BybitCCXT


def normalize_symbol(symbol: str) -> str:
    """
    Normaliza símbolos Bybit no formato CCXT.
    Exemplo:
      'BTC/USDT:USDT' -> 'BTC/USDT'
      'ETH/USDT:USDT' -> 'ETH/USDT'
    """
    if ":USDT" in symbol:
        return symbol.split(":")[0]  # pega só a parte antes do ':'
    return symbol

def load_historical(symbol="BTC/USDT:USDT", timeframe="1m",
                    start_date="2025-09-01", end_date="2025-09-30"):
    bybit = ccxt.bybit()
    bybit.set_sandbox_mode(False)  # dados reais
    bybit.options["defaultType"] = "linear"

    norm_symbol = normalize_symbol(symbol)
    print(f"🔎 Baixando {symbol} (normalizado: {norm_symbol}), timeframe={timeframe}, "
          f"de {start_date} até {end_date}")

    since = int(datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc).timestamp() * 1000)
    until = int(datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc).timestamp() * 1000)

    all_candles = []
    limit = 1000
    timeframe_ms = bybit.parse_timeframe(timeframe) * 1000

    now = since
    while now < until:
        candles = bybit.fetch_ohlcv(norm_symbol, timeframe, since=now, limit=limit)
        if not candles:
            print(f"⚠️ Nenhum candle retornado para {norm_symbol} a partir de {datetime.utcfromtimestamp(now/1000)}")
            break

        for ts, o, h, l, c, v in candles:
            if ts >= until:
                break
            all_candles.append({
                "ts": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            })

        last_ts = candles[-1][0]
        now = last_ts + timeframe_ms
        print(f"✅ {norm_symbol}: já baixados {len(all_candles)} candles... "
              f"até {datetime.utcfromtimestamp(last_ts/1000)}")

        time.sleep(bybit.rateLimit / 1000)

    print(f"📊 Total de candles carregados para {norm_symbol}: {len(all_candles)}")
    return all_candles
    
def main():
    parser = argparse.ArgumentParser(description="Rodar backtest do R2D2")
    parser.add_argument("--symbol", type=str, default="BTC/USDT:USDT")
    parser.add_argument("--timeframe", type=str, default="1m")
    parser.add_argument("--start", type=str, default="2025-09-01")
    parser.add_argument("--end", type=str, default="2025-09-30")
    parser.add_argument("--initial", type=float, default=1000.0)

    # parâmetros da estratégia
    parser.add_argument("--sl_atr_mult", type=float, default=1.8)
    parser.add_argument("--tp_r_mult", type=float, default=2.2)
    parser.add_argument("--bars_confirm_break", type=int, default=1)
    parser.add_argument("--min_atr_points", type=int, default=6)
    parser.add_argument("--filter_ema_slope", type=bool, default=True)
    parser.add_argument("--min_ema_slope_points", type=int, default=3)
    parser.add_argument("--use_break_even", type=bool, default=True)
    parser.add_argument("--break_even_r", type=float, default=1.0)
    parser.add_argument("--use_atr_trailing", type=bool, default=True)
    parser.add_argument("--trail_atr_mult", type=float, default=0.5)
    parser.add_argument("--commission_perc", type=float, default=0.0004)
    parser.add_argument("--slippage_points", type=int, default=2)

    args = parser.parse_args()

    # aplica configs
    CONFIG.initial_balance = args.initial
    CONFIG.symbol = args.symbol
    CONFIG.timeframe = args.timeframe
    CONFIG.commission_perc = args.commission_perc
    CONFIG.slippage_points = args.slippage_points

    # atualiza params da estratégia
    CONFIG.strat_params.sl_atr_mult = args.sl_atr_mult
    CONFIG.strat_params.tp_r_mult = args.tp_r_mult
    CONFIG.strat_params.bars_confirm_break = args.bars_confirm_break
    CONFIG.strat_params.min_atr_points = args.min_atr_points
    CONFIG.strat_params.filter_ema_slope = args.filter_ema_slope
    CONFIG.strat_params.min_ema_slope_points = args.min_ema_slope_points
    CONFIG.strat_params.use_break_even = args.use_break_even
    CONFIG.strat_params.break_even_r = args.break_even_r
    CONFIG.strat_params.use_atr_trailing = args.use_atr_trailing
    CONFIG.strat_params.trail_atr_mult = args.trail_atr_mult

    print(f"🔎 Baixando dados: {args.symbol}, {args.timeframe}, de {args.start} até {args.end}...")
    bars = load_historical(symbol=args.symbol, timeframe=args.timeframe,
                           start_date=args.start, end_date=args.end)
    print(f"✅ Total de candles carregados: {len(bars)}")

    sm = StrategyManager(CONFIG.strategy, params=CONFIG.strat_params.__dict__)

    bt = Backtester(CONFIG, sm.get(), BybitCCXT(testnet=True))
    res = bt.run(bars)
    print("📊 Resultado final:", res)

if __name__ == "__main__":
    main()
