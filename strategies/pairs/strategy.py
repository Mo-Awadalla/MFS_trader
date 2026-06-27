"""Pairs v1 — canonical statistical arbitrage StrategyTemplate."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.contract import StrategyDiagnostics, StrategyTemplate
from strategies.pairs.signal import (
    PairsParams,
    compact_sweep_grid,
    default_params,
    generate_signals,
    params_from_dict,
    params_to_dict,
    sweep_grid,
    validate_inputs,
)

TEMPLATE_VERSION = "v1"


class PairsTradingStrategy(StrategyTemplate[PairsParams]):
    """Dollar-neutral Pairs v1 statistical arbitrage template."""

    name = "pairs_trading"
    template_version = TEMPLATE_VERSION

    def generate_signals(self, df: pd.DataFrame, params: PairsParams | None = None) -> pd.DataFrame:
        self.validate_inputs(df)
        return generate_signals(df, params or self.default_params())

    def default_params(self) -> PairsParams:
        return default_params()

    def sweep_grid(self) -> list[PairsParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[PairsParams]:
        return compact_sweep_grid()

    def diagnose_signals(
        self,
        df: pd.DataFrame,
        params: PairsParams | None = None,
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
            raw_exit_events=int(signals[("portfolio", "exit_count")].sum()),
            filtered_exit_events=int(signals[("portfolio", "exit_count")].sum()),
            entry_signals=int(signals[("portfolio", "entry_count")].sum()),
            exit_signals=int(signals[("portfolio", "exit_count")].sum()),
            bars_held_long=long_cells,
            bars_held_short=short_cells,
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
                "data_shape": "cross_sectional",
                "hypothesis": "cointegrated_spreads_mean_revert",
                "pair_test": "engle_granger",
                "cointegration_pvalue_threshold": params.coint_pvalue_threshold,
                "formation_window_days": params.formation_window_days,
                "min_eligible_universe": params.min_eligible_universe,
                "candidate_pool_size": params.candidate_pool_size,
                "max_active_pairs": params.max_active_pairs,
                "rebalance_rule": "first_trading_session_of_month",
                "skipped_rebalances": int(skipped.sum()),
            },
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_inputs(df)

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume")

    def warmup_bars(self, params: PairsParams | None = None) -> int:
        params = params or self.default_params()
        return max(
            params.min_history_days,
            params.liquidity_lookback_days,
            params.formation_window_days,
        )

    def supports_long(self) -> bool:
        return True

    def supports_short(self) -> bool:
        return True

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template_version": self.template_version,
            "strategy_template_version": self.strategy_template_version,
            "mode": "pairs_trading",
            "data_shape": "cross_sectional",
            "hypothesis": "cointegrated_spreads_mean_revert",
            "asset_class": "us_equities",
            "crypto_included": False,
            "pair_test": "engle_granger",
            "formation_window_days": 252,
            "min_eligible_universe": 100,
            "hedge_ratio": "ols_log_prices_with_intercept",
            "spread": "log_price_y_minus_beta_log_price_x_minus_intercept",
            "normalization": "rolling_zscore",
            "entry_zscore": 2.0,
            "exit_zscore": 0.5,
            "stop_zscore": 4.0,
            "max_holding_days": 60,
            "max_active_pairs": 20,
            "symbol_constraint": "one_active_position_per_symbol",
            "capital": "equal_gross_budget_per_pair",
            "dollar_neutral": True,
            "long_only": False,
            "rebalance_rule": "first_trading_session_of_month",
            "reference_implementation": False,
            "tuning": "none",
        }

    @staticmethod
    def params_to_dict(params: PairsParams) -> dict[str, int | float | bool]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, object]) -> PairsParams:
        return params_from_dict(data)


def get_strategy() -> PairsTradingStrategy:
    return PairsTradingStrategy()
