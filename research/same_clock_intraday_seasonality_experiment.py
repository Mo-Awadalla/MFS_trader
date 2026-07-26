"""SameClockIntradaySeasonalityETF-v1 experiment draft builder."""

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
from strategies.same_clock_intraday_seasonality.signal import (
    SameClockIntradaySeasonalityParams,
    default_params,
    params_to_dict,
)

STRATEGY_NAME = "same_clock_intraday_seasonality"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def default_same_clock_intraday_seasonality_cost_config() -> CostModelConfig:
    """Frozen conservative 30-minute ETF friction assumptions."""
    return CostModelConfig(
        slippage_fixed_pct=0.0006,
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
        "bar_execution_model": "same_clock_signal_prior_bar_execute_next_30m_bar_with_conservative_slippage",
        "flat_by_close_required": True,
    }


def _cost_without_slippage(cost: CostModelConfig) -> dict[str, Any]:
    full = asdict(cost)
    full.pop("slippage_fixed_pct", None)
    full.pop("slippage_variable_coeff", None)
    return full


def build_same_clock_intraday_seasonality_experiment_draft(
    df: pd.DataFrame,
    *,
    label: str,
    params: SameClockIntradaySeasonalityParams | None = None,
    data_source: str = "alpaca_sip_30m_panel",
    bar_frequency: str = "30min",
    data_version: str | None = None,
    storage_dir: str = "data/parquet/same_clock_intraday_seasonality/alpaca_sip",
    cost_config: CostModelConfig | None = None,
    risk_profile: RiskLimits | None = None,
    portfolio_config: PortfolioConfig | None = None,
    random_seed: int = 42,
    config_version: str = "research.toml@0.1.0",
    git_commit: str | None = None,
) -> ExperimentDraft:
    """Build a registry-ready draft for SameClockIntradaySeasonalityETF-v1."""
    params = params or default_params()
    cost_config = cost_config or default_same_clock_intraday_seasonality_cost_config()
    risk_profile = risk_profile or RiskLimits(
        per_position_pct=params.max_symbol_weight,
        max_gross_exposure_pct=params.max_gross,
        max_net_exposure_pct=params.max_gross,
        max_open_positions=3,
        max_daily_loss_pct=0.02,
        block_new_at_daily_loss_pct=0.01,
        max_monthly_loss_pct=0.08,
    )
    portfolio_config = portfolio_config or PortfolioConfig(
        sizing_method="equal_weight_positive_same_clock_etfs",
        execution_mode="intraday_flat_by_close",
        dollar_neutral=False,
        equal_weight=True,
        rebalance_frequency="intraday_30min",
    )
    template_version = strategy_template_version(STRATEGY_NAME)
    symbols = _symbols(df)
    if data_version is None:
        data_version = f"{data_source}:same_clock_intraday_seasonality_v1:{bar_frequency}@{len(df)}x{len(symbols)}"
    start = str(df.index.min()) if len(df) else None
    end = str(df.index.max()) if len(df) else None

    snapshot = ExperimentSnapshot(
        strategy=STRATEGY_NAME,
        strategy_template_version=template_version,
        parameters=params_to_dict(params),
        universe=UniverseSpec(
            symbols=symbols,
            asset_class="equity_etf",
            selection_rule="static_liquid_index_etfs_same_clock_intraday_seasonality_v1",
            filters={
                "symbols": list(symbols),
                "source_memo": "docs/strategy_sources/SameClockIntradaySeasonalityETF-v1.md",
                "lookback_sessions": params.lookback_sessions,
                "min_same_clock_mean_return": params.min_same_clock_mean_return,
                "skip_opening_bars": params.skip_opening_bars,
                "exit_before_close_bars": params.exit_before_close_bars,
                "min_price": params.min_price,
                "min_bar_volume": params.min_bar_volume,
                "flat_by_close": True,
                "long_only": True,
            },
        ),
        data_version=DataVersionSpec(
            source=data_source,
            bar_frequency=bar_frequency,
            data_version=data_version,
            adjustment="split_dividend",
            storage_dir=storage_dir,
        ),
        date_range=DateRangeSpec(start=start, end=end),
        execution_mode="same_clock_signal_prior_bar_execute_next_bar_exit_before_close_no_overnight",
        cost_model=_cost_without_slippage(cost_config),
        slippage_model=_slippage_from_cost(cost_config),
        risk_profile=asdict(risk_profile),
        portfolio_config=asdict(portfolio_config),
        paper_thresholds={
            **dict(PAPER_THRESHOLDS_DEFAULT),
            "min_trading_days": 45,
            "min_completed_executions": 100,
            "flat_by_close_required": True,
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
