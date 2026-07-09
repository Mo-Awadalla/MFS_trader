"""Diagnostics and hard gates for the frozen cross-asset carry/trend scout."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from research.cross_asset_carry_trend_scout import (
    ASSET_CLASSES,
    INSTRUMENTS,
    SOURCE_COMMIT,
    CrossAssetCarryTrendParams,
    CrossAssetCarryTrendScoutReport,
    FuturesScoutPath,
    _path_metrics,
    _return_metrics,
    simulate_component,
)


def run_scout(
    panels: dict[str, pd.DataFrame],
    spy_close: pd.Series,
    params: CrossAssetCarryTrendParams | None = None,
) -> CrossAssetCarryTrendScoutReport:
    """Run the one frozen public-data carry/trend scout and hard gates."""

    params = params or CrossAssetCarryTrendParams()
    if set(panels) != set(INSTRUMENTS):
        raise ValueError("scout panels do not match the frozen 15-market universe")

    component_paths: dict[str, dict[str, FuturesScoutPath]] = {}
    component_metrics: dict[str, dict[str, dict[str, float]]] = {}
    for component in ("carry", "trend", "combined"):
        gross = simulate_component(panels, params, component=component, cost_bps=0.0)
        net = simulate_component(
            panels,
            params,
            component=component,
            cost_bps=params.default_cost_bps,
        )
        component_paths[component] = {"gross": gross, "net": net}
        component_metrics[component] = {
            "gross": _path_metrics(gross),
            "default_net": _path_metrics(net),
        }

    combined_gross = component_paths["combined"]["gross"]
    combined_net = component_paths["combined"]["net"]
    split_date = pd.Timestamp("2017-01-01")
    subperiod_returns = {
        "2010_2016": combined_net.returns.loc[combined_net.returns.index < split_date],
        "2017_2024": combined_net.returns.loc[combined_net.returns.index >= split_date],
    }
    subperiod_metrics = {
        name: _return_metrics(returns) for name, returns in subperiod_returns.items()
    }

    class_metrics: dict[str, dict[str, dict[str, float]]] = {}
    class_gross_pnl: dict[str, float] = {}
    class_net_pnl: dict[str, float] = {}
    gross_equity_before = combined_gross.equity.shift(1).fillna(1.0)
    net_equity_before = combined_net.equity.shift(1).fillna(1.0)
    for asset_class, markets in ASSET_CLASSES.items():
        gross_returns = combined_gross.market_gross_returns.loc[:, list(markets)].sum(axis=1)
        net_returns = (
            combined_net.market_gross_returns.loc[:, list(markets)]
            - combined_net.market_costs.loc[:, list(markets)]
        ).sum(axis=1)
        class_metrics[asset_class] = {
            "gross": _return_metrics(gross_returns),
            "default_net": _return_metrics(net_returns),
        }
        class_gross_pnl[asset_class] = float(gross_returns.mul(gross_equity_before).sum())
        class_net_pnl[asset_class] = float(net_returns.mul(net_equity_before).sum())

    absolute_class_pnl = sum(abs(value) for value in class_gross_pnl.values())
    largest_class_share = (
        max(abs(value) for value in class_gross_pnl.values()) / absolute_class_pnl
        if absolute_class_pnl > 0.0
        else 1.0
    )
    asset_class_diagnostics = {
        "metrics": class_metrics,
        "gross_pnl": class_gross_pnl,
        "default_net_pnl": class_net_pnl,
        "largest_absolute_gross_pnl_share": float(largest_class_share),
    }

    leave_one_out: dict[str, dict[str, float]] = {}
    for asset_class, removed_markets in ASSET_CLASSES.items():
        subset = {market: frame for market, frame in panels.items() if market not in removed_markets}
        path = simulate_component(
            subset,
            params,
            component="combined",
            cost_bps=params.default_cost_bps,
            calendar_override=combined_net.returns.index,
        )
        leave_one_out[asset_class] = _path_metrics(path)

    cost_sensitivity: dict[str, dict[str, float]] = {}
    for bps in (0.0, 1.0, 2.0, 5.0):
        path = simulate_component(panels, params, component="combined", cost_bps=bps)
        cost_sensitivity[f"{bps:.1f}"] = _path_metrics(path)

    spy = _normalize_spy_close(spy_close).reindex(combined_net.returns.index).ffill()
    if spy.isna().any():
        raise ValueError("SPY close does not cover the frozen futures analysis calendar")
    spy_returns = spy.pct_change(fill_method=None).fillna(0.0)
    spy_metrics = _return_metrics(spy_returns)
    overlay_returns = {
        "spy_plus_20pct": spy_returns + params.overlay_diagnostic_scale * combined_net.returns,
        "spy_plus_50pct_primary": spy_returns + params.overlay_primary_scale * combined_net.returns,
    }
    overlay_metrics = {
        name: _return_metrics(returns) for name, returns in overlay_returns.items()
    }

    daily_net_pnl = combined_net.returns.mul(net_equity_before)
    monthly_pnl = daily_net_pnl.resample("ME").sum()
    positive_months = monthly_pnl[monthly_pnl > 0.0]
    top_twelve_share = (
        float(positive_months.nlargest(12).sum() / positive_months.sum())
        if float(positive_months.sum()) > 0.0
        else 1.0
    )
    monthly_concentration = {
        "positive_month_count": float(len(positive_months)),
        "best_12_positive_pnl_share": top_twelve_share,
    }

    gross_notional = combined_net.notional_exposure.abs().sum(axis=1)
    portfolio_diagnostics = {
        "mean_daily_turnover": float(combined_net.turnover.mean()),
        "median_daily_turnover": float(combined_net.turnover.median()),
        "max_daily_turnover": float(combined_net.turnover.max()),
        "mean_daily_cost_bps": float(combined_net.costs.mean() * 10_000.0),
        "total_cost_arithmetic_return": float(combined_net.costs.sum()),
        "mean_active_markets": float(combined_net.active_markets.mean()),
        "min_active_markets_when_invested": float(
            combined_net.active_markets[combined_net.active_markets > 0].min()
            if bool((combined_net.active_markets > 0).any())
            else 0.0
        ),
        "mean_gross_notional": float(gross_notional.mean()),
        "max_gross_notional": float(gross_notional.max()),
        "roll_count": float(combined_net.roll_count),
        "rebalance_count": float(combined_net.rebalance_count),
        "spy_daily_correlation": float(combined_net.returns.corr(spy_returns)),
    }

    primary_overlay = overlay_metrics["spy_plus_50pct_primary"]
    combined_gross_metrics = component_metrics["combined"]["gross"]
    combined_net_metrics = component_metrics["combined"]["default_net"]
    gates = {
        "combined_gross_total_return_positive": combined_gross_metrics["total_return"] > 0.0,
        "combined_gross_sharpe_at_least_0_40": combined_gross_metrics["sharpe"] >= 0.40,
        "combined_net_total_return_positive": combined_net_metrics["total_return"] > 0.0,
        "combined_net_sharpe_at_least_0_35": combined_net_metrics["sharpe"] >= 0.35,
        "carry_and_trend_gross_total_returns_positive": all(
            component_metrics[name]["gross"]["total_return"] > 0.0
            for name in ("carry", "trend")
        ),
        "both_subperiods_net_profitable_with_positive_sharpe": all(
            metrics["total_return"] > 0.0 and metrics["sharpe"] > 0.0
            for metrics in subperiod_metrics.values()
        ),
        "all_leave_one_asset_class_out_net_sharpes_positive": all(
            metrics["sharpe"] > 0.0 for metrics in leave_one_out.values()
        ),
        "largest_asset_class_absolute_gross_pnl_share_at_most_60pct": (
            largest_class_share <= 0.60
        ),
        "best_12_months_positive_pnl_share_at_most_50pct": top_twelve_share <= 0.50,
        "combined_profitable_at_5bps": cost_sensitivity["5.0"]["total_return"] > 0.0,
        "primary_overlay_sharpe_not_below_spy": primary_overlay["sharpe"] >= spy_metrics["sharpe"],
        "primary_overlay_drawdown_within_1pct_of_spy": (
            primary_overlay["max_drawdown"] >= spy_metrics["max_drawdown"] - 0.01
        ),
        "primary_overlay_cagr_within_1pct_of_spy": (
            primary_overlay["cagr"] >= spy_metrics["cagr"] - 0.01
        ),
    }

    return CrossAssetCarryTrendScoutReport(
        strategy_name="cross_asset_carry_trend_scout_v1",
        source_commit=SOURCE_COMMIT,
        params=asdict(params),
        analysis_start=combined_net.returns.index.min().date().isoformat(),
        analysis_end=combined_net.returns.index.max().date().isoformat(),
        component_metrics=component_metrics,
        subperiod_metrics=subperiod_metrics,
        asset_class_diagnostics=asset_class_diagnostics,
        leave_one_asset_class_out=leave_one_out,
        cost_sensitivity_bps=cost_sensitivity,
        spy_metrics=spy_metrics,
        overlay_metrics=overlay_metrics,
        portfolio_diagnostics=portfolio_diagnostics,
        monthly_concentration=monthly_concentration,
        gates=gates,
        scout_passed=all(gates.values()),
        limitations=[
            "Public source multiple-price data are curated and stale after 2024-03-28.",
            "The panel lacks complete individual-contract chains, volume, open interest, and exact notice dates.",
            "Source roll calendars may contain maintainer judgment or manual edits.",
            "Back-adjusted point changes and supplied contract mappings are suitable only for falsification research.",
            "A passing scout requires independent raw-contract replication before validation or trading.",
        ],
    )


def _normalize_spy_close(spy_close: pd.Series) -> pd.Series:
    result = pd.to_numeric(spy_close, errors="coerce").copy()
    result.index = pd.DatetimeIndex(result.index).tz_localize(None).normalize()
    return result.loc[~result.index.duplicated(keep="last")].sort_index()
