"""VS-ICSM v1 — frozen intraday cross-sectional momentum StrategyTemplate."""

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
    warmup_bars,
)

TEMPLATE_VERSION = "v1"


class VolatilityStandardizedICSMStrategy(StrategyTemplate[VSICSMParams]):
    """Long-only hourly cross-sectional momentum template."""

    name = "volatility_standardized_intraday_momentum"
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

    def diagnose_signals(
        self,
        df: pd.DataFrame,
        params: VSICSMParams | None = None,
    ) -> StrategyDiagnostics:
        params = params or self.default_params()
        signals = self.generate_signals(df, params)
        weights = signals.xs("weight", axis=1, level="field").astype(float)
        trades = signals.xs("trade", axis=1, level="field").astype(float)
        rebalance = signals[("portfolio", "is_rebalance")].astype(bool)
        skipped = signals[("portfolio", "rebalance_skipped")].astype(bool)
        active = weights.abs().sum(axis=1) > 0
        long_cells = int((weights > 0).sum().sum())
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
            bars_held_short=0,
            pct_time_invested=round(100.0 * active.sum() / len(signals), 2) if len(signals) else 0.0,
            avg_holding_period_bars=0.0,
            turnover=float(trades.abs().sum().sum()),
            rejected_by_reason={
                "insufficient_history": int(
                    (signals[("portfolio", "skip_reason")] == "insufficient_history").sum()
                ),
                "insufficient_eligible_universe": int(
                    (signals[("portfolio", "skip_reason")] == "insufficient_eligible_universe").sum()
                ),
            },
            execution_mode="experiment_execution_model",
            extra={
                "strategy_template_version": self.strategy_template_version,
                "data_shape": "cross_sectional",
                "hypothesis": "volatility_standardized_intraday_order_flow_persistence",
                "bar_frequency": "1h",
                "rebalance_rule": "every_hourly_bar_close",
                "universe_rule": "monthly_top_liquidity_with_rank_220_buffer",
                "skipped_rebalances": int(skipped.sum()),
            },
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_inputs(df)

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume")

    def warmup_bars(self, params: VSICSMParams | None = None) -> int:
        return warmup_bars(params or self.default_params())

    def supports_long(self) -> bool:
        return True

    def supports_short(self) -> bool:
        return False

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template_version": self.template_version,
            "strategy_template_version": self.strategy_template_version,
            "mode": "vs_icsm",
            "data_shape": "cross_sectional",
            "asset_class": "us_equities",
            "bar_frequency": "1h",
            "hypothesis": "volatility_standardized_intraday_order_flow_persistence",
            "momentum_lookback_bars": 6,
            "volatility_lookback_bars": 13,
            "top_k": 15,
            "dollar_neutral": False,
            "long_only": True,
            "order_type": "limit_only_day",
            "entry_limit_offset_bps": -5.0,
            "exit_limit_offset_bps": 5.0,
            "cash_buffer_pct": 0.02,
            "max_position_weight": 0.15,
            "tuning": "none",
            "reference_implementation": False,
        }

    @staticmethod
    def params_to_dict(params: VSICSMParams) -> dict[str, int | float]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, object]) -> VSICSMParams:
        return params_from_dict(data)


def get_strategy() -> VolatilityStandardizedICSMStrategy:
    return VolatilityStandardizedICSMStrategy()
