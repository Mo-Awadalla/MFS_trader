"""Reconcile corrected liquidation P&L and unchanged decision information."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.crypto_symbol_cache import digest
from research.liquidation_event_replay import FIELDS

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout/liquidation_event_20260930"
OUT = BASE / "dual_clock"


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "results.json").read_text())
    original = json.loads((BASE / "results.json").read_text())
    assert digest(BASE / "strategy_specification.json") == spec["original_spec_sha256"]
    for p, expected in spec["code_sha256"].items():
        assert digest(ROOT / p) == expected
    key = ["date", "event_id", "mode", "label", "target_us"]
    columns = ["quote_local_us", "quote_exchange_us", *FIELDS]
    panels, inputs_verified = [], 0
    for audit in results["source_audits"]:
        day = audit["date"]
        path = OUT / f"{day}_quotes.parquet"
        assert digest(path) == audit["panel_sha256"]
        assert digest(BASE / "panels" / f"{day}_events.parquet") == audit["events_sha256"]
        assert digest(BASE / "raw/book_snapshot_5" / day / "BTCUSDT.csv.gz") == audit["source_sha256"]
        quotes = pd.read_parquet(path)
        old = pd.read_parquet(BASE / "panels" / f"{day}_quotes.parquet")
        decision = quotes.label.isin(["signal", "prior30"])
        left = quotes.loc[decision].set_index(key)[columns].sort_index()
        right = old.loc[old.label.isin(["signal", "prior30"])].set_index(key)[columns].sort_index()
        pd.testing.assert_frame_equal(left, right)
        assert (quotes.loc[decision, "quote_local_us"] < quotes.loc[decision, "target_us"]).all()
        assert (quotes.loc[~decision, "quote_exchange_us"] < quotes.loc[~decision, "target_us"]).all()
        inputs_verified += int(decision.sum())
        panels.append(quotes)
    priced, maximum_error, differences = 0, 0., []
    for name, candidate in results["results"].items():
        for scenario, expected in candidate["scenarios"].items():
            trades = pd.read_parquet(OUT / f"{name}_{scenario}_trades.parquet")
            daily = pd.read_parquet(OUT / f"{name}_{scenario}_daily.parquet")
            fee = 10 if scenario == "double_fees" else 5
            delay = 3_000_000 if scenario == "latency_3s" else 1_000_000
            totals = dict.fromkeys(spec["evaluation"], 0.)
            free, incomplete = {}, set()
            for trade in trades.to_dict("records"):
                day = trade["date"]
                assert day not in incomplete and trade["decision_us"] > free.get(day, -1)
                if trade["status"] != "priced":
                    incomplete.add(day)
                    continue
                priced += 1
                gross = trade["direction"] * trade["quantity"] * (trade["exit"] - trade["entry"])
                notional = trade["quantity"] * (trade["exit"] + trade["entry"])
                expected_fee, adverse = notional * fee / 10000, notional / 10000
                pnl = gross - expected_fee - adverse
                maximum_error = max(maximum_error, abs(pnl - trade["pnl"]))
                assert abs(pnl - trade["pnl"]) < 1e-8
                assert abs(expected_fee - trade["fees"]) < 1e-8
                assert abs(adverse - trade["slippage_dollars"]) < 1e-8
                assert 1 <= trade["entry_levels"] <= 5 and 1 <= trade["exit_levels"] <= 5
                assert abs(trade["quantity"] * 1000 - round(trade["quantity"] * 1000)) < 1e-8
                totals[day] += pnl
                free[day] = trade["exit_us"] + delay
            assert expected["complete"] == (not incomplete)
            assert expected["net_dollars"] is None if incomplete else abs(expected["net_dollars"] - sum(totals.values())) < 1e-8
            assert abs(expected["closed_trade_subtotal"] - sum(totals.values())) < 1e-8
            for d in daily.to_dict("records"):
                assert d["complete"] == (d["date"] not in incomplete)
                assert abs(d["closed_trade_subtotal"] - totals[d["date"]]) < 1e-8
        before, after = original["results"][name]["scenarios"]["base"], candidate["scenarios"]["base"]
        differences.append({"rule": name, "original_complete": before["complete"], "corrected_complete": after["complete"],
                            "original_base_net": before["net_dollars"], "corrected_base_net": after["net_dollars"],
                            "corrected_closed_subtotal": after["closed_trade_subtotal"], "corrected_trades": after["trades"]})
    assert not results["complete_and_positive_all_scenarios"]
    audit = {"verified": True, "decision_input_snapshots_identical": inputs_verified,
             "priced_trades_across_dependent_scenarios": priced, "maximum_pnl_error_dollars": maximum_error,
             "frozen_candidate_outcomes": differences, "reliable_edge_established": False}
    (OUT / "verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    lines = ["LIQUIDATION REPLAY: EXCHANGE-TIME EXECUTION CORRECTION", "", "VERDICT: NO RELIABLE EDGE. No frozen rule is complete and profitable across all scenarios.",
             "", "All 124 frozen events, directions, timing, sizing, price collars and costs are unchanged. No new date or parameter was selected.",
             "Signals and prior-30-second controls retain exactly the same capture-time data. Order fills instead use the strictly preceding exchange-time book.",
             "The original receive-time artifacts remain unchanged and are superseded for execution evidence by this directory.",
             "", "rule | original net dollars | corrected net dollars | complete"]
    for row in differences:
        lines.append(f"{row['rule']} | {row['original_base_net']} | {row['corrected_base_net']} | {row['corrected_complete']}")
    best = results["results"]["follow_quiet_120s"]["scenarios"]["base"]
    lines += ["", f"Best complete baseline liquidation rule remains follow/quiet/120s: gross ${best['gross_dollars']:+.4f}; net ${best['net_dollars']:+.4f}; {best['trades']} trades.",
              "The price-follow quiet/120s control remains negative too. Some former complete paths become incomplete when the physical execution book cannot support a full exit; closed subtotals are not portfolio returns.",
              f"Independent verification reconciled {priced} priced trades across dependent scenarios, maximum P&L error ${maximum_error:.3g}; {inputs_verified} decision-input snapshots are exactly unchanged.",
              "These are implementation repairs, not new independent validation. The reproduced old 64-version bootstrap fields are historical diagnostics and do not account for the full current search; no candidate is promoted using them.",
              "Public exchange timestamps and historical books remain execution proxies. Market impact, actual routing, disconnects and fill acceptance are not proven.",
              "", "The search remains active at 60 configurations / 84 evaluated implementation versions, including this 16-rule repair. No reliable edge or competition win established.", ""]
    (OUT / "REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    (BASE / "EXECUTION_CLOCK_ERRATUM.txt").write_text(
        "Original receive-clock results and frozen sources are preserved. Execution evidence is superseded by dual_clock/REPORT.txt and dual_clock/verification.json. "
        "Capture-time decision information is unchanged; order execution now uses exchange-time books. No candidate becomes a reliable edge.\n", encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint.update(implementation_versions=84, liquidation_dual_clock_reconciled=True,
                      liquidation_best_complete_base_net=best["net_dollars"],
                      liquidation_clock_correction_report=str(OUT / "REPORT.txt"),
                      remaining_evidence_work="Continue economically distinct HFT mechanisms; receipt-time execution artifacts must not be promoted.")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "frozen_candidate_outcomes"}, indent=2))


if __name__ == "__main__":
    main()
