# r2d2/backtester.py
from typing import List, Dict, Any, Optional
from datetime import datetime
from r2d2.utils.logger import get_logger
from r2d2.strategy.base_strategy import Signal
from r2d2.position_manager import PositionManager
from r2d2.risk_manager import RiskManager
from r2d2.config import AppConfig
from r2d2.supabase_store import SupabaseStore

log = get_logger("backtest")

class Backtester:
    def __init__(self, cfg: AppConfig, strategy, exchange):
        self.cfg = cfg
        self.strategy = strategy
        self.exchange = exchange
        self.pm = PositionManager()
        self.rm = RiskManager(cfg.risk)
        self.equity = cfg.initial_balance
        self.point_value = exchange.point_value(cfg.symbol)
        self.results = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}

        # integração com supabase
        self.sb = SupabaseStore()
        self.trades_log: List[Dict[str, Any]] = []

        # snapshot da posição aberta (dados fiéis da ENTRADA)
        self._open_snapshot: Optional[Dict[str, Any]] = None

        # Diagnóstico
        self.debug = {
            "signals": 0,
            "entries": 0,
            "blocked_risk": 0,
            "blocked_time": 0,     # novo: bloqueado por hora/dia
            "stop_closes": 0,
            "exit_closes": 0,
            "tp_hits": 0,          # novo
            "sl_hits": 0,          # novo
            "blocked_reasons": {},
            "blocked_by_day": {}
        }

    @staticmethod
    def _utc_dt(ts_ms: Optional[int]) -> Optional[datetime]:
        return datetime.utcfromtimestamp(ts_ms / 1000) if ts_ms is not None else None

    @staticmethod
    def _utc_day_from_ts(ts_ms: Optional[int]):
        dt = Backtester._utc_dt(ts_ms)
        return dt.date() if dt else None

    def _can_trade_debug(self, bar: Dict[str, Any]):
        """Wrapper de can_trade() com inferência do motivo do bloqueio."""
        ok = self.rm.can_trade()
        reason = "ok"
        if ok:
            return True, reason
        try:
            if hasattr(self.rm, "trades_today") and hasattr(self.rm, "max_trades_per_day"):
                if getattr(self.rm, "max_trades_per_day") is not None and \
                   getattr(self.rm, "trades_today", 0) >= getattr(self.rm, "max_trades_per_day"):
                    reason = "cap_trades_day"
            if hasattr(self.rm, "daily_pnl") and hasattr(self.rm, "max_daily_loss"):
                if getattr(self.rm, "max_daily_loss") not in (None, 0) and \
                   getattr(self.rm, "daily_pnl", 0.0) <= -abs(getattr(self.rm, "max_daily_loss")):
                    reason = "daily_loss_limit"
            if any(hasattr(self.rm, a) for a in ("cooldown_bars_left", "cooldown_until_ts")):
                left = getattr(self.rm, "cooldown_bars_left", 0) or 0
                until = getattr(self.rm, "cooldown_until_ts", None)
                if (isinstance(left, (int, float)) and left > 0) or (until and bar.get("ts") and bar["ts"] < until):
                    reason = "cooldown"
        except Exception:
            reason = "unknown"
        return False, reason

    def _time_filter_allows(self, ts_ms: Optional[int]) -> bool:
        """Permite controlar entradas por hora UTC e dia da semana."""
        dt = self._utc_dt(ts_ms)
        if dt is None:
            return True  # sem timestamp, não bloqueia

        hours = getattr(self.cfg.strat_params, "allowed_hours", None)
        days  = getattr(self.cfg.strat_params, "allowed_weekdays", None)  # ex.: ["Tuesday","Thursday"]

        if hours and len(hours) > 0 and dt.hour not in set(hours):
            return False
        if days and len(days) > 0 and dt.strftime("%A") not in set(days):
            return False
        return True

    def run(self, bars: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not bars:
            log.warning("Nenhum dado para backtest.")
            return {}

        current_day = None
        ctx = {"position": 0}

        for i, bar in enumerate(bars):
            ts = bar.get("ts")
            bar_dt = self._utc_dt(ts)
            bar_day = bar_dt.date() if bar_dt else None
            price = bar["close"]

            # --- ROLLOVER DIÁRIO (UTC) ---
            if bar_day is not None:
                if current_day is None:
                    self.rm.start_day(self.equity)
                    current_day = bar_day
                elif bar_day != current_day:
                    if hasattr(self.rm, "end_day"):
                        try:
                            self.rm.end_day()
                        except Exception:
                            pass
                    self.rm.start_day(self.equity)
                    current_day = bar_day

            # --- 1) STOPS: snapshot ANTES de checar stops
            pos_snapshot_pre = None if self.pm.flat() else (self._open_snapshot or {
                "side": getattr(self.pm.pos, "side", "UNKNOWN"),
                "entry": float(getattr(self.pm.pos, "entry", price)),
                "qty": float(getattr(self.pm.pos, "qty", 0.0)),
                "sl": float(getattr(self.pm.pos, "sl", price)) if hasattr(self.pm.pos, "sl") else None,
                "tp": float(getattr(self.pm.pos, "tp", price)) if hasattr(self.pm.pos, "tp") else None,
                "ts": ts
            })

            pnl_stop = self.pm.check_stops(price)
            if pnl_stop is not None and pos_snapshot_pre is not None:
                self._apply_pnl(pnl_stop, bar, exit_price=price, pos=pos_snapshot_pre, close_reason="stop")
                self._open_snapshot = None
                ctx["position"] = 0
                self.debug["stop_closes"] += 1
                continue

            # --- 2) Sinal da estratégia
            sig = self.strategy.on_bar(bar, ctx)

            # --- 2a) Aberturas: gating por tempo + risco APENAS para novas entradas
            if sig in (Signal.BUY, Signal.SELL):
                self.debug["signals"] += 1

                if self.pm.flat():
                    # Filtro de hora/dia (apenas para ENTRADA)
                    if not self._time_filter_allows(ts):
                        self.debug["blocked_time"] += 1
                        continue

                    ok, reason = self._can_trade_debug(bar)
                    if not ok:
                        self.debug["blocked_risk"] += 1
                        self.debug["blocked_reasons"][reason] = self.debug["blocked_reasons"].get(reason, 0) + 1
                        if bar_day is not None:
                            key = bar_day.isoformat()
                            self.debug["blocked_by_day"][key] = self.debug["blocked_by_day"].get(key, 0) + 1
                        continue

                    # NÃO abrir na última barra para evitar open->close no mesmo preço
                    is_last_bar = (i == len(bars) - 1)
                    if is_last_bar:
                        continue

                    # calcula SL/TP e qty (simplificação baseada em ATR-pontos)
                    stop_points = max(1.0, self.cfg.strat_params.sl_atr_mult * 10)
                    tp_points   = self.cfg.strat_params.tp_r_mult * stop_points
                    qty = self.rm.size_from_risk(price, stop_points, self.equity, self.point_value)

                    if sig == Signal.BUY:
                        sl, tp = price - stop_points, price + tp_points
                        self.pm.open("LONG", qty, price, sl, tp)
                        ctx["position"] = 1
                        side = "LONG"
                    else:
                        sl, tp = price + stop_points, price - tp_points
                        self.pm.open("SHORT", qty, price, sl, tp)
                        ctx["position"] = -1
                        side = "SHORT"

                    # snapshot fiel de ENTRADA (com SL/TP)
                    self._open_snapshot = {
                        "side": side,
                        "entry": float(price),
                        "qty": float(qty),
                        "sl": float(sl),
                        "tp": float(tp),
                        "ts": ts,
                    }
                    self.debug["entries"] += 1

            # --- 2b) Fechamentos por EXIT (sem gating de risco)
            elif sig == Signal.EXIT and not self.pm.flat():
                pos_snapshot = self._open_snapshot or {
                    "side": getattr(self.pm.pos, "side", "UNKNOWN"),
                    "entry": float(getattr(self.pm.pos, "entry", price)),
                    "qty": float(getattr(self.pm.pos, "qty", 0.0)),
                    "sl": float(getattr(self.pm.pos, "sl", price)) if hasattr(self.pm.pos, "sl") else None,
                    "tp": float(getattr(self.pm.pos, "tp", price)) if hasattr(self.pm.pos, "tp") else None,
                    "ts": ts,
                }
                pnl = self.pm.close(price)
                self._apply_pnl(pnl, bar, exit_price=price, pos=pos_snapshot, close_reason="exit")
                self._open_snapshot = None
                ctx["position"] = 0
                self.debug["exit_closes"] += 1

        # --- 3) Fecha posição no final do período, se existir
        if not self.pm.flat():
            last_bar = bars[-1]
            price_last = last_bar["close"]
            last_ts = last_bar.get("ts")
            pos_snapshot = self._open_snapshot or {
                "side": getattr(self.pm.pos, "side", "UNKNOWN"),
                "entry": float(getattr(self.pm.pos, "entry", price_last)),
                "qty": float(getattr(self.pm.pos, "qty", 0.0)),
                "sl": float(getattr(self.pm.pos, "sl", price_last)) if hasattr(self.pm.pos, "sl") else None,
                "tp": float(getattr(self.pm.pos, "tp", price_last)) if hasattr(self.pm.pos, "tp") else None,
                "ts": last_ts,
            }
            pnl = self.pm.close(price_last)
            self._apply_pnl(pnl, last_bar, exit_price=price_last, pos=pos_snapshot, close_reason="exit_end")
            self._open_snapshot = None
            self.debug["exit_closes"] += 1

        # encerra último dia (se existir hook)
        if hasattr(self.rm, "end_day"):
            try:
                self.rm.end_day()
            except Exception:
                pass

        log.info(
            f"Backtest finalizado | PnL={self.results['pnl']:.2f} | "
            f"Trades={self.results['trades']} | Wins={self.results['wins']} | "
            f"Losses={self.results['losses']} | "
            f"Signals={self.debug['signals']} Entries={self.debug['entries']} "
            f"Blocked={self.debug['blocked_risk']} TimeBlocked={self.debug['blocked_time']} "
            f"StopCloses={self.debug['stop_closes']} ExitCloses={self.debug['exit_closes']} "
            f"TP={self.debug['tp_hits']} SL={self.debug['sl_hits']}"
        )

        # inclui debug no resultado retornado
        self.results["debug"] = self.debug

        # grava no supabase
        if self.sb.enabled:
            backtest_id = self.sb.insert_backtest({
                "strategy": self.cfg.strategy,
                "symbol": self.cfg.symbol,
                "timeframe": self.cfg.timeframe,
                "initial_balance": self.cfg.initial_balance,
                "final_balance": self.equity,
                "pnl": self.results["pnl"],
                "trades": self.results["trades"],
                "wins": self.results["wins"],
                "losses": self.results["losses"],
                "params": self.cfg.strat_params.__dict__,
            })
            if backtest_id:
                for t in self.trades_log:
                    t["backtest_id"] = backtest_id
                self.sb.insert_trades(self.trades_log)

        return self.results

    def _apply_pnl(self, pnl: float, bar: Dict[str, Any], exit_price: float,
                   pos: Dict[str, Any], close_reason: str):
        """Fecha trade, calcula taxa de forma REALISTA e registra motivo/TP/SL."""
        if not pos:
            pos = {"side": "UNKNOWN", "entry": float(exit_price), "qty": 0.0, "ts": bar.get("ts")}

        # --- TAXAS corretas: sobre notional de entrada + saída ---
        entry_notional = abs(pos["entry"]) * abs(pos["qty"])
        exit_notional  = abs(exit_price) * abs(pos["qty"])
        fee = self.cfg.commission_perc * (entry_notional + exit_notional)

        net = pnl - fee
        self.equity += net
        self.results["pnl"] += net
        self.results["trades"] += 1
        if net >= 0:
            self.results["wins"] += 1
        else:
            self.results["losses"] += 1

        self.rm.register_trade(net)

        # Classificação do stop (tp/sl) quando aplicável
        stop_kind = None
        if close_reason.startswith("stop"):
            sl = pos.get("sl")
            tp = pos.get("tp")
            side = pos.get("side", "UNKNOWN")
            if sl is not None and tp is not None and side in ("LONG", "SHORT"):
                if side == "LONG":
                    if exit_price >= tp: stop_kind = "tp"
                    elif exit_price <= sl: stop_kind = "sl"
                else:
                    if exit_price <= tp: stop_kind = "tp"
                    elif exit_price >= sl: stop_kind = "sl"
            if stop_kind == "tp":
                self.debug["tp_hits"] += 1
            elif stop_kind == "sl":
                self.debug["sl_hits"] += 1

        trade = {
            "entry_time": datetime.utcfromtimestamp(pos.get("ts")/1000).isoformat() if pos.get("ts") else None,
            "exit_time": datetime.utcfromtimestamp(bar.get("ts")/1000).isoformat() if bar.get("ts") else None,
            "side": pos["side"],
            "entry_price": float(pos["entry"]),
            "exit_price": float(exit_price),
            "qty": float(pos["qty"]),
            "pnl": float(net),
            "fee": float(fee),
            "equity": float(self.equity),
            "close_reason": close_reason,
            "stop_kind": stop_kind
        }
        self.trades_log.append(trade)

        print(
            f"Trade #{self.results['trades']}: Side={pos['side']}, "
            f"Entry={pos['entry']}, Exit={exit_price}, Qty={pos['qty']}, "
            f"Fee={fee:.4f}, PnL={net:.2f}, Equity={self.equity:.2f}, Close={close_reason}, Stop={stop_kind}"
        )
