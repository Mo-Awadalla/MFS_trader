"""Registry-ready frozen FTRE v1 experiment draft."""

from __future__ import annotations

import subprocess
from dataclasses import asdict

import pandas as pd

from config.schema import CostModelConfig, PortfolioConfig, RiskLimits
from experiments.models import (
    DataVersionSpec,
    DateRangeSpec,
    ExperimentDraft,
    ExperimentSnapshot,
    UniverseSpec,
)
from strategies.ftre.signal import FTREParams, default_params, params_to_dict
from strategies.registry import strategy_template_version

STRATEGY_NAME = "funding_time_reversal"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
PAPER_THRESHOLDS = {"min_calendar_days": 30, "min_trades": 30, "target_trades": 50}


def ftre_cost_config() -> CostModelConfig:
    return CostModelConfig(
        slippage_fixed_pct=0.0002,
        slippage_variable_coeff=0.0,
        crypto_taker_fee_pct=0.00045,
        crypto_maker_fee_pct=0.0002,
        borrow_cost_annual_pct=0.0,
    )


def build_ftre_experiment_draft(
    df: pd.DataFrame,
    *,
    label: str,
    params: FTREParams | None = None,
    data_version: str | None = None,
    cost_config: CostModelConfig | None = None,
    random_seed: int = 42,
    git_commit: str | None = None,
) -> ExperimentDraft:
    params = params or default_params()
    cost = cost_config or ftre_cost_config()
    start = str(df.index.min()) if len(df) else None
    end = str(df.index.max()) if len(df) else None
    data_version = data_version or f"binance_vision:usdm_ftre:5min@{len(df)}"
    risk = RiskLimits(per_position_pct=0.05, max_gross_exposure_pct=0.15,
                      max_net_exposure_pct=0.15, max_open_positions=3)
    portfolio = PortfolioConfig(sizing_method="fixed_fraction", execution_mode="signal_transition",
                                per_position_risk_pct=0.05, equal_weight=False,
                                rebalance_frequency="funding_event")
    cost_dict = asdict(cost)
    slippage = {key: cost_dict.pop(key) for key in ("slippage_fixed_pct", "slippage_variable_coeff")}
    snapshot = ExperimentSnapshot(
        strategy=STRATEGY_NAME,
        strategy_template_version=strategy_template_version(STRATEGY_NAME),
        parameters=params_to_dict(params),
        universe=UniverseSpec(symbols=SYMBOLS, asset_class="crypto_perp",
                              selection_rule="fixed_binance_usdm_majors",
                              filters={"venue": "binance_usdm", "leverage": 1,
                                       "long_only": True, "cash_buffer_pct": 0.50}),
        data_version=DataVersionSpec(source="binance_vision", bar_frequency="5min",
                                     data_version=data_version, adjustment="none",
                                     storage_dir="data/parquet/crypto_futures"),
        date_range=DateRangeSpec(start=start, end=end),
        execution_mode="settlement_close_signal_next_bar_open",
        cost_model=cost_dict,
        slippage_model=slippage,
        risk_profile=asdict(risk),
        portfolio_config=asdict(portfolio),
        paper_thresholds=dict(PAPER_THRESHOLDS),
        git_commit=git_commit if git_commit is not None else _git_commit(),
        config_version="ftre_v1@1.0.0",
        random_seed=random_seed,
    )
    return ExperimentDraft(label=label, snapshot=snapshot)


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
