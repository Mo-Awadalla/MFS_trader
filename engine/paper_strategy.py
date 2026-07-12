"""Fail-closed strategy routing and market-data preparation for paper runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from config.schema import Config, DataConfig
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


@dataclass(frozen=True)
class PreparedPaperStrategy:
    bars: pd.DataFrame
    symbols: tuple[str, ...]
    strategy_name: str
    strategy_params: dict[str, Any]
    strategy_fn: Callable[[pd.DataFrame, dict[str, Any]], dict[str, float]]


def prepare_paper_strategy(
    config: Config,
    experiment: Experiment,
    *,
    frequency: str = "1d",
    load_symbol: Callable[..., pd.DataFrame],
    ma_symbol: str = "AAPL",
    ma_params: dict[str, Any] | None = None,
) -> PreparedPaperStrategy:
    """Prepare the configured strategy only when config and Experiment agree."""

    strategy = config.strategy_name
    if ETF_TSM_STRATEGY in {strategy, experiment.snapshot.strategy} and strategy != experiment.snapshot.strategy:
        raise ValueError(
            f"Configured strategy {strategy!r} disagrees with frozen Experiment "
            f"strategy {experiment.snapshot.strategy!r}"
        )
    if strategy == ETF_TSM_STRATEGY:
        return _prepare_etf_tsm(config, experiment, frequency, load_symbol)
    if strategy in MA_STRATEGIES:
        return _prepare_ma(config, frequency, load_symbol, ma_symbol, ma_params or {})
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
    frozen_params = etf_tsm_params_from_dict(params)
    def strategy_fn(bars: pd.DataFrame, runtime_params: dict[str, Any]) -> dict[str, float]:
        if bars.empty:
            return {}
        if runtime_params != params:
            raise ValueError("ETF TSM runtime parameters disagree with frozen Experiment")
        runtime_symbols = tuple(str(symbol) for symbol in bars.columns.get_level_values(0).unique())
        if runtime_symbols != symbols:
            raise ValueError("ETF TSM runtime panel disagrees with frozen universe")
        signals = generate_etf_tsm_signals(bars, frozen_params)
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
    bars = load_symbol(data_config.storage_dir, symbol, frequency, source="alpaca")

    def strategy_fn(frame: pd.DataFrame, values: dict[str, Any]) -> dict[str, float]:
        ma = MAParams(
            fast_ma_window=int(values.get("fast_ma_window", 20)),
            slow_ma_window=int(values.get("slow_ma_window", 100)),
            trend_filter_active=bool(values.get("trend_filter_active", True)),
            long_only=True,
        )
        signals = generate_ma_signals(frame, ma)
        if signals.empty or "position" not in signals:
            return {}
        return {symbol: float(signals["position"].iloc[-1])}

    return PreparedPaperStrategy(bars, (symbol,), config.strategy_name, params, strategy_fn)


def _panel_data_config(config: Config, symbols: tuple[str, ...]) -> DataConfig:
    expected = set(symbols)
    matches = [item for item in config.data if set(item.symbols) == expected]
    if len(matches) != 1:
        raise ValueError("ETF TSM data config must contain the exact frozen seven-symbol universe")
    return matches[0]
