"""Market intraday momentum v1 StrategyTemplate."""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.contract import StrategyDiagnostics, StrategyTemplate
from strategies.market_intraday_momentum.signal import (
    MarketIntradayMomentumParams,
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


class MarketIntradayMomentumStrategy(StrategyTemplate[MarketIntradayMomentumParams]):
    """Long/flat 30-minute market intraday momentum template."""

    name = "market_intraday_momentum"
    template_version = TEMPLATE_VERSION

    def generate_signals(
        self,
        df: pd.DataFrame,
        params: MarketIntradayMomentumParams | None = None,
    ) -> pd.DataFrame:
        params = params or self.default_params()
        self.validate_inputs(df)
        return generate_signals(df, params)

    def default_params(self) -> MarketIntradayMomentumParams:
        return default_params()

    def sweep_grid(self) -> list[MarketIntradayMomentumParams]:
        return sweep_grid()

    def compact_sweep_grid(self) -> list[MarketIntradayMomentumParams]:
        return compact_sweep_grid()

    def diagnose_signals(
        self,
        df: pd.DataFrame,
        params: MarketIntradayMomentumParams | None = None,
    ) -> StrategyDiagnostics:
        params = params or self.default_params()
        signals = self.generate_signals(df, params)
        weights = signals.xs("weight", axis=1, level="field").astype(float)
        trades = signals.xs("trade", axis=1, level="field").astype(float)
        active = weights.abs().sum(axis=1) > 0
        return StrategyDiagnostics(
            bars=len(df),
            warmup_bars=self.warmup_bars(params),
            raw_entry_events=int((trades > 0).sum().sum()),
            filtered_entry_events=int((trades > 0).sum().sum()),
            raw_exit_events=int((trades < 0).sum().sum()),
            filtered_exit_events=int((trades < 0).sum().sum()),
            entry_signals=int((trades > 0).sum().sum()),
            exit_signals=int((trades < 0).sum().sum()),
            bars_held_long=int((weights > 0).sum().sum()),
            bars_held_short=0,
            pct_time_invested=round(100.0 * active.sum() / len(signals), 2) if len(signals) else 0.0,
            avg_holding_period_bars=0.0,
            turnover=float(trades.abs().sum().sum()),
            execution_mode="next_30m_bar_after_signal_close",
            extra={
                "strategy_template_version": self.strategy_template_version,
                "data_shape": "cross_sectional_etf_intraday",
                "bar_frequency": "30min",
                "hypothesis": "first_30m_return_predicts_late_day_continuation",
                "flat_by_close": True,
            },
        )

    def validate_inputs(self, df: pd.DataFrame) -> None:
        validate_inputs(df, self.default_params())

    def required_columns(self) -> tuple[str, ...]:
        return ("open", "high", "low", "close", "volume")

    def warmup_bars(self, params: MarketIntradayMomentumParams | None = None) -> int:
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
            "mode": "market_intraday_momentum",
            "data_shape": "cross_sectional_etf_intraday",
            "asset_class": "equity_etf",
            "bar_frequency": "30min",
            "source_memo": "docs/research_scout/SwingDayTradingStrategySources-v1.md",
            "hypothesis": "first_30m_return_predicts_late_day_continuation",
            "long_only": True,
            "flat_by_close": True,
            "tuning": "none",
        }

    @staticmethod
    def params_to_dict(params: MarketIntradayMomentumParams) -> dict[str, int | float | bool]:
        return params_to_dict(params)

    @staticmethod
    def params_from_dict(data: dict[str, object]) -> MarketIntradayMomentumParams:
        return params_from_dict(data)


def get_strategy() -> MarketIntradayMomentumStrategy:
    return MarketIntradayMomentumStrategy()
