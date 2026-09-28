"""Offline real-path ETF execution ledgers; attribution is not financial equality."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config.loader import load_config
from engine.cli import main
from engine.etf_tsm_replay import declare_etf_tsm_execution, run_etf_tsm_engine_replay
from engine.parity import (
    LEDGER_FIELDS,
    MECHANISMS,
    ParityDeclarationError,
    compare_ledgers,
    evaluate_execution_parity,
    simulate_ledger,
    write_declaration,
)
from research.universes.etf_tactical_v1 import all_symbols
from storage.parquet_io import write_bars
from strategies.etf_time_series_momentum.signal import default_params


def synthetic_panel() -> pd.DataFrame:
    """Frozen params, several market regimes; never tune params to obtain equality."""
    n = 680
    index = pd.bdate_range("2020-01-02", periods=n, tz="UTC")
    t = np.arange(n)
    frames = []
    for i, symbol in enumerate(all_symbols()):
        trend = 0.0002 + i * 0.00012
        returns = trend + 0.002 * np.sin(t / (7 + i))
        if symbol != "SHY":
            returns = returns - np.where((t > 390) & (t < 510), 0.0035, 0.0)
        close = (40 + 10 * i) * np.exp(np.cumsum(returns))
        frame = pd.DataFrame({"open": close * 0.998, "high": close * 1.01,
                              "low": close * 0.99, "close": close,
                              "volume": np.full(n, 2_000_000.0)}, index=index)
        frame.columns = pd.MultiIndex.from_product([[symbol], frame.columns], names=["symbol", "field"])
        frames.append(frame)
    return pd.concat(frames, axis=1)


@pytest.fixture(scope="module")
def replay_case(tmp_path_factory):
    config = load_config("config/research.toml")
    params = default_params()
    panel = synthetic_panel()
    declaration = declare_etf_tsm_execution(config, params=params)
    result = run_etf_tsm_engine_replay(
        config=config, params=params, panel=panel,
        out_dir=tmp_path_factory.mktemp("parity"), assumptions=declaration,
        assert_financial_parity=True,
    )
    return config, panel, declaration, result


def test_actual_research_and_runtime_ledgers_match_declarations(replay_case):
    _, panel, _, result = replay_case
    assert result.passed
    assert result.replay.bar_count == len(panel)
    assert result.replay.orders_filled == result.replay.orders_submitted
    report = result.execution_parity
    assert report["financial_parity"] == "attributed"
    assert result.financial_parity_assertion_failed
    assert report["decision_parity"]["identical"]
    for path in ("research", "runtime"):
        checks = report[f"{path}_declaration_check"]
        assert set(checks) == set(LEDGER_FIELDS)
        for name, check in checks.items():
            assert check["within_tolerance"], (path, name, check)
            assert check["divergent_bars"] == 0
    assert set(report["attribution"]["order"]) == {name for name, _ in MECHANISMS}
    assert report["attribution"]["residual_within_tolerance"]
    assert sum(step["equity_delta"] for step in report["attribution"]["chain"]) == pytest.approx(
        report["final_equity"]["gap_runtime_minus_research"], abs=0.0001,
    )
    for name in LEDGER_FIELDS:
        assert report["research_vs_runtime_fields"][name]["status"] in ("equal", "attributed")
    # A real buy and liquidation/reduction are both exercised, not a flat ledger.
    assert (result.runtime_ledger.order_qty.to_numpy() > 1).any()
    assert (result.runtime_ledger.order_qty.to_numpy() < -1).any()
    np.testing.assert_allclose(
        result.runtime_ledger.target_weight.to_numpy(),
        result.research_ledger.target_weight.shift(1).fillna(0.0).to_numpy(),
        atol=1e-12, rtol=0,
    )


@pytest.mark.parametrize("field", LEDGER_FIELDS)
def test_intermediate_ledger_corruption_cannot_hide_in_final_equity(replay_case, field):
    _, panel, declaration, result = replay_case
    damaged = replace(result.runtime_ledger)
    value = getattr(damaged, field).copy()
    if isinstance(value, pd.DataFrame):
        value.iloc[350, 0] += 1.0
    else:
        value.iloc[350] += 1.0
    setattr(damaged, field, value)
    report = evaluate_execution_parity(
        close=panel.xs("close", axis=1, level="field"),
        decision_weights=result.research_ledger.target_weight,
        research_actual=result.research_ledger, runtime_actual=damaged,
        research=declaration.research, runtime=declaration.runtime, initial_capital=10_000,
    )
    assert report["financial_parity"] == "failed"
    assert not report["runtime_declaration_check"][field]["within_tolerance"]
    assert report["runtime_declaration_check"][field]["first_divergence"] == str(panel.index[350])


def test_fill_timing_is_checked_against_actual_orders(replay_case):
    _, panel, declaration, result = replay_case
    wrong = simulate_ledger(
        panel.xs("close", axis=1, level="field"), result.research_ledger.target_weight,
        replace(declaration.runtime, fill_lag_bars=0), initial_capital=10_000,
    )
    checks = compare_ledgers(result.runtime_ledger, wrong, initial_capital=10_000)
    assert not checks["order_qty"]["within_tolerance"]
    assert not checks["position"]["within_tolerance"]
    first_decision = result.research_ledger.target_weight.abs().sum(axis=1).gt(0).idxmax()
    first_fill = result.runtime_ledger.order_qty.abs().sum(axis=1).gt(0).idxmax()
    assert panel.index.get_loc(first_fill) == panel.index.get_loc(first_decision) + 1


def test_existing_threshold_knob_agrees_with_independent_attribution(replay_case, tmp_path):
    config, panel, declaration, baseline = replay_case
    overrides = {"min_notional_delta": 0.0, "min_pct_position_delta": 0.0}
    declared = declare_etf_tsm_execution(config, rebalance_threshold_overrides=overrides)
    changed = run_etf_tsm_engine_replay(
        config=config, panel=panel, out_dir=tmp_path, assumptions=declared,
        rebalance_threshold_overrides=overrides,
    )
    assert declared.runtime.risk == declaration.runtime.risk  # No risk controls disabled.
    assert changed.execution_parity["runtime_matches_runtime_declaration"]
    reference = simulate_ledger(
        panel.xs("close", axis=1, level="field"), baseline.research_ledger.target_weight,
        declared.runtime, initial_capital=10_000,
    )
    baseline_model = baseline.execution_parity["final_equity"]["runtime_model"]
    assert changed.replay_final_equity - baseline.replay_final_equity == pytest.approx(
        reference.final_equity - baseline_model, abs=0.0001,
    )
    assert not np.allclose(changed.runtime_ledger.order_qty, baseline.runtime_ledger.order_qty)


def test_nan_or_missing_bar_is_not_agreement(replay_case):
    _, _, _, result = replay_case
    damaged = replace(result.runtime_ledger, equity=result.runtime_ledger.equity.copy())
    damaged.equity.iloc[300] = np.nan
    assert not compare_ledgers(result.runtime_ledger, damaged, initial_capital=10_000)["equity"]["within_tolerance"]
    damaged.equity = damaged.equity.drop(damaged.equity.index[300])
    assert not compare_ledgers(result.runtime_ledger, damaged, initial_capital=10_000)["equity"]["within_tolerance"]


def test_invalid_declaration_fails_before_replay_io(replay_case, tmp_path):
    config, _, declaration, _ = replay_case
    output = tmp_path / "must-not-be-created"
    with pytest.raises(ParityDeclarationError):
        run_etf_tsm_engine_replay(config=config, out_dir=output, assert_financial_parity=True)
    with pytest.raises(ParityDeclarationError):
        run_etf_tsm_engine_replay(
            config=config, out_dir=output,
            assumptions=replace(declaration, runtime=replace(declaration.runtime, fill_lag_bars=0)),
        )
    assert not output.exists()


def test_cli_never_upgrades_structural_pass_to_financial_parity(replay_case, tmp_path, capsys):
    _, panel, declaration, _ = replay_case
    cache = tmp_path / "cache"
    for symbol in all_symbols():
        write_bars(panel[symbol], cache / f"{symbol}_1d.parquet")
    args = ["--config", "config/research.toml", "replay-etf-tsm", "--cache-dir", str(cache),
            "--out-dir", str(tmp_path / "reports")]
    assert main(args) == 0
    payload = json.loads((tmp_path / "reports" / "etf_tsm_engine_replay.json").read_text())
    assert payload["scope"] == "structural_replay"
    assert payload["financial_parity"] == "not_established"
    declaration_path = tmp_path / "assumptions.json"
    write_declaration(declaration, declaration_path)
    assert main(args + ["--assert-financial-parity", "--allow-diffs"]) == 1
    assert main(args + ["--assumptions", str(declaration_path), "--assert-financial-parity", "--allow-diffs"]) == 1
    payload = json.loads((tmp_path / "reports" / "etf_tsm_engine_replay.json").read_text())
    assert payload["structural_replay_status"] == "PASS"
    assert payload["financial_parity"] == "attributed"
    captured = capsys.readouterr()
    assert "financial_parity: not_established" in captured.out
    assert "financial_parity: attributed" in captured.out


def test_predeclared_assumptions_cannot_be_overwritten(replay_case, tmp_path):
    _, _, declaration, _ = replay_case
    path = tmp_path / "assumptions.json"
    write_declaration(declaration, path)
    original = path.read_bytes()
    changed = replace(declaration, runtime=replace(declaration.runtime, fill_lag_bars=0))
    with pytest.raises(FileExistsError):
        write_declaration(changed, path)
    assert path.read_bytes() == original
