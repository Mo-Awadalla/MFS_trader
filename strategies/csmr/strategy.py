"""CSMR v1 — canonical cross-sectional mean reversion StrategyTemplate."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.contract import StrategyDiagnostics, StrategyTemplate
from strategies.csmr.signal import (
    CSMRParams,
    compact_sweep_grid,
    default_params,
    generate_signals,
    params_from_dict,
    params_to_dict,
    sweep_grid,
    validate_inputs,
)

TEMPLATE_VERSION = "v1"


class CrossSectionalMeanReversionStrategy(StrategyTemplate[CSMRParams]):
    """Dollar-neutral short-term reversal template."""

    name = "cross_sectional_mean_reversion"
    template_version = TEMPLATE_VERSION

    def generate_signals(self, df: pd.DataFrame, params: CSMRParams | None = None) -> pd.DataFrame:
        self.validate_inputs(df)
        return generate_signals(df, params or self.default_params())

    def default_params(self) -> CSMRParams:
        return default_params()

    def sweep_grid(self) -> list[CSMRParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[CSMRParams]:
        return compact_sweep_grid()

    def diagnose_signals(
        self,
        df: pd.DataFrame,
        params: CSMRParams | None = None,
    ) -> StrategyDiagnostics:
        params = params or self.default_params()
        signals = self.generate_signals(df, params)
        weights = signals.xs("weight", axis=1, level="field")
        trades = signals.xs("trade", axis=1, level="field")
        rebalance = signals[("portfolio", "is_rebalance")].astype(bool)
        skipped = signals[("portfolio", "rebalance_skipped")].astype(bool)
        active = weights.abs().sum(axis=1) > 0
        long_cells = int((weights > 0).sum().sum())
        short_cells = int((weights < 0).sum().sum())
        return StrategyDiagnostics(
            bars=len(df),
            warmup_bars=self.warmup_bars(params),
            raw_entry_events=int(rebalance.sum()),
            filtered_entry_events=int((rebalance & ~skipped).sum()),
            raw_exit_events=0,
            filtered_exit_events=0,
            entry_signals=int((trades > 0).sum().sum()),
            exit_signals=int((trades < 0).sum().sum()),
            bars_held_long=long_cells,
            bars_held_short=short_cells,
            pct_time_invested=round(100.0 * active.sum() / len(signals), 2) if len(signals) else 0.0,
            avg_holding_period_bars=0.0,
            turnover=float(trades.abs().sum().sum()),
            rejected_by_reason={
                "insufficient_eligible_universe": int(
                    (signals[("portfolio", "skip_reason")] == "insufficient_eligible_universe").sum()
                )
            },
            execution_mode="experiment_execution_model",
            extra={
                "strategy_template_version": self.strategy_template_version,
                "data_shape": "cross_sectional",
                "lookback_days": params.lookback_days,
                "rebalance_rule": "first_trading_session_of_week",
                "skipped_rebalances": int(skipped.sum()),
            },
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_inputs(df)

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume")

    def warmup_bars(self, params: CSMRParams | None = None) -> int:
        params = params or self.default_params()
        return max(params.min_history_days, params.liquidity_lookback_days, params.lookback_days + 1)

    def supports_long(self) -> bool:
        return True

    def supports_short(self) -> bool:
        return True

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template_version": self.template_version,
            "strategy_template_version": self.strategy_template_version,
            "mode": "cross_sectional_mean_reversion",
            "data_shape": "cross_sectional",
            "hypothesis": "recent_losers_outperform_recent_winners",
            "dollar_neutral": True,
            "long_only": False,
            "rebalance_rule": "first_trading_session_of_week",
            "reference_implementation": False,
        }

    @staticmethod
    def params_to_dict(params: CSMRParams) -> dict[str, int | float]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, object]) -> CSMRParams:
        return params_from_dict(data)


def get_strategy() -> CrossSectionalMeanReversionStrategy:
    return CrossSectionalMeanReversionStrategy()
