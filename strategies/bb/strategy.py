"""Bollinger Bands — reference StrategyTemplate implementation."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.bb.signal import (
    BBParams,
    compact_sweep_grid,
    default_params,
    generate_signals,
    params_from_dict,
    params_to_dict,
    sweep_grid,
)
from strategies.contract import (
    StrategyDiagnostics,
    StrategyTemplate,
    diagnose_from_signal_frame,
    validate_ohlcv_inputs,
)

TEMPLATE_VERSION = "v2"


class BollingerBandsStrategy(StrategyTemplate[BBParams]):
    """Long-only mean-reversion BB template (reference implementation)."""

    name = "bollinger_bands"
    template_version = TEMPLATE_VERSION

    def generate_signals(self, df: pd.DataFrame, params: BBParams | None = None) -> pd.DataFrame:
        self.validate_inputs(df)
        return generate_signals(df, params or self.default_params())

    def default_params(self) -> BBParams:
        return default_params()

    def sweep_grid(self) -> list[BBParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[BBParams]:
        return compact_sweep_grid()

    def diagnose_signals(self, df: pd.DataFrame, params: BBParams | None = None) -> StrategyDiagnostics:
        params = params or self.default_params()
        signals = self.generate_signals(df, params)
        width_ok_pct = 100.0
        if "width_ok" in signals.columns and len(signals):
            width_ok_pct = round(100.0 * signals["width_ok"].fillna(False).sum() / len(signals), 2)
        return diagnose_from_signal_frame(
            signals,
            bars=len(df),
            warmup_bars=self.warmup_bars(params),
            raw_entry_col="cross_below_lower",
            raw_exit_col="cross_above_middle",
            filter_col="width_ok" if params.width_mode != "none" else None,
            extra={
                "strategy_template_version": self.strategy_template_version,
                "width_mode": params.width_mode,
                "pct_bars_width_ok": width_ok_pct,
            },
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_ohlcv_inputs(df, self.required_columns())

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume")

    def warmup_bars(self, params: BBParams | None = None) -> int:
        params = params or self.default_params()
        if params.width_mode == "none":
            return params.window
        return max(params.window, params.width_lookback)

    def supports_long(self) -> bool:
        return True

    def supports_short(self) -> bool:
        return False

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template_version": self.template_version,
            "strategy_template_version": self.strategy_template_version,
            "mode": "mean_reversion",
            "long_only": True,
            "breakout_supported": False,
            "reference_implementation": True,
        }

    @staticmethod
    def params_to_dict(params: BBParams) -> dict[str, object]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, object]) -> BBParams:
        return params_from_dict(data)


def get_strategy() -> BollingerBandsStrategy:
    return BollingerBandsStrategy()
