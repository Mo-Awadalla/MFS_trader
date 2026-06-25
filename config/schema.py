"""Config schema for the MFS trading system.

All configs share a common shape. Environment-specific overrides live in
config/{research,paper,live}.toml. Secrets are NEVER in TOML — they come
from environment variables via the loader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Mode(StrEnum):
    RESEARCH = "research"
    PAPER = "paper"
    LIVE = "live"


class AssetClass(StrEnum):
    EQUITY = "equity"
    CRYPTO = "crypto"


@dataclass(frozen=True)
class BrokerConfig:
    name: str  # "alpaca" | "ccxt_binance" | "sim_broker"
    asset_class: AssetClass
    api_key_env: str  # env var name, never the key itself
    api_secret_env: str
    base_url: str
    data_url: str | None = None
    is_paper: bool = True


@dataclass(frozen=True)
class DataConfig:
    symbols: list[str]
    asset_class: AssetClass
    bar_frequency_raw: str = "1min"  # raw storage frequency
    target_frequencies: list[str] = field(default_factory=lambda: ["1h", "1d"])
    start_date: str = "2020-01-01"
    end_date: str | None = None
    adjustment: str = "split_dividend"  # for equities
    exchange: str | None = None  # for crypto venue tagging
    storage_dir: str = "data/parquet"
    min_volume: float = 0.0
    price_floor: float = 0.0


@dataclass(frozen=True)
class RiskLimits:
    per_position_pct: float = 0.01  # 1% of equity
    max_daily_loss_pct: float = 0.03
    block_new_at_daily_loss_pct: float = 0.02
    max_weekly_loss_pct: float = 0.06
    max_monthly_loss_pct: float = 0.15  # hard halt
    max_gross_exposure_pct: float = 1.5  # 150% of equity
    max_net_exposure_pct: float = 0.10
    max_beta_adjusted_net_pct: float = 0.10
    max_sector_gross_pct: float = 0.35
    max_sector_net_pct: float = 0.10
    max_correlated_cluster_gross_pct: float = 0.35
    max_correlated_cluster_risk_pct: float = 0.03
    correlation_threshold: float = 0.70
    max_open_positions: int = 15
    max_open_positions_live_phase1: int = 10


@dataclass(frozen=True)
class PortfolioConfig:
    sizing_method: str = "fixed_fraction"  # fixed_fraction | vol_target | kelly
    execution_mode: str = "signal_transition"  # signal_transition | continuous_rebalance
    per_position_risk_pct: float = 0.01
    dollar_neutral: bool = False
    equal_weight: bool = True
    rebalance_frequency: str = "daily"  # daily | weekly
    min_notional_delta: float = 25.0
    min_qty_delta: float = 1e-6
    min_pct_position_delta: float = 0.05


@dataclass(frozen=True)
class CostModelConfig:
    slippage_fixed_pct: float = 0.0005
    slippage_variable_coeff: float = 0.5  # impact = coeff * trade_size / adv
    commission_pct: float = 0.0
    sec_fee_per_dollar_sold: float = 5.1e-6  # ~$5.10 per $1M
    finra_taf_per_share_sold: float = 0.000119
    crypto_taker_fee_pct: float = 0.001
    crypto_maker_fee_pct: float = 0.0007
    borrow_cost_annual_pct: float = 0.01  # for shorts


@dataclass(frozen=True)
class MonitoringConfig:
    dashboard_enabled: bool = False
    dashboard_port: int = 8501
    telegram_alerts: bool = False
    telegram_bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str = "TELEGRAM_CHAT_ID"
    alert_cooldown_minutes: int = 10
    alert_escalation_minutes: int = 30
    heartbeat_interval_seconds: int = 30
    watchdog_enabled: bool = False
    watchdog_heartbeat_timeout_seconds: int = 120


@dataclass(frozen=True)
class EngineConfig:
    bar_close_execution: bool = True  # signals at bar close, exec next bar
    reconciliation_interval_minutes: int = 60
    startup_reconciliation_required: bool = True
    kill_switch_persistent: bool = True
    graceful_shutdown_timeout_seconds: int = 30
    max_consecutive_losses_before_halt: int = 20


@dataclass(frozen=True)
class LiveDeploymentConfig:
    authorized: bool = False  # must be explicitly set true for live
    max_live_capital: float = 0.0
    starting_capital: float = 0.0
    strategy_capital_limit: float = 0.0
    paper_submit_enabled: bool = False
    max_paper_notional: float = 0.0
    max_notional_per_order: float = 0.0
    max_strategy_capital: float = 0.0
    allow_short: bool = False
    paper_order_type: str = "limit"  # limit | market
    paper_limit_offset_pct: float = 0.001
    paper_cancel_open_order_after_submit: bool = False
    paper_session_count: int = 1
    initial_capital_fraction: float = 0.15  # 10-25% phase 1
    dry_run_mode: bool = False  # real data, read-only broker, no order submit
    single_strategy_first_live: bool = True
    promotion_status: str = "research"  # research|research_passed|paper|live_candidate|live|suspended|retired


@dataclass(frozen=True)
class Config:
    mode: Mode
    brokers: list[BrokerConfig]
    data: list[DataConfig]  # one per asset class / source
    risk_limits: RiskLimits
    portfolio: PortfolioConfig
    cost_model: CostModelConfig
    monitoring: MonitoringConfig
    engine: EngineConfig
    live_deployment: LiveDeploymentConfig
    artifacts_dir: str = "~/trading_artifacts"
    strategy_name: str = ""
    strategy_version: str = "0.0.0"
    strategies_enabled: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
