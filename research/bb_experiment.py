"""BB experiment draft builder — frozen snapshot for registry.create()."""

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
from research.bb_defaults import default_cost_config
from strategies.bb.signal import BBParams, params_to_dict
from strategies.registry import strategy_template_version

PAPER_THRESHOLDS_DEFAULT: dict[str, Any] = {
    "min_calendar_days": 30,
    "min_trades": 100,
    "target_trades": 200,
}


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


def build_bb_experiment_draft(
    df: pd.DataFrame,
    *,
    label: str,
    params: BBParams | None = None,
    symbol: str = "AAPL",
    data_source: str = "alpaca",
    bar_frequency: str = "1d",
    data_version: str | None = None,
    storage_dir: str = "data/parquet/equity",
    cost_config: CostModelConfig | None = None,
    risk_profile: RiskLimits | None = None,
    portfolio_config: PortfolioConfig | None = None,
    random_seed: int = 42,
    config_version: str = "research.toml@0.1.0",
    git_commit: str | None = None,
) -> ExperimentDraft:
    """Build a registry-ready draft from OHLCV bars and BB parameters."""
    from strategies.bb.signal import default_params

    params = params or default_params()
    cost_config = cost_config or default_cost_config()
    risk_profile = risk_profile or RiskLimits()
    portfolio_config = portfolio_config or PortfolioConfig()
    template_version = strategy_template_version("bollinger_bands")

    if data_version is None:
        data_version = f"{data_source}:{symbol}:{bar_frequency}@{len(df)}"

    start = str(df.index.min()) if len(df) else None
    end = str(df.index.max()) if len(df) else None

    snapshot = ExperimentSnapshot(
        strategy="bollinger_bands",
        strategy_template_version=template_version,
        parameters=params_to_dict(params),
        universe=UniverseSpec(
            symbols=(symbol,),
            asset_class="equity",
            selection_rule=None,
            filters={},
        ),
        data_version=DataVersionSpec(
            source=data_source,
            bar_frequency=bar_frequency,
            data_version=data_version,
            adjustment="split_dividend",
            storage_dir=storage_dir,
        ),
        date_range=DateRangeSpec(start=start, end=end),
        execution_mode="next_bar_open",
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
