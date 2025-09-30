# r2d2/portfolio_backtester.py
from __future__ import annotations
from typing import Dict, List, Any, Optional
from copy import deepcopy
from datetime import datetime

import pandas as pd

from r2d2.backtester import Backtester
from r2d2.strategy_manager import StrategyManager

class PortfolioBacktester:
    """
    Executa múltiplos backtests (1 por símbolo) e agrega:
    - trades (com coluna 'symbol')
    - PnL e métricas por símbolo
    - curva de equity do portfólio (somando PnLs conforme as saídas acontecem)
    """
    def __init__(self, base_cfg, exchange_factory, strategy_cfg: Optional[dict] = None):
        """
        base_cfg: AppConfig base (será copiado por símbolo)
        exchange_factory: callable -> instancia do exchange (ex.: lambda: BybitCCXT(testnet=True))
        strategy_cfg: dict opcional para sobrescrever params comuns (allowed_hours/days etc.)
        """
        self.base_cfg = base_cfg
        self.exchange_factory = exchange_factory
        self.strategy_cfg = strategy_cfg or {}

        self.symbol_results: Dict[str, dict] = {}
        self.symbol_trades: Dict[str, List[dict]] = {}
        self.portfolio_trades: List[dict] = []  # trades com 'symbol'
        self.portfolio_equity_curve: Optional[pd.DataFrame] = None
        self.summary: Dict[str, Any] = {}

    def run(self, bars_by_symbol: Dict[str, List[dict]], weights: Optional[Dict[str, float]] = None):
        """
        bars_by_symbol: {symbol: [bars...]}
        weights: pesos por símbolo (soma ~1) para alocação de capital inicial (equal-weight se None).
        """
        symbols = [s for s, bars in bars_by_symbol.items() if bars]
        if not symbols:
            return {"error": "Sem dados para backtest de portfólio."}

        n = len(symbols)
        weights = weights or {s: 1.0 / n for s in symbols}

        # 1) roda cada símbolo isolado (com fração do capital inicial, se desejar)
        for sym in symbols:
            bars = bars_by_symbol[sym]
            cfg = deepcopy(self.base_cfg)

            # alocação do capital inicial por peso (equal-weight por padrão)
            if hasattr(cfg, "initial_balance"):
                cfg.initial_balance = float(self.base_cfg.initial_balance) * float(weights.get(sym, 1.0 / n))

            cfg.symbol = sym

            # aplica overrides de params (ex.: allowed_hours/days)
            if hasattr(cfg, "strat_params") and self.strategy_cfg:
                for k, v in self.strategy_cfg.items():
                    setattr(cfg.strat_params, k, v)

            sm = StrategyManager(cfg.strategy, params=cfg.strat_params.__dict__)
            exchange = self.exchange_factory()

            bt = Backtester(cfg, sm.get(), exchange)
            res = bt.run(bars)

            # guarda
            self.symbol_results[sym] = res
            # anexa trades com o símbolo
            trades = []
            for t in bt.trades_log:
                tt = dict(t)
                tt["symbol"] = sym
                trades.append(tt)
            self.symbol_trades[sym] = trades
            self.portfolio_trades.extend(trades)

        # 2) agrega trades e constrói curva de equity do portfólio
        if not self.portfolio_trades:
            self.summary = {"trades": 0, "pnl": 0.0}
            return self.summary

        df = pd.DataFrame(self.portfolio_trades)
        # ordena por exit_time (ou pela ordem se faltar timestamp)
        if "exit_time" in df.columns:
            df["exit_time"] = pd.to_datetime(df["exit_time"], errors="coerce")
            df = df.sort_values("exit_time", kind="mergesort")
        # equity do portfólio: soma incremental de pnl
        df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce").fillna(0.0)
        df["equity_portfolio"] = float(self.base_cfg.initial_balance) + df["pnl"].cumsum()
        self.portfolio_equity_curve = df[["exit_time", "equity_portfolio"]]

        # 3) métricas agregadas e por símbolo
        trades_total = int(len(df))
        pnl_total = float(df["pnl"].sum())
        wins = int((df["pnl"] > 0).sum())
        losses = int((df["pnl"] < 0).sum())
        wr = float(wins / trades_total * 100.0) if trades_total else 0.0

        # por símbolo
        per_symbol = []
        for sym in symbols:
            d = pd.DataFrame(self.symbol_trades[sym])
            if d.empty:
                per_symbol.append({"symbol": sym, "trades": 0, "net_pnl": 0.0, "win_rate_%": 0.0})
                continue
            pnl_s = d["pnl"].astype(float)
            wins_s = pnl_s[pnl_s > 0].sum()
            losses_s = -pnl_s[pnl_s < 0].sum()
            pf_s = float(wins_s / losses_s) if losses_s > 0 else None
            per_symbol.append({
                "symbol": sym,
                "trades": int(len(d)),
                "net_pnl": float(pnl_s.sum()),
                "win_rate_%": round(float((pnl_s > 0).mean() * 100), 2),
                "profit_factor": round(pf_s, 3) if pf_s is not None else None
            })

        self.summary = {
            "trades": trades_total,
            "wins": wins,
            "losses": losses,
            "pnl": pnl_total,
            "win_rate_%": round(wr, 2),
            "per_symbol": per_symbol,
        }
        return self.summary
