"""Fail-closed strategy routing and market-data preparation for paper runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from config.schema import Config, DataConfig
from data.catalog import BarRequest, DataCatalog
from experiments.models import Experiment
from strategies.etf_time_series_momentum.signal import (
    generate_signals as generate_etf_tsm_signals,
)
from strategies.etf_time_series_momentum.signal import (
    params_from_dict as etf_tsm_params_from_dict,
)
from strategies.ma.signal import MAParams
from strategies.ma.signal import generate_signals as generate_ma_signals

ETF_TSM_STRATEGY = "etf_time_series_momentum"
MA_STRATEGIES = frozenset({"dual_ma_crossover", "ma"})
NEW_YORK = ZoneInfo("America/New_York")
BROKER_PAPER_EXECUTION_MODE = "broker_market_after_completed_bar_observed_fill"


def completed_daily_bars(
    bars: pd.DataFrame,
    *,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return only daily bars from sessions before the current New York date."""

    if bars.empty:
        return bars
    current = now or pd.Timestamp.now(tz="UTC")
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    current_session_date = current.tz_convert(NEW_YORK).date()
    # Alpaca labels daily equity bars by the UTC calendar date of the session.
    # Current-session partials may arrive at 00:00 UTC, which maps to the prior
    # New York date and must not be interpreted through timezone conversion.
    session_dates = bars.index.date
    return bars.loc[session_dates < current_session_date]


@dataclass(frozen=True)
class PreparedPaperStrategy:
    bars: pd.DataFrame
    symbols: tuple[str, ...]
    strategy_name: str
    strategy_params: dict[str, Any]
    strategy_fn: Callable[[pd.DataFrame, dict[str, Any]], dict[str, float]]


def verify_broker_paper_execution_mode(config: Config, experiment: Experiment) -> None:
    """Reject research fill models the continuous market-order loop cannot promise."""
    if (
        experiment.snapshot.execution_mode != BROKER_PAPER_EXECUTION_MODE
        or not config.engine.bar_close_execution
    ):
        raise ValueError(
            "Unsupported broker-paper execution mode: "
            f"{experiment.snapshot.execution_mode!r}; continuous paper submits market orders "
            "after a completed bar and records observed fills, not guaranteed next-open/close fills"
        )


def verify_paper_strategy_identity(
    config: Config,
    experiment: Experiment,
    *,
    strategy_name: str,
    strategy_params: dict[str, Any],
    symbols: tuple[str, ...],
    frequency: str,
) -> None:
    """Bind strategy/data/cost/risk identity; broker timing is checked separately."""
    snapshot = experiment.snapshot
    if strategy_name not in MA_STRATEGIES | {ETF_TSM_STRATEGY}:
        raise ValueError(f"Unsupported paper strategy {strategy_name!r}")
    costs = asdict(config.cost_model)
    slippage = {key: costs.pop(key) for key in ("slippage_fixed_pct", "slippage_variable_coeff")}
    expected = {
        "strategy": (strategy_name, snapshot.strategy),
        "configured strategy": (config.strategy_name, snapshot.strategy),
        "strategy version": (config.strategy_version, snapshot.strategy_template_version),
        "parameters": (strategy_params, snapshot.parameters),
        "universe": (symbols, snapshot.universe.symbols),
        "frequency": (frequency, snapshot.data_version.bar_frequency),
        "cost model": (costs, snapshot.cost_model),
        "slippage model": (slippage, snapshot.slippage_model),
        "risk profile": (asdict(config.risk_limits), snapshot.risk_profile),
        "portfolio config": (asdict(config.portfolio), snapshot.portfolio_config),
    }
    disagreements = [name for name, (actual, frozen) in expected.items() if actual != frozen]
    if strategy_name in MA_STRATEGIES:
        if strategy_params != asdict(MAParams(**strategy_params)):
            disagreements.append("complete MA parameters")
    else:
        if strategy_params != asdict(etf_tsm_params_from_dict(strategy_params)):
            disagreements.append("complete ETF parameters")
    data = [item for item in config.data if tuple(item.symbols) == symbols]
    if len(data) != 1 or data[0].asset_class.value != snapshot.universe.asset_class:
        disagreements.append("data universe")
    elif data[0].adjustment != snapshot.data_version.adjustment:
        disagreements.append("data adjustment")
    if str(config.raw.get("paper_data_source", "alpaca")) != snapshot.data_version.source:
        disagreements.append("data source")
    if disagreements:
        raise ValueError("Paper runtime disagrees with frozen Experiment: " + ", ".join(disagreements))


def prepare_paper_strategy(
    config: Config,
    experiment: Experiment,
    *,
    frequency: str = "1d",
    load_symbol: Callable[..., pd.DataFrame] | None = None,
    catalog: DataCatalog | None = None,
    ma_symbol: str = "AAPL",
    ma_params: dict[str, Any] | None = None,
) -> PreparedPaperStrategy:
    """Prepare the configured strategy only when config and Experiment agree."""

    strategy = config.strategy_name
    if load_symbol is None:
        data_catalog = catalog or DataCatalog()

        def load_symbol(
            storage_dir: Any,
            symbol: str,
            requested_frequency: str,
            *,
            source: str = "",
        ) -> pd.DataFrame:
            return data_catalog.load(
                BarRequest(
                    storage_dir=storage_dir,
                    symbols=(symbol,),
                    frequency=requested_frequency,
                    source=source,
                )
            ).frame
    if strategy != experiment.snapshot.strategy:
        raise ValueError(
            f"Configured strategy {strategy!r} disagrees with frozen Experiment "
            f"strategy {experiment.snapshot.strategy!r}"
        )
    params = dict(experiment.snapshot.parameters)
    symbols = experiment.snapshot.universe.symbols
    if strategy in MA_STRATEGIES:
        params = asdict(MAParams(**{**params, **(ma_params or {})}))
        symbols = (ma_symbol,)
    verify_paper_strategy_identity(
        config, experiment, strategy_name=strategy, strategy_params=params,
        symbols=symbols, frequency=frequency,
    )
    if strategy == ETF_TSM_STRATEGY:
        return _prepare_etf_tsm(config, experiment, frequency, load_symbol)
    if strategy in MA_STRATEGIES:
        return _prepare_ma(config, frequency, load_symbol, ma_symbol, params)
    raise ValueError(f"paper-run does not support configured strategy {strategy!r}")


def _prepare_etf_tsm(
    config: Config,
    experiment: Experiment,
    frequency: str,
    load_symbol: Callable[..., pd.DataFrame],
) -> PreparedPaperStrategy:
    frozen = config.raw.get("frozen_experiment", {})
    expected = {
        "uuid": experiment.uuid,
        "hash": experiment.experiment_hash,
        "label": experiment.label,
        "strategy": experiment.snapshot.strategy,
        "universe": list(experiment.snapshot.universe.symbols),
        "parameters": experiment.snapshot.parameters,
    }
    disagreements = [key for key, value in expected.items() if frozen.get(key) != value]
    if disagreements:
        raise ValueError(
            "ETF TSM frozen config disagrees with Experiment: " + ", ".join(disagreements)
        )
    symbols = experiment.snapshot.universe.symbols
    data_config = _panel_data_config(config, symbols)
    frames: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    for symbol in symbols:
        try:
            frame = load_symbol(
                data_config.storage_dir,
                symbol,
                frequency,
                source=str(config.raw.get("paper_data_source", "")),
            )
        except (FileNotFoundError, ValueError) as exc:
            failures.append(f"{symbol}: {exc}")
            continue
        if config.raw.get("paper_data_source") == "alpaca" and frequency == "1d":
            frame = completed_daily_bars(frame)
        if frame.empty:
            failures.append(f"{symbol}: empty bars")
        else:
            frames[symbol] = frame.sort_index()
    if failures:
        raise ValueError("ETF TSM partial panel: " + "; ".join(failures))

    latest = {symbol: frame.index[-1] for symbol, frame in frames.items()}
    newest = max(latest.values())
    stale = [symbol for symbol, timestamp in latest.items() if timestamp != newest]
    if stale:
        raise ValueError(f"ETF TSM stale panel members: {', '.join(stale)}")

    panel = pd.concat(frames, axis=1, names=["symbol", "field"], join="inner").sort_index()
    params = dict(experiment.snapshot.parameters)
    strategy_fn = bind_paper_strategy_callable(ETF_TSM_STRATEGY, params, symbols)

    return PreparedPaperStrategy(panel, symbols, ETF_TSM_STRATEGY, params, strategy_fn)


def _prepare_ma(
    config: Config,
    frequency: str,
    load_symbol: Callable[..., pd.DataFrame],
    symbol: str,
    params: dict[str, Any],
) -> PreparedPaperStrategy:
    data_config = next((item for item in config.data if symbol in item.symbols), None)
    if data_config is None:
        raise ValueError(f"No data config contains symbol {symbol}")
    bars = load_symbol(
        data_config.storage_dir, symbol, frequency,
        source=str(config.raw.get("paper_data_source", "alpaca")),
    )

    strategy_fn = bind_paper_strategy_callable(config.strategy_name, params, (symbol,))

    return PreparedPaperStrategy(bars, (symbol,), config.strategy_name, params, strategy_fn)


def bind_paper_strategy_callable(
    strategy_name: str,
    strategy_params: dict[str, Any],
    symbols: tuple[str, ...],
) -> Callable[[pd.DataFrame, dict[str, Any]], dict[str, float]]:
    """Resolve the actual supported implementation, not a caller-declared label."""
    params = dict(strategy_params)
    if strategy_name in MA_STRATEGIES:
        if len(symbols) != 1:
            raise ValueError("MA paper execution requires exactly one frozen symbol")
        frozen_ma = MAParams(**params)
        if asdict(frozen_ma) != params:
            raise ValueError("MA paper execution requires complete frozen parameters")
        symbol = symbols[0]

        def ma_strategy(frame: pd.DataFrame, values: dict[str, Any]) -> dict[str, float]:
            if values != params:
                raise ValueError("MA runtime parameters disagree with frozen Experiment")
            signals = generate_ma_signals(frame, frozen_ma)
            if signals.empty or "position" not in signals:
                return {}
            return {symbol: float(signals["position"].iloc[-1])}

        return ma_strategy
    if strategy_name != ETF_TSM_STRATEGY:
        raise ValueError(f"Unsupported paper strategy {strategy_name!r}")
    frozen_etf = etf_tsm_params_from_dict(params)
    if asdict(frozen_etf) != params:
        raise ValueError("ETF paper execution requires complete frozen parameters")

    def etf_strategy(bars: pd.DataFrame, runtime_params: dict[str, Any]) -> dict[str, float]:
        if runtime_params != params:
            raise ValueError("ETF TSM runtime parameters disagree with frozen Experiment")
        if bars.empty:
            return {}
        runtime_symbols = tuple(str(symbol) for symbol in bars.columns.get_level_values(0).unique())
        if runtime_symbols != symbols:
            raise ValueError("ETF TSM runtime panel disagrees with frozen universe")
        signals = generate_etf_tsm_signals(bars, frozen_etf)
        target_weights = signals.xs("weight", axis=1, level="field").astype(float)
        held_weights = target_weights.shift(1).fillna(0.0)
        eligible = held_weights.index[held_weights.index <= bars.index[-1]]
        if len(eligible) == 0:
            return dict.fromkeys(symbols, 0.0)
        position = held_weights.index.get_loc(eligible[-1])
        row = held_weights.iloc[position].reindex(symbols).fillna(0.0)
        if position > 0 and row.equals(
            held_weights.iloc[position - 1].reindex(symbols).fillna(0.0)
        ):
            return {}
        return {symbol: float(row.loc[symbol]) for symbol in symbols}

    return etf_strategy


def _panel_data_config(config: Config, symbols: tuple[str, ...]) -> DataConfig:
    expected = set(symbols)
    matches = [item for item in config.data if set(item.symbols) == expected]
    if len(matches) != 1:
        raise ValueError("ETF TSM data config must contain the exact frozen seven-symbol universe")
    return matches[0]
