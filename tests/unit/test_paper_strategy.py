from __future__ import annotations

from dataclasses import replace

import pandas as pd

from config.loader import load_config
from data.catalog import DataCatalog
from engine.paper_strategy import completed_daily_bars, prepare_paper_strategy
from experiments.registry import ExperimentRegistry

EXPERIMENT_UUID = "119131fa-0f67-48d7-ab87-f20d81c70c1f"
SYMBOLS = ("DBC", "GLD", "IEF", "IWM", "QQQ", "SHY", "SPY")


def test_alpaca_daily_panel_excludes_current_new_york_session():
    bars = pd.DataFrame(
        {"close": [100.0, 101.0]},
        index=pd.to_datetime(["2026-07-13T04:00:00Z", "2026-07-14T00:00:00Z"]),
    )

    completed = completed_daily_bars(
        bars,
        now=pd.Timestamp("2026-07-14T14:30:00Z"),
    )

    assert list(completed.index) == [pd.Timestamp("2026-07-13T04:00:00Z")]


def test_etf_alpaca_route_never_exposes_current_session_bar():
    config = load_config("config/paper_etf_tsm.toml", load_env=False)
    config = replace(config, raw={**config.raw, "paper_data_source": "alpaca"})
    current_session = pd.Timestamp.now(tz="America/New_York").normalize().tz_convert("UTC")
    registry = ExperimentRegistry("experiments")

    def load_symbol(_storage_dir: str, symbol: str, _frequency: str, **_kwargs):
        bars = _bars(symbol)
        bars.loc[current_session] = bars.iloc[-1]
        return bars.sort_index()

    try:
        experiment = registry.get(EXPERIMENT_UUID)
        prepared = prepare_paper_strategy(config, experiment, load_symbol=load_symbol)
    finally:
        registry.close()

    assert current_session not in prepared.bars.index


def _bars(symbol: str) -> pd.DataFrame:
    index = pd.date_range("2023-01-02", periods=260, freq="B", tz="UTC")
    base = float(SYMBOLS.index(symbol) + 10)
    return pd.DataFrame(
        {
            "open": base + pd.Series(range(260), index=index) * 0.01,
            "high": base + 1.0,
            "low": base - 1.0,
            "close": base + pd.Series(range(260), index=index) * 0.01,
            "volume": 1_000_000.0,
        },
        index=index,
    )


def _monthly_open_targets(prepared):
    indices = [
        i
        for i, timestamp in enumerate(prepared.bars.index, start=1)
        if timestamp.day <= 5
    ]
    return [
        (i, prepared.strategy_fn(prepared.bars.iloc[:i], prepared.strategy_params))
        for i in indices
    ]


def test_etf_paper_route_loads_frozen_panel_and_parameters(monkeypatch):
    monkeypatch.setattr(
        "engine.paper_strategy.generate_ma_signals",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("MA route invoked")),
    )
    config = load_config("config/paper_etf_tsm.toml", load_env=False)
    registry = ExperimentRegistry("experiments")
    loaded: list[str] = []

    def load_symbol(_storage_dir: str, symbol: str, _frequency: str, **_kwargs):
        loaded.append(symbol)
        return _bars(symbol)

    try:
        experiment = registry.get(EXPERIMENT_UUID)
        prepared = prepare_paper_strategy(config, experiment, load_symbol=load_symbol)
    finally:
        registry.close()

    assert tuple(loaded) == SYMBOLS
    assert prepared.symbols == SYMBOLS
    assert prepared.strategy_name == "etf_time_series_momentum"
    assert prepared.strategy_params == experiment.snapshot.parameters
    routed_targets = [targets for _, targets in _monthly_open_targets(prepared)]
    assert any(set(targets) == set(SYMBOLS) for targets in routed_targets)


def test_etf_paper_route_emits_targets_only_on_execution_dates():
    config = load_config("config/paper_etf_tsm.toml", load_env=False)
    registry = ExperimentRegistry("experiments")
    try:
        experiment = registry.get(EXPERIMENT_UUID)
        prepared = prepare_paper_strategy(
            config,
            experiment,
            load_symbol=lambda _dir, symbol, _frequency, **_kwargs: _bars(symbol),
        )
    finally:
        registry.close()

    emissions = [i for i, targets in _monthly_open_targets(prepared) if targets]
    assert emissions
    assert all(
        prepared.bars.index[i - 1].month != prepared.bars.index[i - 2].month
        or prepared.bars.index[i - 2].month != prepared.bars.index[i - 3].month
        for i in emissions
        if i > 2
    )


def test_etf_paper_route_fails_closed_on_partial_panel():
    config = load_config("config/paper_etf_tsm.toml", load_env=False)
    registry = ExperimentRegistry("experiments")

    def load_symbol(_storage_dir: str, symbol: str, _frequency: str, **_kwargs):
        if symbol == "GLD":
            raise FileNotFoundError("missing GLD")
        return _bars(symbol)

    try:
        experiment = registry.get(EXPERIMENT_UUID)
        try:
            prepare_paper_strategy(config, experiment, load_symbol=load_symbol)
        except ValueError as exc:
            assert "GLD" in str(exc)
        else:
            raise AssertionError("partial ETF panel was accepted")
    finally:
        registry.close()


def test_etf_paper_route_fails_closed_on_stale_panel_member():
    config = load_config("config/paper_etf_tsm.toml", load_env=False)
    registry = ExperimentRegistry("experiments")

    def load_symbol(_storage_dir: str, symbol: str, _frequency: str, **_kwargs):
        bars = _bars(symbol)
        return bars.iloc[:-1] if symbol == "GLD" else bars

    try:
        experiment = registry.get(EXPERIMENT_UUID)
        try:
            prepare_paper_strategy(config, experiment, load_symbol=load_symbol)
        except ValueError as exc:
            assert "stale" in str(exc).lower()
            assert "GLD" in str(exc)
        else:
            raise AssertionError("stale ETF panel was accepted")
    finally:
        registry.close()


def test_etf_paper_route_fails_closed_when_frozen_config_disagrees():
    config = load_config("config/paper_etf_tsm.toml", load_env=False)
    raw = {**config.raw, "frozen_experiment": {**config.raw["frozen_experiment"], "label": "wrong"}}
    config = replace(config, raw=raw)
    registry = ExperimentRegistry("experiments")
    try:
        experiment = registry.get(EXPERIMENT_UUID)
        try:
            prepare_paper_strategy(config, experiment, load_symbol=lambda *args, **kwargs: _bars(args[1]))
        except ValueError as exc:
            assert "label" in str(exc).lower()
        else:
            raise AssertionError("mismatched frozen config was accepted")
    finally:
        registry.close()


def test_paper_preparation_uses_catalog_for_default_reads(monkeypatch):
    config = load_config("config/paper_etf_tsm.toml", load_env=False)
    registry = ExperimentRegistry("experiments")
    calls = []

    class RecordingCatalog(DataCatalog):
        def load(self, request):
            calls.append(request)
            return type("Loaded", (), {"frame": _bars(request.symbols[0])})()

    try:
        experiment = registry.get(EXPERIMENT_UUID)
        prepared = prepare_paper_strategy(config, experiment, catalog=RecordingCatalog())
    finally:
        registry.close()

    assert prepared.symbols == SYMBOLS
    assert tuple(request.symbols[0] for request in calls) == SYMBOLS
