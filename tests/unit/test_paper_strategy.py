from __future__ import annotations

from dataclasses import asdict, replace

import pandas as pd
import pytest

from config.loader import load_config
from data.catalog import DataCatalog
from engine.paper_strategy import (
    BROKER_PAPER_EXECUTION_MODE,
    completed_daily_bars,
    prepare_paper_strategy,
    verify_broker_paper_execution_mode,
)
from experiments.models import DataVersionSpec, DateRangeSpec, ExperimentDraft, ExperimentSnapshot, UniverseSpec
from experiments.registry import ExperimentRegistry
from strategies.ma.signal import MAParams

SYMBOLS = ("DBC", "GLD", "IEF", "IWM", "QQQ", "SHY", "SPY")


def snapshot_for_config(config, *, parameters, symbols, source="alpaca", execution_mode=BROKER_PAPER_EXECUTION_MODE):
    costs = asdict(config.cost_model)
    slippage = {key: costs.pop(key) for key in ("slippage_fixed_pct", "slippage_variable_coeff")}
    return ExperimentSnapshot(
        strategy=config.strategy_name, strategy_template_version=config.strategy_version,
        parameters=parameters, universe=UniverseSpec(symbols=symbols, asset_class="equity"),
        data_version=DataVersionSpec(source=source, bar_frequency="1d", data_version="synthetic-test", adjustment="split_dividend"),
        date_range=DateRangeSpec(), execution_mode=execution_mode, cost_model=costs,
        slippage_model=slippage, risk_profile=asdict(config.risk_limits), portfolio_config=asdict(config.portfolio),
        paper_thresholds={}, git_commit="synthetic", config_version="test", random_seed=1,
    )


@pytest.fixture
def etf(tmp_path):
    config = load_config("config/paper_etf_tsm.toml", load_env=False)
    snapshot = snapshot_for_config(config, parameters=dict(config.raw["frozen_experiment"]["parameters"]), symbols=SYMBOLS, source="yahoo_chart")
    registry = ExperimentRegistry(tmp_path / "experiments")
    experiment = registry.create(ExperimentDraft(label="synthetic ETF", snapshot=snapshot))
    frozen = dict(uuid=experiment.uuid, hash=experiment.experiment_hash, label=experiment.label,
                  strategy=snapshot.strategy, universe=list(SYMBOLS), parameters=snapshot.parameters)
    config = replace(config, raw={**config.raw, "frozen_experiment": frozen})
    yield config, experiment
    registry.close()


def _bars(symbol):
    index = pd.date_range("2023-01-02", periods=260, freq="B", tz="UTC")
    base = float(SYMBOLS.index(symbol) + 10) if symbol in SYMBOLS else 100.0
    return pd.DataFrame({"open": base + pd.Series(range(260), index=index) * .01,
                         "high": base + 1, "low": base - 1,
                         "close": base + pd.Series(range(260), index=index) * .01,
                         "volume": 1_000_000.0}, index=index)


def test_alpaca_daily_panel_excludes_current_new_york_session():
    bars = pd.DataFrame({"close": [100., 101.]}, index=pd.to_datetime(["2026-07-13T04:00:00Z", "2026-07-14T00:00:00Z"]))
    completed = completed_daily_bars(bars, now=pd.Timestamp("2026-07-14T14:30:00Z"))
    assert list(completed.index) == [pd.Timestamp("2026-07-13T04:00:00Z")]


def test_etf_paper_route_loads_frozen_panel_and_parameters(etf, monkeypatch):
    config, experiment = etf
    def forbidden(*args, **kwargs):
        raise AssertionError("MA route invoked")
    monkeypatch.setattr("engine.paper_strategy.generate_ma_signals", forbidden)
    loaded = []
    def load_symbol(_dir, symbol, _frequency, **kwargs):
        loaded.append(symbol)
        return _bars(symbol)
    prepared = prepare_paper_strategy(config, experiment, load_symbol=load_symbol)
    assert tuple(loaded) == SYMBOLS
    assert prepared.symbols == SYMBOLS
    assert prepared.strategy_params == experiment.snapshot.parameters
    emissions = [(i, prepared.strategy_fn(prepared.bars.iloc[:i], prepared.strategy_params))
                 for i in range(1, len(prepared.bars) + 1)]
    assert any(set(targets) == set(SYMBOLS) for _, targets in emissions)
    assert all(prepared.bars.index[i - 1].month != prepared.bars.index[i - 2].month
               or prepared.bars.index[i - 2].month != prepared.bars.index[i - 3].month
               for i, targets in emissions if targets and i > 2)


@pytest.mark.parametrize("problem", ["missing", "stale"])
def test_etf_rejects_incomplete_panel(etf, problem):
    config, experiment = etf
    def load_symbol(_dir, symbol, _frequency, **kwargs):
        if symbol == "GLD" and problem == "missing":
            raise FileNotFoundError("missing GLD")
        bars = _bars(symbol)
        return bars.iloc[:-1] if symbol == "GLD" else bars
    with pytest.raises(ValueError, match="GLD"):
        prepare_paper_strategy(config, experiment, load_symbol=load_symbol)


def test_etf_rejects_mismatched_frozen_label(etf):
    config, experiment = etf
    config = replace(config, raw={**config.raw, "frozen_experiment": {**config.raw["frozen_experiment"], "label": "wrong"}})
    with pytest.raises(ValueError, match="label"):
        prepare_paper_strategy(config, experiment, load_symbol=lambda *a, **k: _bars(a[1]))


def test_paper_preparation_uses_catalog_for_default_reads(etf):
    config, experiment = etf
    calls = []
    class RecordingCatalog(DataCatalog):
        def load(self, request):
            calls.append(request)
            return type("Loaded", (), {"frame": _bars(request.symbols[0])})()
    prepared = prepare_paper_strategy(config, experiment, catalog=RecordingCatalog())
    assert prepared.symbols == SYMBOLS
    assert tuple(request.symbols[0] for request in calls) == SYMBOLS


@pytest.mark.parametrize("mismatch", ["strategy", "parameters", "universe", "cost", "risk", "portfolio", "frequency", "source"])
def test_ma_rejects_hypothesis_substitution_before_data(tmp_path, mismatch):
    config = load_config("builtin:paper_shakedown", load_env=False)
    snapshot = snapshot_for_config(config, parameters=asdict(MAParams()), symbols=("AAPL",))
    frequency = "1d"
    if mismatch == "strategy":
        snapshot = replace(snapshot, strategy="bollinger_bands")
    elif mismatch == "parameters":
        snapshot = replace(snapshot, parameters=asdict(MAParams(fast_ma_window=7)))
    elif mismatch == "universe":
        snapshot = replace(snapshot, universe=UniverseSpec(symbols=("MSFT",), asset_class="equity"))
    elif mismatch == "cost":
        config = replace(config, cost_model=replace(config.cost_model, commission_pct=.001))
    elif mismatch == "risk":
        config = replace(config, risk_limits=replace(config.risk_limits, max_open_positions=99))
    elif mismatch == "portfolio":
        config = replace(config, portfolio=replace(config.portfolio, per_position_risk_pct=.2))
    elif mismatch == "frequency":
        frequency = "1h"
    else:
        snapshot = replace(snapshot, data_version=replace(snapshot.data_version, source="yahoo_chart"))
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        experiment = registry.create(ExperimentDraft(label="wrong MA identity", snapshot=snapshot))
        def forbidden(*args, **kwargs):
            raise AssertionError("mismatched qualification reached data")
        with pytest.raises(ValueError):
            prepare_paper_strategy(config, experiment, frequency=frequency, ma_params=asdict(MAParams()), load_symbol=forbidden)
    finally:
        registry.close()


def test_ma_executes_full_frozen_parameters_and_rejects_mutation(tmp_path):
    config = load_config("builtin:paper_shakedown", load_env=False)
    parameters = asdict(MAParams(
        fast_ma_type="ema", fast_ma_window=2, slow_ma_window=3,
        trend_filter_active=False,
    ))
    # Final EMA(2) crosses above SMA(3), whereas SMA(2) remains below.
    bars = pd.DataFrame(
        {"close": [3., 3., 3., 3., 1., 4.]},
        index=pd.date_range("2024-01-01", periods=6, tz="UTC"),
    )
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        experiment = registry.create(ExperimentDraft(label="synthetic MA", snapshot=snapshot_for_config(config, parameters=parameters, symbols=("AAPL",))))
        prepared = prepare_paper_strategy(config, experiment, load_symbol=lambda *a, **k: bars)
        assert prepared.strategy_fn(prepared.bars, parameters) == {"AAPL": 1.}
        prepared.strategy_params["fast_ma_type"] = "sma"
        with pytest.raises(ValueError):
            prepared.strategy_fn(prepared.bars, prepared.strategy_params)
    finally:
        registry.close()


def test_alpaca_preparation_excludes_current_session(etf, tmp_path, monkeypatch):
    config, experiment = etf
    config = replace(config, raw={**config.raw, "paper_data_source": "alpaca"})
    snapshot = replace(experiment.snapshot, data_version=replace(experiment.snapshot.data_version, source="alpaca"))
    registry = ExperimentRegistry(tmp_path / "alpaca-synthetic")
    try:
        experiment = registry.create(ExperimentDraft(label="synthetic Alpaca panel", snapshot=snapshot))
        config = replace(config, raw={**config.raw, "frozen_experiment": {
            "uuid": experiment.uuid, "hash": experiment.experiment_hash, "label": experiment.label,
            "strategy": snapshot.strategy, "universe": list(SYMBOLS), "parameters": snapshot.parameters,
        }})
        current = pd.Timestamp("2026-07-14T00:00:00Z")
        monkeypatch.setattr(
            "engine.paper_strategy.completed_daily_bars",
            lambda bars: completed_daily_bars(bars, now=pd.Timestamp("2026-07-14T14:30:00Z")),
        )
        def load_symbol(_dir, symbol, _frequency, **kwargs):
            bars = _bars(symbol)
            bars.loc[current] = bars.iloc[-1]
            return bars
        prepared = prepare_paper_strategy(config, experiment, load_symbol=load_symbol)
        assert current not in prepared.bars.index
        assert prepared.bars.index[-1] == _bars("SPY").index[-1]
    finally:
        registry.close()


@pytest.mark.parametrize("execution_mode", [
    "next_bar_open", "next_bar_close",
    "signals_after_t_minus_1_close_first_executable_price",
])
def test_research_timing_remains_simulation_only(tmp_path, execution_mode):
    config = load_config("builtin:paper_shakedown", load_env=False)
    registry = ExperimentRegistry(tmp_path / "timing")
    try:
        experiment = registry.create(ExperimentDraft(
            label="synthetic research timing",
            snapshot=snapshot_for_config(
                config, parameters=asdict(MAParams()), symbols=("AAPL",),
                execution_mode=execution_mode,
            ),
        ))
        prepared = prepare_paper_strategy(config, experiment, load_symbol=lambda *a, **k: _bars("AAPL"))
        assert prepared.symbols == ("AAPL",)
        with pytest.raises(ValueError, match="Unsupported broker-paper execution mode"):
            verify_broker_paper_execution_mode(config, experiment)
        assert registry.get(experiment.uuid).snapshot.execution_mode == execution_mode
    finally:
        registry.close()
