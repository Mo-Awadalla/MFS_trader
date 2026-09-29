"""Caller -> gauntlet -> serialized report contract for corrected validation.

Each case drives a real research caller (declared cross-sectional search,
no-tuning validation, or the ETF TSM pipeline) through ``run_gauntlet`` and
the canonical ArtifactManager report writer, then checks the persisted JSON.
The toy strategies below deliberately use look-ahead so the outcome is known;
they exercise the validation plumbing, not a tradable hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from experiments.artifacts import ArtifactKind, ArtifactManager
from research.cross_sectional_pipeline import (
    CrossSectionalValidationReport,
    backtest_cross_sectional,
    make_no_tuning_wfa_fns,
    run_declared_cross_sectional_search,
    run_no_tuning_cross_sectional_validation,
    write_validation_artifacts,
)
from research.etf_time_series_momentum_pipeline import (
    run_etf_time_series_momentum_validation_gauntlet,
)
from strategies.etf_time_series_momentum.signal import ETFTimeSeriesMomentumParams
from validation.gauntlet import GAUNTLET_REPORT_SCHEMA_VERSION, run_gauntlet
from validation.mc.engine import MC_FORMULA_VERSION
from validation.wfa.engine import PRESETS, WFATier

UUID = "0f0e0d0c-0b0a-4908-8706-050403020100"
SYMBOLS = ("AAA", "BBB", "CCC", "DDD", "EEE")


@pytest.fixture(autouse=True)
def _toy_template_version(monkeypatch):
    """The toy strategy is not registered; give it a template version label."""
    monkeypatch.setattr(
        "research.cross_sectional_pipeline.strategy_template_version",
        lambda name: f"{name}:test",
    )


@dataclass(frozen=True)
class ToyParams:
    exposure: float
    sign: float = 1.0
    symbol_index: int = 0


def _toy_params_to_dict(params: ToyParams) -> dict[str, Any]:
    return {"exposure": params.exposure, "sign": params.sign, "symbol_index": params.symbol_index}


def _toy_signals(df: pd.DataFrame, params: ToyParams) -> pd.DataFrame:
    """Independent toy trials: each holds one synthetic asset on favorable bars."""
    close = df.xs("close", axis=1, level=1)
    next_return = close.pct_change(fill_method=None).shift(-1).fillna(0.0)
    weight = pd.DataFrame(0.0, index=df.index, columns=close.columns)
    symbol = SYMBOLS[params.symbol_index]
    weight[symbol] = (np.sign(next_return[symbol]) == params.sign).astype(float) * params.exposure
    trade = weight.diff().fillna(weight)
    frames = {
        **{(symbol, "weight"): weight[symbol] for symbol in close.columns},
        **{(symbol, "trade"): trade[symbol] for symbol in close.columns},
        ("portfolio", "is_rebalance"): pd.Series(True, index=df.index),
        ("portfolio", "rebalance_skipped"): pd.Series(False, index=df.index),
    }
    signals = pd.DataFrame(frames, index=df.index)
    signals.columns = signals.columns.set_names(["symbol", "field"])
    return signals


def _panel(n: int = 900, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2019-01-01", periods=n, freq="B", tz="UTC")
    frames = {}
    for symbol in SYMBOLS:
        close = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, n))
        frames[symbol] = pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close, "volume": 1e6},
            index=index,
        )
    panel = pd.concat(frames, axis=1)
    panel.columns = pd.MultiIndex.from_tuples(list(panel.columns), names=["symbol", "field"])
    return panel


def _run_toy_caller(tmp_path: Path, sign: float) -> dict[str, Any]:
    df = _panel()
    grid = [ToyParams(1.0, sign, symbol_index=i) for i in range(len(SYMBOLS))]
    selected = grid[2]
    common = {
        "strategy_name": "toy_lookahead",
        "generate_signals": _toy_signals,
        "params_to_dict": _toy_params_to_dict,
    }
    sweep, search = run_declared_cross_sectional_search(
        df,
        grid,
        selected,
        sweep_metadata={},
        search_scope="five independent synthetic asset trials",
        **common,
    )
    train_fn, test_fn = make_no_tuning_wfa_fns(df, selected, **common)
    gauntlet = run_gauntlet(
        "toy_lookahead",
        df,
        train_fn,
        test_fn,
        sweep,
        ["symbol_index"],
        dsr_search=search,
        wfa_config=PRESETS[WFATier.PRIMARY],
        mc_num_paths=300,
    )
    report = CrossSectionalValidationReport(
        strategy_name="toy_lookahead",
        report_title="toy",
        params=selected,
        params_dict=_toy_params_to_dict(selected),
        research=backtest_cross_sectional(df, selected, **common),
        sweep=sweep,
        gauntlet=gauntlet,
        replay_attribution={},
        experiment_uuid=UUID,
    )
    return _write_and_read(tmp_path, report)


def _write_and_read(tmp_path: Path, report: CrossSectionalValidationReport) -> dict[str, Any]:
    artifacts = ArtifactManager(tmp_path / "experiments")
    write_validation_artifacts(artifacts, UUID, report)
    payload = artifacts.read_json(UUID, ArtifactKind.VALIDATION_REPORT_JSON)
    verdict = artifacts.path(UUID, ArtifactKind.VALIDATION_VERDICT_TXT).read_text().strip()
    payload["_verdict"] = verdict
    return payload


def _assert_versioned(gauntlet: dict[str, Any]) -> None:
    assert gauntlet["report_schema_version"] == GAUNTLET_REPORT_SCHEMA_VERSION
    assert gauntlet["monte_carlo"]["formula_version"] == MC_FORMULA_VERSION
    assert "pct_95_max_dd" not in gauntlet["monte_carlo"]
    assert gauntlet["dsr"]["formula_version"] == "bailey_lopez_de_prado_eq2_v1"


def test_declared_search_success_is_serialized_as_corrected_pass(tmp_path):
    payload = _run_toy_caller(tmp_path, sign=1.0)
    gauntlet = payload["gauntlet"]

    _assert_versioned(gauntlet)
    assert gauntlet["failure_reasons"] == []
    assert gauntlet["passed"] is True
    assert payload["_verdict"] == "PASS"
    dsr = gauntlet["dsr"]
    assert dsr["available"] is True and dsr["passed"] is True
    assert dsr["m_raw"] == 5
    assert dsr["m_eff"] >= 2
    assert dsr["confidence"] == pytest.approx(1.0 - dsr["pvalue"])
    mc = gauntlet["monte_carlo"]
    assert mc["available"] is True
    assert mc["observation_count"] > 0 and mc["periods_per_year"] == 252.0
    assert mc["pct_5_max_dd"] >= -0.30


def test_declared_search_failure_is_serialized_as_fail_with_available_metrics(tmp_path):
    payload = _run_toy_caller(tmp_path, sign=-1.0)
    gauntlet = payload["gauntlet"]

    _assert_versioned(gauntlet)
    assert gauntlet["passed"] is False
    assert payload["_verdict"] == "FAIL"
    assert gauntlet["dsr"]["available"] is True
    assert gauntlet["dsr"]["passed"] is False
    assert gauntlet["monte_carlo"]["available"] is True
    assert any(reason.startswith("MC: ") for reason in gauntlet["failure_reasons"])


def test_no_tuning_caller_reports_unavailable_dsr_and_fails(tmp_path):
    df = _panel()
    report = run_no_tuning_cross_sectional_validation(
        df,
        ToyParams(1.0),
        strategy_name="toy_lookahead",
        report_title="toy",
        generate_signals=_toy_signals,
        params_to_dict=_toy_params_to_dict,
        build_experiment_draft=lambda *a, **k: None,
        param_columns=["exposure"],
        sweep_metadata={},
        replay_reason="synthetic",
        mc_num_paths=200,
    )
    report.experiment_uuid = UUID
    payload = _write_and_read(tmp_path, report)
    dsr = payload["gauntlet"]["dsr"]

    # Every other gate is favorable; only missing search evidence blocks PASS.
    assert dsr["available"] is False
    assert dsr["passed"] is False
    assert "at least two documented trials" in dsr["unavailable_reason"]
    assert payload["gauntlet"]["passed"] is False
    assert payload["_verdict"] == "FAIL"
    assert [r for r in payload["gauntlet"]["failure_reasons"] if r.startswith("DSR")]


def test_frozen_params_outside_declared_grid_are_unavailable_not_best_trial(tmp_path):
    index = pd.date_range("2020-01-01", periods=520, freq="B", tz="UTC")
    frames = {}
    for i, symbol in enumerate(("SPY", "QQQ", "IWM", "IEF", "GLD", "SHY", "DBC")):
        close = 100.0 * np.cumprod(np.full(len(index), 1.0001 + i * 0.00002))
        frames[symbol] = pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close, "volume": 1.5e6},
            index=index,
        )
    panel = pd.concat(frames, axis=1)
    panel.columns = pd.MultiIndex.from_tuples(list(panel.columns), names=["symbol", "field"])

    report = run_etf_time_series_momentum_validation_gauntlet(
        panel,
        params=ETFTimeSeriesMomentumParams(momentum_lookback_days=126, vol_lookback_days=42),
        mc_num_paths=100,
        write_artifacts=False,
    )
    dsr = report.gauntlet.to_dict()["dsr"]

    assert dsr["available"] is False
    assert "match 0 declared trials" in dsr["unavailable_reason"]
    assert report.gauntlet.passed is False
