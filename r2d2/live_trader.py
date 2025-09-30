# r2d2/live_trader.py
import time
from typing import Dict, Any
from r2d2.config import CONFIG, AppConfig
from r2d2.bybit_exchange import BybitCCXT
from r2d2.exchange_api import ExchangeAPI
from r2d2.strategy_manager import StrategyManager
from r2d2.position_manager import PositionManager
from r2d2.risk_manager import RiskManager
from r2d2.control_loop import ControlLoop
from r2d2.strategy.base_strategy import Signal
from r2d2.utils.logger import get_logger
from r2d2.supabase_store import SupabaseStore

log = get_logger("live")

_TIMEFRAME_SECONDS = {
    "1s": 1,
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400
}

class LiveTrader:
    def __init__(self, cfg: AppConfig = CONFIG, poll_interval: int | None = None):
        self.cfg = cfg
        self.exchange: ExchangeAPI = self._load_exchange()
        self.sm = StrategyManager(cfg.strategy, params=self._build_params(cfg))
        self.strategy = self.sm.get()
        self.pm = PositionManager()
        self.rm = RiskManager(cfg.risk)
        self.rm.start_day(cfg.initial_balance)
        self.equity = cfg.initial_balance
        self.point_value = self.exchange.point_value(cfg.symbol)
        self.results: Dict[str, Any] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        self.trades_log = []
        self.bars_ref = []

        default_poll = max(1, _TIMEFRAME_SECONDS.get(cfg.timeframe, 60) // 3)
        self.poll_interval = poll_interval if poll_interval is not None else default_poll

        self.ctrl = ControlLoop(
            get_bars_fn=lambda: self.bars_ref,
            get_equity_fn=lambda: self.equity,
            get_trade_stats_fn=lambda: self.results,
            strat_name=cfg.strategy,
            strat_params_ref=self.strategy.params,
            apply_overrides_fn=self.sm.apply_overrides,
            interval_bars=60,
        )

        # Supabase
        self.sb = SupabaseStore()
        if self.sb.enabled:
            self.sb.log_event("startup", {
                "symbol": cfg.symbol,
                "tf": cfg.timeframe,
                "testnet": cfg.bybit_testnet
            })

    def _load_exchange(self) -> ExchangeAPI:
        if self.cfg.exchange == "bybit":
            return BybitCCXT(api_key="", api_secret="", testnet=self.cfg.bybit_testnet)
        raise ValueError(f"exchange não suportada no modo live: {self.cfg.exchange}")

    def _build_params(self, cfg: AppConfig) -> Dict[str, Any]:
        return {
            "ema_period": cfg.strat_params.ema_period,
            "atr_period": cfg.strat_params.atr_period,
            "keltner_mult": cfg.strat_params.keltner_mult,
            "sl_atr_mult": cfg.strat_params.sl_atr_mult,
            "tp_r_mult": cfg.strat_params.tp_r_mult,
            "bars_confirm_break": cfg.strat_params.bars_confirm_break,
            "min_atr_points": cfg.strat_params.min_atr_points,
            "max_spread_points": cfg.strat_params.max_spread_points,
            "filter_ema_slope": cfg.strat_params.filter_ema_slope,
            "min_ema_slope_points": cfg.strat_params.min_ema_slope_points,
        }

    def run(self):
        log.info(
            f"Iniciando R2D2 Live | symbol={self.cfg.symbol} tf={self.cfg.timeframe} "
            f"exchange={self.cfg.exchange} testnet={self.cfg.bybit_testnet} poll={self.poll_interval}s"
        )
        i = 0
        last_ts = None

        while True:
            try:
                bars = self.exchange.get_ohlcv(self.cfg.symbol, self.cfg.timeframe, limit=2)
                if not bars:
                    time.sleep(self.poll_interval)
                    continue

                bar = bars[-1]
                if last_ts is not None and bar["ts"] == last_ts:
                    time.sleep(self.poll_interval)
                    continue

                self.bars_ref.append(bar)
                last_ts = bar["ts"]
                price = bar["close"]
                log.info(
                    f"New Candle | ts={bar['ts']} O={bar['open']} H={bar['high']} "
                    f"L={bar['low']} C={bar['close']} V={bar.get('volume',0)}"
                )

                if self.sb.enabled:
                    snapshot = {
                        "equity": self.equity,
                        "position": {
                            "side": self.pm.pos.side,
                            "qty": self.pm.pos.qty,
                            "entry": self.pm.pos.entry,
                            "stop": self.pm.pos.stop,
                            "take": self.pm.pos.take,
                        } if not self.pm.flat() else None,
                    }
                    self.sb.log_snapshot(snapshot)

                pnl_stop = self.pm.check_stops(price)
                if pnl_stop is not None:
                    self._apply_pnl(pnl_stop)

                ctx_pos = 0 if self.pm.flat() else (1 if self.pm.pos.side == "LONG" else -1)
                sig = self.strategy.on_bar(bar, {"position": ctx_pos})

                if self.rm.can_trade():
                    self._handle_signal(sig, price, bar)

                if self.cfg.risk.use_break_even and not self.pm.flat():
                    moved = abs(price - self.pm.pos.entry)
                    r_points = abs(self.pm.pos.entry - self.pm.pos.stop)
                    if r_points > 0 and moved >= self.cfg.risk.break_even_r * r_points:
                        self.pm.move_to_breakeven(price)

                upd = self.ctrl.maybe_update(i)
                if upd.get("applied"):
                    log.info(f"Overrides aplicados: {upd['applied']}")

                i += 1
                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                log.info("Encerrando R2D2 Live (Ctrl+C).")
                if self.sb.enabled:
                    self.sb.log_event("shutdown", {"equity": self.equity})
                break
            except Exception as e:
                log.error(f"Erro no loop live: {e}")
                if self.sb.enabled:
                    self.sb.log_event("error", {"msg": str(e)})
                time.sleep(self.poll_interval)

    def _apply_pnl(self, pnl: float):
        fee = abs(pnl) * self.cfg.commission_perc
        net = pnl - fee
        self.equity += net
        self.results["pnl"] += net
        self.results["trades"] += 1

        if net >= 0:
            self.results["wins"] += 1
        else:
            self.results["losses"] += 1

        self.rm.register_trade(net)
        print(f"Trade #{self.results['trades']}: PnL={net:.2f}, Equity={self.equity:.2f}")

    def _handle_signal(self, sig: str, price: float, bar: Dict[str, Any]):
        if sig in (Signal.BUY, Signal.SELL) and self.pm.flat():
            atr_points = bar.get("atr", self.cfg.strat_params.atr_period)
            stop_points = max(1.0, self.cfg.strat_params.sl_atr_mult * atr_points)
            tp_points = self.cfg.strat_params.tp_r_mult * stop_points

            qty_raw = self.rm.size_from_risk(price, stop_points, self.equity, self.point_value)
            qty = self.exchange.amount_to_precision(self.cfg.symbol, qty_raw)

            if sig == Signal.BUY:
                sl, tp = price - stop_points, price + tp_points
                order = self.exchange.place_order(
                    self.cfg.symbol, "BUY", qty, type_="market",
                    params={
                        "takeProfitPrice": self.exchange.price_to_precision(self.cfg.symbol, tp),
                        "stopLossPrice": self.exchange.price_to_precision(self.cfg.symbol, sl),
                        "reduceOnly": False,
                    }
                )
                if order.get("status") == "error": return
                self.pm.open("LONG", qty, price, sl, tp)
                if self.sb.enabled: self.sb.log_order(order)

            elif sig == Signal.SELL:
                sl, tp = price + stop_points, price - tp_points
                order = self.exchange.place_order(
                    self.cfg.symbol, "SELL", qty, type_="market",
                    params={
                        "takeProfitPrice": self.exchange.price_to_precision(self.cfg.symbol, tp),
                        "stopLossPrice": self.exchange.price_to_precision(self.cfg.symbol, sl),
                        "reduceOnly": False,
                    }
                )
                if order.get("status") == "error": return
                self.pm.open("SHORT", qty, price, sl, tp)
                if self.sb.enabled: self.sb.log_order(order)

        elif sig == Signal.EXIT and not self.pm.flat():
            side = "SELL" if self.pm.pos.side == "LONG" else "BUY"
            qty = self.exchange.amount_to_precision(self.cfg.symbol, self.pm.pos.qty)
            order = self.exchange.place_order(self.cfg.symbol, side, qty, type_="market", params={"reduceOnly": True})
            if order.get("status") == "error": return
            pnl = self.pm.close(price)
            self._apply_pnl(pnl)
            if self.sb.enabled: self.sb.log_order(order)