from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

from research.bitcoin_delta_neutral_funding_carry_scout import evaluate, load_spec
from scripts.run_bitcoin_delta_neutral_funding_carry_scout import _unlock


def test_evaluator_preserves_funding_basis_and_cost_accounting():
    spec = copy.deepcopy(load_spec())
    spec["progression_gates"]["minimum_trades"] = 2
    spec["bootstrap"]["trade_resamples"] = 100
    trades = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(["2021-01-01", "2021-01-09"], utc=True),
            "funding_event_count": [21, 21],
            "realized_funding_sum": [0.006, 0.006],
            "basis_pnl": [0.001, 0.001],
            "funding_pnl": [0.003, 0.003],
            "gross_return": [0.004, 0.004],
            "fee_cost": [0.0015, 0.0015],
            "slippage_cost": [0.001, 0.001],
            "fee_only_return": [0.0025, 0.0025],
            "conservative_return": [0.0015, 0.0015],
            "cashflow_accounting_valid": [True, True],
        }
    )

    report = evaluate(trades, spec)

    assert report["mean_gross_bps"] == pytest.approx(40.0)
    assert report["mean_fee_only_bps"] == pytest.approx(25.0)
    assert report["mean_conservative_bps"] == pytest.approx(15.0)
    assert report["passed"] is True


def test_later_partition_lock_requires_prior_pass(tmp_path):
    development = tmp_path / "development"
    development.mkdir()
    (development / "report.json").write_text(json.dumps({"passed": False}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="development did not pass"):
        _unlock("internal_validation", tmp_path)
