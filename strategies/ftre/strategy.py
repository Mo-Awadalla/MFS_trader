"""FTRE v1 StrategyTemplate adapter."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.contract import StrategyDiagnostics, StrategyTemplate, diagnose_from_signal_frame
from strategies.ftre.signal import (
    REQUIRED_COLUMNS,
    FTREParams,
    compact_sweep_grid,
    default_params,
    generate_signals,
    params_from_dict,
    params_to_dict,
    sweep_grid,
    validate_inputs,
)


class FTREStrategy(StrategyTemplate[FTREParams]):
    name = "funding_time_reversal"
    template_version = "v1"

    def generate_signals(self, df: pd.DataFrame, params: FTREParams | None = None) -> pd.DataFrame:
        return generate_signals(df, params or self.default_params())

    def default_params(self) -> FTREParams:
        return default_params()

    def sweep_grid(self) -> list[FTREParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[FTREParams]:
        return compact_sweep_grid()

    def diagnose_signals(self, df: pd.DataFrame, params: FTREParams | None = None) -> StrategyDiagnostics:
        signals = self.generate_signals(df, params or self.default_params())
        return diagnose_from_signal_frame(signals, bars=len(df), warmup_bars=self.warmup_bars(),
                                          raw_entry_col="raw_entry", raw_exit_col="raw_exit",
                                          extra=self.metadata())

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_inputs(df)

    def required_columns(self) -> tuple[str, ...]:
        return REQUIRED_COLUMNS

    def warmup_bars(self, params: FTREParams | None = None) -> int:
        return 20 * 24 * 12

    def supports_long(self) -> bool:
        return True

    def supports_short(self) -> bool:
        return False

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "template_version": self.template_version,
                "strategy_template_version": self.strategy_template_version,
                "data_shape": "single_asset_funding_event", "bar_frequency": "5min",
                "execution_mode": "settlement_close_signal_next_bar_open", "long_only": True}

    @staticmethod
    def params_to_dict(params: FTREParams) -> dict[str, int | float]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, object]) -> FTREParams:
        return params_from_dict(dict(data))


def get_strategy() -> FTREStrategy:
    return FTREStrategy()
