"""OpeningRangeBreakoutETF-v1 StrategyTemplate."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.contract import StrategyDiagnostics, StrategyTemplate
from strategies.opening_range_breakout.signal import (
    OpeningRangeBreakoutParams,
    compact_sweep_grid,
    default_params,
    generate_signals,
    params_from_dict,
    params_to_dict,
    sweep_grid,
    validate_inputs,
)

TEMPLATE_VERSION = "v1"


class OpeningRangeBreakoutStrategy(StrategyTemplate[OpeningRangeBreakoutParams]):
    """Long-only 30-minute ETF opening-range breakout template."""

    name = "opening_range_breakout"
    template_version = TEMPLATE_VERSION

    def generate_signals(
        self,
        df: pd.DataFrame,
        params: OpeningRangeBreakoutParams | None = None,
    ) -> pd.DataFrame:
        params = params or self.default_params()
        self.validate_inputs(df)
        return generate_signals(df, params)

    def default_params(self) -> OpeningRangeBreakoutParams:
        return default_params()

    def sweep_grid(self) -> list[OpeningRangeBreakoutParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[OpeningRangeBreakoutParams]:
        return compact_sweep_grid()

    def diagnose_signals(
        self,
        df: pd.DataFrame,
        params: OpeningRangeBreakoutParams | None = None,
    ) -> StrategyDiagnostics:
        params = params or self.default_params()
        signals = self.generate_signals(df, params)
        weights = signals.xs("weight", axis=1, level="field").astype(float)
        trades = signals.xs("trade", axis=1, level="field").astype(float)
        rebalance = signals[("portfolio", "is_rebalance")].astype(bool)
        skipped = signals[("portfolio", "rebalance_skipped")].astype(bool)
        active = weights.abs().sum(axis=1) > 0
        return StrategyDiagnostics(
            bars=len(df),
            warmup_bars=self.warmup_bars(params),
            raw_entry_events=int(rebalance.sum()),
            filtered_entry_events=int((rebalance & ~skipped).sum()),
            raw_exit_events=0,
            filtered_exit_events=0,
            entry_signals=int((trades > 0).sum().sum()),
            exit_signals=int((trades < 0).sum().sum()),
            bars_held_long=int((weights > 0).sum().sum()),
            bars_held_short=0,
            pct_time_invested=round(100.0 * active.sum() / len(signals), 2) if len(signals) else 0.0,
            avg_holding_period_bars=0.0,
            turnover=float(trades.abs().sum().sum()),
            rejected_by_reason={
                "incomplete_session": int(
                    (signals[("portfolio", "skip_reason")] == "incomplete_session").sum()
                ),
            },
            execution_mode="experiment_execution_model",
            extra={
                "strategy_template_version": self.strategy_template_version,
                "data_shape": "cross_sectional_intraday_etf_panel",
                "hypothesis": "first_hour_opening_range_breakout_intraday_continuation",
                "rebalance_rule": "30m_breakout_then_flat_by_close",
                "opening_range_bars": params.opening_range_bars,
                "exit_before_close_bars": params.exit_before_close_bars,
                "breakout_buffer_pct": params.breakout_buffer_pct,
                "skipped_rebalances": int(skipped.sum()),
            },
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_inputs(df)

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume")

    def warmup_bars(self, params: OpeningRangeBreakoutParams | None = None) -> int:
        params = params or self.default_params()
        return params.opening_range_bars

    def supports_long(self) -> bool:
        return True

    def supports_short(self) -> bool:
        return False

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template_version": self.template_version,
            "strategy_template_version": self.strategy_template_version,
            "mode": "opening_range_breakout_etf",
            "data_shape": "cross_sectional_intraday_etf_panel",
            "hypothesis": "first_hour_opening_range_breakout_intraday_continuation",
            "dollar_neutral": False,
            "long_only": True,
            "rebalance_rule": "30m_breakout_then_flat_by_close",
            "source_memo": "docs/strategy_sources/OpeningRangeBreakoutETF-v1.md",
            "reference_implementation": False,
        }

    @staticmethod
    def params_to_dict(params: OpeningRangeBreakoutParams) -> dict[str, int | float | bool]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, object]) -> OpeningRangeBreakoutParams:
        return params_from_dict(data)


def get_strategy() -> OpeningRangeBreakoutStrategy:
    return OpeningRangeBreakoutStrategy()
