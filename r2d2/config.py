from dotenv import load_dotenv
load_dotenv()
from dataclasses import dataclass, field

@dataclass
class SessionConfig:
    use_sessions: bool = False
    sess1: str = "00:00-23:59"
    sess2: str = "00:00-23:59"

@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 0.25
    max_daily_loss_money: float = 2000.0
    max_trades_per_day: int = 20
    use_equity_for_risk: bool = False
    slippage_points: float = 2.0
    fixed_lots: float = 1.0
    lot_per_money: float = 0.0
    break_even_r: float = 1.0
    use_break_even: bool = True
    use_atr_trailing: bool = True
    trail_atr_mult: float = 0.5




@dataclass
class StrategyParams:
    ema_period: int = 20
    atr_period: int = 14
    keltner_mult: float = 1.2
    sl_atr_mult: float = 2.0
    tp_r_mult: float = 3.0
    bars_confirm_break: int = 2
    min_atr_points: float = 10.0
    max_spread_points: float = 3.0
    filter_ema_slope: bool = True
    min_ema_slope_points: float = 5.0

@dataclass
class AppConfig:
    symbol: str = "BTC/USDT:USDT"
    timeframe: str = "1m"
    initial_balance: float = 10000.0
    commission_perc: float = 0.0005
    exchange: str = "bybit"
    strategy: str = "trend_following"
    risk: RiskConfig = field(default_factory=RiskConfig)
    strat_params: StrategyParams = field(default_factory=StrategyParams)
    sessions: SessionConfig = field(default_factory=SessionConfig)
    data_csv: str = ""
    bybit_testnet: bool = True

CONFIG = AppConfig()
