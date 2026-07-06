"""ETF tactical momentum StrategyTemplate."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.contract import StrategyDiagnostics, StrategyTemplate
from strategies.etf_tactical.signal import (
    ETFTacticalParams,
    compact_sweep_grid,
    default_params,
    generate_signals,
    params_from_dict,
    params_to_dict,
    sweep_grid,
    validate_inputs,
)

TEMPLATE_VERSION = "v1"


class ETFTacticalMomentumStrategy(StrategyTemplate[ETFTacticalParams]):
    """Long-only ETF tactical absolute/relative momentum template."""

    name = "etf_tactical_momentum"
    template_version = TEMPLATE_VERSION

    def generate_signals(self, df: pd.DataFrame, params: ETFTacticalParams | None = None) -> pd.DataFrame:
        self.validate_inputs(df)
        return generate_signals(df, params or self.default_params())

    def default_params(self) -> ETFTacticalParams:
        return default_params()

    def sweep_grid(self) -> list[ETFTacticalParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[ETFTacticalParams]:
        return compact_sweep_grid()

    def diagnose_signals(
        self,
        df: pd.DataFrame,
        params: ETFTacticalParams | None = None,
    ) -> StrategyDiagnostics:
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
                "insufficient_history": int((signals[("portfolio", "skip_reason")] == "insufficient_history").sum()),
                "insufficient_eligible_universe": int(
                    (signals[("portfolio", "skip_reason")] == "insufficient_eligible_universe").sum()
                ),
            },
            execution_mode="experiment_execution_model",
            extra={
                "strategy_template_version": self.strategy_template_version,
                "data_shape": "cross_sectional_etf_panel",
                "hypothesis": "positive_medium_term_etf_momentum_with_spy_trend_filter",
                "rebalance_rule": "first_trading_session_of_month",
                "short_lookback_days": params.short_lookback_days,
                "long_lookback_days": params.long_lookback_days,
                "trend_ma_days": params.trend_ma_days,
                "skipped_rebalances": int(skipped.sum()),
            },
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_inputs(df)

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume")

    def warmup_bars(self, params: ETFTacticalParams | None = None) -> int:
        params = params or self.default_params()
        return max(
            params.min_history_days,
            params.long_lookback_days + 1,
            params.trend_ma_days,
            params.vol_lookback_days + 1,
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
            "mode": "etf_tactical_momentum",
            "data_shape": "cross_sectional_etf_panel",
            "hypothesis": "positive_medium_term_etf_momentum_with_spy_trend_filter",
            "dollar_neutral": False,
            "long_only": True,
            "rebalance_rule": "first_trading_session_of_month",
            "reference_implementation": False,
        }

    @staticmethod
    def params_to_dict(params: ETFTacticalParams) -> dict[str, int | float]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, object]) -> ETFTacticalParams:
        return params_from_dict(data)


def get_strategy() -> ETFTacticalMomentumStrategy:
    return ETFTacticalMomentumStrategy()
