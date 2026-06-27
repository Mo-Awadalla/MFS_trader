"""Dual MA crossover — StrategyTemplate implementation."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.contract import (
    StrategyDiagnostics,
    StrategyTemplate,
    diagnose_from_signal_frame,
    validate_ohlcv_inputs,
)
from strategies.ma.signal import (
    MAParams,
    compact_sweep_grid,
    default_params,
    generate_signals,
    sweep_grid,
)

TEMPLATE_VERSION = "v2"


class DualMACrossoverStrategy(StrategyTemplate[MAParams]):
    """Pipeline-validator MA crossover template."""

    name = "dual_ma_crossover"
    template_version = TEMPLATE_VERSION

    def generate_signals(self, df: pd.DataFrame, params: MAParams | None = None) -> pd.DataFrame:
        self.validate_inputs(df)
        return generate_signals(df, params or self.default_params())

    def default_params(self) -> MAParams:
        return default_params()

    def sweep_grid(self) -> list[MAParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[MAParams]:
        return compact_sweep_grid()

    def diagnose_signals(self, df: pd.DataFrame, params: MAParams | None = None) -> StrategyDiagnostics:
        params = params or self.default_params()
        signals = self.generate_signals(df, params)
        return diagnose_from_signal_frame(
            signals,
            bars=len(df),
            warmup_bars=self.warmup_bars(params),
            raw_entry_col="cross_above",
            raw_exit_col="cross_below",
            extra={"strategy_template_version": self.strategy_template_version},
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_ohlcv_inputs(df, self.required_columns())

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume")

    def warmup_bars(self, params: MAParams | None = None) -> int:
        params = params or self.default_params()
        if not params.trend_filter_active:
            return params.slow_ma_window
        return max(params.slow_ma_window, params.trend_filter_window)

    def supports_long(self) -> bool:
        return True

    def supports_short(self) -> bool:
        return True

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template_version": self.template_version,
            "strategy_template_version": self.strategy_template_version,
            "mode": "momentum",
            "long_only_default": True,
            "reference_implementation": False,
        }


def get_strategy() -> DualMACrossoverStrategy:
    return DualMACrossoverStrategy()
