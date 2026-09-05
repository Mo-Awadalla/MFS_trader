"""VS-ICSM experiment draft builder."""

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

STRATEGY_NAME = "vs_icsm"


def vs_icsm_cost_config() -> CostModelConfig:
    return CostModelConfig(
        slippage_fixed_pct=0.0003,
        slippage_variable_coeff=0.0,
        commission_pct=0.0,
        sec_fee_per_dollar_sold=20.60 / 1_000_000.0,
        finra_taf_per_share_sold=0.000195,
        borrow_cost_annual_pct=0.0,
    )


def build_vs_icsm_experiment_draft(
    df: pd.DataFrame,
    *,
    label: str,
    params: VSICSMParams | None = None,
    data_source: str = "alpaca_sip",
    bar_frequency: str = "1h",
    data_version: str | None = None,
    storage_dir: str = "data/parquet/equity",
    cost_config: CostModelConfig | None = None,
    risk_profile: RiskLimits | None = None,
    portfolio_config: PortfolioConfig | None = None,
    random_seed: int = 42,
    config_version: str = "research.toml@0.1.0",
    git_commit: str | None = None,
) -> ExperimentDraft:
    params = params or default_params()
    cost_config = cost_config or vs_icsm_cost_config()
    risk_profile = risk_profile or RiskLimits(
        max_gross_exposure_pct=1.0,
        max_net_exposure_pct=1.0,
        max_open_positions=params.k_names,
    )
    portfolio_config = portfolio_config or PortfolioConfig(
        dollar_neutral=False,
        equal_weight=False,
        rebalance_frequency="daily",
    )
    symbols = _symbols(df)
    if data_version is None:
        data_version = f"{data_source}:top200_liquid_us_equities:{bar_frequency}@{len(df)}x{len(symbols)}"
    start = str(df.index.min()) if len(df) else None
    end = str(df.index.max()) if len(df) else None
    snapshot = ExperimentSnapshot(
        strategy=STRATEGY_NAME,
        strategy_template_version=strategy_template_version(STRATEGY_NAME),
        parameters=params_to_dict(params),
        universe=UniverseSpec(
            symbols=symbols,
            asset_class="equity",
            selection_rule="top_200_by_60_day_median_dollar_volume_each_hour",
            filters={
                "exclude_etfs": True,
                "exclude_adrs": True,
                "exclude_reits": True,
                "exclude_spacs": True,
                "min_price": params.min_price,
                "liquidity_lookback_bars": params.liquidity_lookback_bars,
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
        execution_mode="hourly_close_signal_next_open_limit",
        cost_model=_cost_without_slippage(cost_config),
        slippage_model={
            "mega_large_slippage_pct": 0.0003,
            "mid_slippage_pct": 0.0005,
        },
        risk_profile=asdict(risk_profile),
        portfolio_config=asdict(portfolio_config),
        paper_thresholds=dict(PAPER_THRESHOLDS_DEFAULT),
        git_commit=git_commit if git_commit is not None else _git_commit(),
        config_version=config_version,
        random_seed=random_seed,
    )
    return ExperimentDraft(label=label, snapshot=snapshot)


def _cost_without_slippage(cost: CostModelConfig) -> dict[str, Any]:
    full = asdict(cost)
    full.pop("slippage_fixed_pct", None)
    full.pop("slippage_variable_coeff", None)
    return full


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _symbols(df: pd.DataFrame) -> tuple[str, ...]:
    if not isinstance(df.columns, pd.MultiIndex):
        return ()
    return tuple(sorted(str(symbol) for symbol in df.columns.get_level_values(0).unique()))
