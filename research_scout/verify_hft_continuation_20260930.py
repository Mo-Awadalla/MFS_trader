"""Independent fill-ledger reconciliation for the current research continuation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PASSIVE = ROOT / "research_scout/crypto_passive_partial_20260930"
CROSS = ROOT / "research_scout/crypto_cross_market_20260930"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_frozen_sources(spec, directory):
    for path, expected in spec["code_sha256"].items():
        source = ROOT / path
        if sha(source) != expected:
            source = directory / "code_snapshot" / path
        assert sha(source) == expected


def verify_partial(directory=PASSIVE, section="development"):
    spec = json.loads((directory / "specification.json").read_text())
    summary = json.loads((directory / f"{section}_results.json").read_text())
    verify_frozen_sources(spec, directory)
    max_pnl_error = max_inventory_error = max_summary_error = 0.0
    count = unresolved = mixed = small_fills = 0
    for name, scenario in spec["scenarios"].items():
        frame = pd.read_parquet(directory / f"{section}_{name}_trades.parquet")
        totals = dict.fromkeys(spec[section], 0.0)
        last_exit = {}
        for t in frame.to_dict("records"):
            day = t["date"]
            assert t["decision_ms"] > last_exit.get(day, -1)
            if t["status"] != "priced":
                unresolved += 1
                continue
            count += 1
            entries, exits = t["entry_fills"], t["exit_fills"]
            entry_q, exit_q = sum(f["quantity"] for f in entries), sum(f["quantity"] for f in exits)
            error = max(abs(entry_q - exit_q), abs(entry_q - t["quantity"]), abs(exit_q - t["closed_quantity"]))
            max_inventory_error = max(max_inventory_error, error)
            assert error < 1e-10
            assert entry_q <= t["intended_quantity"] + 1e-10
            assert all(t["activation_ms"] < f["time"] < t["entry_expiration_ms"] for f in entries)
            assert all(f["time"] >= t["exit_activation_ms"] for f in exits)
            if t["partial_entry"]:
                assert t["exit_activation_ms"] >= t["entry_expiration_ms"] + 2 * scenario["order_delay_ms"]
            for f in exits:
                if f["kind"] == "taker_timeout":
                    assert f["time"] >= t["cancel_arrival_ms"] + 2 * scenario["order_delay_ms"]
            entry_value = sum(f["quantity"] * f["price"] for f in entries)
            exit_value = sum(f["quantity"] * f["price"] for f in exits)
            fees = entry_value * scenario["maker_fee_bps"] / 10000
            fees += sum(f["quantity"] * f["price"] * (scenario["maker_fee_bps"] if f["kind"] == "maker"
                        else scenario["taker_fee_bps"]) / 10000 for f in exits)
            extra = sum(f["quantity"] * f["price"] * scenario["taker_slippage_bps"] / 10000 for f in exits if f["kind"] != "maker")
            pnl = t["direction"] * (exit_value - entry_value) - fees - extra
            max_pnl_error = max(max_pnl_error, abs(pnl - t["pnl"]))
            assert abs(pnl - t["pnl"]) < 1e-9
            assert abs(fees - t["fees"]) < 1e-9
            totals[day] += pnl
            last_exit[day] = t["exit_ms"] + scenario["order_delay_ms"]
            small_fills += int(len(entries) > 1 or len(exits) > 1)
            mixed += int(t["maker_exit_quantity"] > 1e-12 and t["taker_exit_quantity"] > 1e-12)
        max_summary_error = max(max_summary_error, abs(sum(totals.values()) - summary[name]["closed_trade_pnl"]))
        for day in summary[name]["daily"]:
            assert abs(totals[day["date"]] - day["closed_trade_pnl"]) < 1e-8
        if not summary[name]["complete"]:
            assert summary[name]["net_dollars"] is None
    return {"verified": True, "priced_trades_across_dependent_stresses": count,
            "unresolved_records": unresolved, "multiple_fill_records": small_fills, "mixed_exit_records": mixed,
            "maximum_pnl_error_dollars": max_pnl_error, "maximum_quantity_error": max_inventory_error,
            "maximum_summary_error_dollars": max_summary_error}


def verify_cross():
    if not (CROSS / "results.json").exists():
        return {"verified": False, "status": "not_finished"}
    spec = json.loads((CROSS / "specification.json").read_text())
    results = json.loads((CROSS / "results.json").read_text())
    verify_frozen_sources(spec, CROSS)
    correction = json.loads((CROSS / "execution_correction.json").read_text())
    assert correction["all_recorded_results_unchanged"]
    assert sha(ROOT / "research/crypto_cross_market.py") == correction["corrected_engine_sha256"]
    if "results" not in results:
        return {"verified": False, "status": results["verdict"]}
    max_error, count = 0.0, 0
    for name, result in results["results"].items():
        for scenario, expected in result["scenarios"].items():
            frame = pd.read_parquet(CROSS / f"{name}_{scenario}_trades.parquet")
            ledger = frame.loc[frame.status.eq("priced")] if len(frame) else frame
            if len(ledger):
                fee_bps = 10 if scenario == "double_fees" else 5
                latency = 3000 if scenario == "latency_3s" else 1000
                fees = ledger.quantity * (ledger.entry + ledger.exit) * fee_bps / 10000
                slip = ledger.quantity * (ledger.entry + ledger.exit) / 10000
                pnl = ledger.direction * ledger.quantity * (ledger.exit - ledger.entry) - fees - slip
                max_error = max(max_error, float(np.max(np.abs(pnl - ledger.pnl))))
                assert np.allclose(pnl, ledger.pnl, rtol=0, atol=1e-9)
                assert (ledger.quantity <= ledger.intended_quantity + 1e-10).all()
                for _, group in ledger.groupby("date"):
                    assert (group.decision_ms.to_numpy()[1:] > group.exit_ms.to_numpy()[:-1] + latency).all()
                count += len(ledger)
                total = float(pnl.sum())
            else:
                total = 0.0
            assert abs(total - expected["closed_trade_pnl"]) < 1e-8
            if not expected["complete"]:
                assert expected["net_dollars"] is None
    return {"verified": True, "priced_trades_across_dependent_stresses": count,
            "maximum_pnl_error_dollars": max_error}


def main():
    output = {"passive_partial": verify_partial(), "cross_market": verify_cross(),
              "passive_confirmation": verify_partial(ROOT / "research_scout/crypto_passive_confirmation_20260930", "selection")}
    target = ROOT / "research_scout/hft_edge_search_20260930/continuation_accounting_check.json"
    target.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
