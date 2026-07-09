"""FundamentalEventSmartReversal v1 StrategyTemplate."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.contract import StrategyDiagnostics, StrategyTemplate
from strategies.fundamental_event_smart_reversal.signal import (
    FundamentalEventSmartReversalParams,
    compact_sweep_grid,
    default_params,
    generate_signals,
    params_from_dict,
    params_to_dict,
    sweep_grid,
    validate_inputs,
    warmup_bars,
)

TEMPLATE_VERSION = "v1"


class FundamentalEventSmartReversalStrategy(
    StrategyTemplate[FundamentalEventSmartReversalParams]
):
    """Daily dollar-neutral smart reversal with point-in-time SEC event vetoes."""

    name = "fundamental_event_smart_reversal"
    template_version = TEMPLATE_VERSION

    def generate_signals(
        self,
        df: pd.DataFrame,
        params: FundamentalEventSmartReversalParams | None = None,
    ) -> pd.DataFrame:
        return generate_signals(df, params or self.default_params())

    def default_params(self) -> FundamentalEventSmartReversalParams:
        return default_params()

    def sweep_grid(self) -> list[FundamentalEventSmartReversalParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[FundamentalEventSmartReversalParams]:
        return compact_sweep_grid()

    def diagnose_signals(
        self,
        df: pd.DataFrame,
        params: FundamentalEventSmartReversalParams | None = None,
    ) -> StrategyDiagnostics:
        params = params or self.default_params()
        signals = self.generate_signals(df, params)
        weights = signals.xs("weight", axis=1, level="field").astype(float)
        trades = signals.xs("trade", axis=1, level="field").astype(float)
        rebalance = signals[("portfolio", "is_rebalance")].astype(bool)
        skipped = signals[("portfolio", "rebalance_skipped")].astype(bool)
        active = weights.abs().sum(axis=1) > 0.0
        return StrategyDiagnostics(
            bars=len(df),
            warmup_bars=self.warmup_bars(params),
            raw_entry_events=int(rebalance.sum()),
            filtered_entry_events=int((rebalance & ~skipped).sum()),
            raw_exit_events=int((trades != 0.0).sum().sum()),
            filtered_exit_events=int((trades < 0.0).sum().sum()),
            entry_signals=int((trades > 0.0).sum().sum()),
            exit_signals=int((trades < 0.0).sum().sum()),
            bars_held_long=int((weights > 0.0).sum().sum()),
            bars_held_short=int((weights < 0.0).sum().sum()),
            pct_time_invested=round(100.0 * float(active.mean()), 2) if len(active) else 0.0,
            avg_holding_period_bars=_average_holding_period(weights),
            turnover=float(trades.abs().sum().sum()),
            rejected_by_reason={
                "insufficient_history": int(
                    (signals[("portfolio", "skip_reason")] == "insufficient_history").sum()
                ),
                "insufficient_eligible_universe": int(
                    (
                        signals[("portfolio", "skip_reason")]
                        == "insufficient_eligible_universe"
                    ).sum()
                ),
                "event_vetoed_symbol_days": int(
                    signals[("portfolio", "event_vetoed_count")].astype(int).sum()
                ),
            },
            execution_mode="experiment_execution_model",
            extra={
                "strategy_template_version": self.strategy_template_version,
                "data_shape": "cross_sectional_event_panel",
                "rebalance_rule": "daily",
                "entry_fraction": params.entry_fraction,
                "exit_percentile": params.exit_percentile,
                "event_veto_sessions": params.event_veto_sessions,
                "event_forced_exits": int(
                    signals[("portfolio", "event_forced_exit_count")].astype(int).sum()
                ),
                "skipped_rebalances": int(skipped.sum()),
            },
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_inputs(df)

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume", "fundamental_event")

    def warmup_bars(
        self,
        params: FundamentalEventSmartReversalParams | None = None,
    ) -> int:
        return warmup_bars(params or self.default_params())

    def supports_long(self) -> bool:
        return True

    def supports_short(self) -> bool:
        return True

    def metadata(self) -> dict[str, Any]:
        params = self.default_params()
        return {
            "name": self.name,
            "template_version": self.template_version,
            "strategy_template_version": self.strategy_template_version,
            "mode": "fundamental_event_smart_reversal",
            "data_shape": "cross_sectional_event_panel",
            "hypothesis": "non_event_extreme_short_term_returns_revert_with_rank_buffer_exits",
            "dollar_neutral": True,
            "long_only": False,
            "rebalance_rule": "daily",
            "event_field": "fundamental_event",
            "entry_fraction": params.entry_fraction,
            "exit_percentile": params.exit_percentile,
            "reference_implementation": False,
        }

    @staticmethod
    def params_to_dict(params: FundamentalEventSmartReversalParams) -> dict[str, Any]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, Any]) -> FundamentalEventSmartReversalParams:
        return params_from_dict(data)


def _average_holding_period(weights: pd.DataFrame) -> float:
    durations: list[int] = []
    for symbol in weights.columns:
        signs = weights[symbol].map(lambda value: 1 if value > 0 else (-1 if value < 0 else 0))
        active_sign = 0
        duration = 0
        for sign in signs:
            if sign == active_sign and sign != 0:
                duration += 1
            else:
                if active_sign != 0 and duration:
                    durations.append(duration)
                active_sign = int(sign)
                duration = 1 if sign != 0 else 0
        if active_sign != 0 and duration:
            durations.append(duration)
    return round(float(pd.Series(durations).mean()), 2) if durations else 0.0


def get_strategy() -> FundamentalEventSmartReversalStrategy:
    return FundamentalEventSmartReversalStrategy()
