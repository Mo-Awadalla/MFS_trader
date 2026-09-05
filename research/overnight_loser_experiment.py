"""Overnight loser experiment draft builder — frozen snapshot for registry.create()."""

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
from research.overnight_loser_cost import overnight_loser_cost_config
from strategies.overnight_loser.signal import (
    OvernightLoserParams,
    default_params,
    params_to_dict,
)
from strategies.registry import strategy_template_version

STRATEGY_NAME = "overnight_loser"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _slippage_from_cost(cost: CostModelConfig) -> dict[str, Any]:
    return {
        "slippage_fixed_pct": cost.slippage_fixed_pct,
        "slippage_variable_coeff": cost.slippage_variable_coeff,
    }


def _cost_without_slippage(cost: CostModelConfig) -> dict[str, Any]:
    full = asdict(cost)
    full.pop("slippage_fixed_pct", None)
    full.pop("slippage_variable_coeff", None)
    return full


def build_overnight_loser_experiment_draft(
    df: pd.DataFrame,
    *,
    label: str,
    params: OvernightLoserParams | None = None,
    data_source: str = "research_panel",
    bar_frequency: str = "1d",
    data_version: str | None = None,
    storage_dir: str = "data/parquet/equity/massive_daily",
    cost_config: CostModelConfig | None = None,
    risk_profile: RiskLimits | None = None,
    portfolio_config: PortfolioConfig | None = None,
    random_seed: int = 42,
    config_version: str = "research.toml@0.1.0",
    git_commit: str | None = None,
) -> ExperimentDraft:
    """Build a registry-ready draft for canonical overnight loser v1."""
    params = params or default_params()
    cost_config = cost_config or overnight_loser_cost_config(params)
    risk_profile = risk_profile or RiskLimits(
        max_gross_exposure_pct=params.long_gross + params.short_gross,
        max_net_exposure_pct=params.long_gross,
        max_open_positions=params.num_long_positions + params.num_short_positions,
    )
    portfolio_config = portfolio_config or PortfolioConfig(
        dollar_neutral=False,
        equal_weight=True,
        rebalance_frequency="daily",
    )
    template_version = strategy_template_version(STRATEGY_NAME)
    symbols = _symbols(df)

    if data_version is None:
        data_version = f"{data_source}:{params.universe}:{bar_frequency}@{len(df)}x{len(symbols)}"

    start = str(df.index.min()) if len(df) else None
    end = str(df.index.max()) if len(df) else None

    snapshot = ExperimentSnapshot(
        strategy=STRATEGY_NAME,
        strategy_template_version=template_version,
        parameters=params_to_dict(params),
        universe=UniverseSpec(
            symbols=symbols,
            asset_class="equity",
            selection_rule=f"fixed_etf_universe:{params.universe}",
            filters={
                "price_min": params.min_price,
                "median_dollar_volume_lookback_days": params.liquidity_lookback_days,
                "median_dollar_volume_min": params.min_median_dollar_volume,
                "min_history_days": params.min_history_days,
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
        execution_mode="signal_at_open_enter_open_exit_same_close",
        cost_model=_cost_without_slippage(cost_config),
        slippage_model=_slippage_from_cost(cost_config),
        risk_profile=asdict(risk_profile),
        portfolio_config=asdict(portfolio_config),
        paper_thresholds=dict(PAPER_THRESHOLDS_DEFAULT),
        git_commit=git_commit if git_commit is not None else _git_commit(),
        config_version=config_version,
        random_seed=random_seed,
    )
    return ExperimentDraft(label=label, snapshot=snapshot)


def _symbols(df: pd.DataFrame) -> tuple[str, ...]:
    if not isinstance(df.columns, pd.MultiIndex):
        return ()
    return tuple(sorted(str(symbol) for symbol in df.columns.get_level_values(0).unique()))
