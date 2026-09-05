"""VS-ICSM StrategyTemplate."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.contract import StrategyDiagnostics, StrategyTemplate
from strategies.vs_icsm.signal import (
    VSICSMParams,
    compact_sweep_grid,
    default_params,
    generate_signals,
    params_from_dict,
    params_to_dict,
    sweep_grid,
    validate_inputs,
)

TEMPLATE_VERSION = "v1"


class VSICSMStrategy(StrategyTemplate[VSICSMParams]):
    name = "vs_icsm"
    template_version = TEMPLATE_VERSION

    def generate_signals(self, df: pd.DataFrame, params: VSICSMParams | None = None) -> pd.DataFrame:
        self.validate_inputs(df)
        return generate_signals(df, params or self.default_params())

    def default_params(self) -> VSICSMParams:
        return default_params()

    def sweep_grid(self) -> list[VSICSMParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[VSICSMParams]:
        return compact_sweep_grid()

    def diagnose_signals(self, df: pd.DataFrame, params: VSICSMParams | None = None) -> StrategyDiagnostics:
        params = params or self.default_params()
        signals = self.generate_signals(df, params)
        weights = signals.xs("weight", axis=1, level="field")
        trades = signals.xs("trade", axis=1, level="field")
        rebalance = signals[("portfolio", "is_rebalance")].astype(bool)
        skipped = signals[("portfolio", "rebalance_skipped")].astype(bool)
        active = weights.abs().sum(axis=1) > 0
        return StrategyDiagnostics(
            bars=len(df),
            warmup_bars=self.warmup_bars(params),
            raw_entry_events=int(rebalance.sum()),
            filtered_entry_events=int((rebalance & ~skipped).sum()),
            raw_exit_events=int((trades < 0).sum().sum()),
            filtered_exit_events=int((trades < 0).sum().sum()),
            entry_signals=int((trades > 0).sum().sum()),
            exit_signals=int((trades < 0).sum().sum()),
            bars_held_long=int((weights > 0).sum().sum()),
            bars_held_short=0,
            pct_time_invested=round(100.0 * active.sum() / len(signals), 2) if len(signals) else 0.0,
            avg_holding_period_bars=0.0,
            turnover=float(trades.abs().sum().sum()),
            rejected_by_reason={
                "insufficient_eligible_universe": int(
                    (signals[("portfolio", "skip_reason")] == "insufficient_eligible_universe").sum()
                )
            },
            execution_mode="hourly_close_signal_next_open_limit",
            extra=self.metadata(),
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_inputs(df)

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume")

    def warmup_bars(self, params: VSICSMParams | None = None) -> int:
        params = params or self.default_params()
        return max(
            params.min_history_bars,
            params.liquidity_lookback_bars,
            params.volatility_lookback_bars,
            params.atr_lookback_bars,
        )

    def supports_long(self) -> bool:
        return True

    def supports_short(self) -> bool:
        return False

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template_version": self.template_version,
            "strategy_template_version": self.strategy_template_version,
            "mode": "volatility_scaled_intraday_cross_sectional_momentum",
            "data_shape": "cross_sectional",
            "long_only": True,
            "bar_frequency": "1h",
            "rebalance_rule": "every_hour",
            "reference_implementation": False,
        }

    @staticmethod
    def params_to_dict(params: VSICSMParams) -> dict[str, int | float]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, object]) -> VSICSMParams:
        return params_from_dict(dict(data))


def get_strategy() -> VSICSMStrategy:
    return VSICSMStrategy()
