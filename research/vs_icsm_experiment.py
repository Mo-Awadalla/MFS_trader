"""VS-ICSM experiment draft builder — frozen snapshot for registry.create()."""

from __future__ import annotations

import subprocess
from dataclasses import asdict
from typing import Any

import pandas as pd

from config.schema import CostModelConfig, PortfolioConfig, RiskLimits
from experiments.models import (
    DataVersionSpec,
    DateRangeSpec,
    ExperimentDraft,
    ExperimentSnapshot,
    UniverseSpec,
)
from research.bb_experiment import PAPER_THRESHOLDS_DEFAULT
from strategies.registry import strategy_template_version
from strategies.vs_icsm.signal import VSICSMParams, default_params, params_to_dict

STRATEGY_NAME = "volatility_standardized_intraday_momentum"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def default_vs_icsm_cost_config() -> CostModelConfig:
    """Frozen blended Alpaca SIP/hourly limit-order friction assumptions."""
    return CostModelConfig(
        slippage_fixed_pct=0.0004,
        slippage_variable_coeff=0.0,
        commission_pct=0.0,
        sec_fee_per_dollar_sold=20.60 / 1_000_000.0,
        finra_taf_per_share_sold=0.000195,
        borrow_cost_annual_pct=0.0,
    )


def _slippage_from_cost(cost: CostModelConfig) -> dict[str, Any]:
    return {
        "slippage_fixed_pct": cost.slippage_fixed_pct,
        "slippage_variable_coeff": cost.slippage_variable_coeff,
        "limit_order_entry_offset_bps": -5.0,
        "limit_order_exit_offset_bps": 5.0,
        "passive_fill_model": "bar_range_crosses_limit_price_with_adverse_selection_drag",
    }


def _cost_without_slippage(cost: CostModelConfig) -> dict[str, Any]:
    full = asdict(cost)
    full.pop("slippage_fixed_pct", None)
    full.pop("slippage_variable_coeff", None)
    return full


def build_vs_icsm_experiment_draft(
    df: pd.DataFrame,
    *,
    label: str,
    params: VSICSMParams | None = None,
    data_source: str = "alpaca_sip_panel",
    bar_frequency: str = "1h",
    data_version: str | None = None,
    storage_dir: str = "data/parquet/equity_1h",
    cost_config: CostModelConfig | None = None,
    risk_profile: RiskLimits | None = None,
    portfolio_config: PortfolioConfig | None = None,
    random_seed: int = 42,
    config_version: str = "research.toml@0.1.0",
    git_commit: str | None = None,
) -> ExperimentDraft:
    """Build a registry-ready draft for canonical VS-ICSM v1."""
    params = params or default_params()
    cost_config = cost_config or default_vs_icsm_cost_config()
    risk_profile = risk_profile or RiskLimits(
        per_position_pct=params.max_position_weight,
        max_gross_exposure_pct=params.gross_exposure,
        max_net_exposure_pct=params.gross_exposure,
        max_open_positions=params.top_k,
        max_monthly_loss_pct=0.12,
        max_sector_gross_pct=0.40,
    )
    portfolio_config = portfolio_config or PortfolioConfig(
        sizing_method="inverse_atr",
        execution_mode="continuous_rebalance",
        dollar_neutral=False,
        equal_weight=False,
        rebalance_frequency="hourly",
    )
    template_version = strategy_template_version(STRATEGY_NAME)
    symbols = _symbols(df)

    if data_version is None:
        data_version = f"{data_source}:pit_top_liquidity_us_common_stocks:{bar_frequency}@{len(df)}x{len(symbols)}"

    start = str(df.index.min()) if len(df) else None
    end = str(df.index.max()) if len(df) else None

    snapshot = ExperimentSnapshot(
        strategy=STRATEGY_NAME,
        strategy_template_version=template_version,
        parameters=params_to_dict(params),
        universe=UniverseSpec(
            symbols=symbols,
            asset_class="equity",
            selection_rule="monthly_top_200_by_trailing_60_session_median_dollar_volume",
            filters={
                "asset_class": "US common stocks listed on NYSE/NASDAQ; ETFs/ADRs/REITs/SPACs excluded upstream",
                "price_min": params.min_price,
                "price_lookback_sessions": params.price_lookback_sessions,
                "median_dollar_volume_lookback_sessions": params.liquidity_lookback_sessions,
                "universe_size": params.universe_size,
                "transition_buffer_rank": params.transition_buffer_rank,
                "min_hourly_volume": params.min_hourly_volume,
                "min_eligible_symbols": params.min_eligible_symbols,
            },
        ),
        data_version=DataVersionSpec(
            source=data_source,
            bar_frequency=bar_frequency,
            data_version=data_version,
            adjustment="point_in_time_split_dividend",
            storage_dir=storage_dir,
        ),
        date_range=DateRangeSpec(start=start, end=end),
        execution_mode="limit_only_day_orders_signal_at_hourly_close_execute_next_bar_open",
        cost_model=_cost_without_slippage(cost_config),
        slippage_model=_slippage_from_cost(cost_config),
        risk_profile=asdict(risk_profile),
        portfolio_config=asdict(portfolio_config),
        paper_thresholds={
            **dict(PAPER_THRESHOLDS_DEFAULT),
            "min_fill_rate": 0.60,
            "max_round_turn_slippage_bps": 5.0,
            "min_completed_executions": 350,
            "min_trading_days": 45,
        },
        git_commit=git_commit if git_commit is not None else _git_commit(),
        config_version=config_version,
        random_seed=random_seed,
    )
    return ExperimentDraft(label=label, snapshot=snapshot)


def _symbols(df: pd.DataFrame) -> tuple[str, ...]:
    if not isinstance(df.columns, pd.MultiIndex):
        return ()
    return tuple(sorted(str(symbol) for symbol in df.columns.get_level_values(0).unique()))
