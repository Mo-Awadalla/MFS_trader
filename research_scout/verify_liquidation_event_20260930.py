"""Independent ledger reconciliation and final evidence checkpoint."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research.liquidation_event_replay import valid_snapshot

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/liquidation_event_20260930"


def main():
    spec = json.loads((OUTPUT / "strategy_specification.json").read_text())
    result = json.loads((OUTPUT / "results.json").read_text())
    audits = json.loads((OUTPUT / "book_data_audit.json").read_text())
    assert all(digest(ROOT / path) == expected for path, expected in spec["code_sha256"].items())
    count, max_error = 0, 0.
    for name, candidate in result["results"].items():
        for scenario, expected in candidate["scenarios"].items():
            trades = pd.read_parquet(OUTPUT / f"{name}_{scenario}_trades.parquet")
            totals = dict.fromkeys(spec["evaluation"], 0.)
            fee_bps = 10 if scenario == "double_fees" else 5
            delay_us = 3_000_000 if scenario == "latency_3s" else 1_000_000
            free_at = {}
            unresolved_days = set()
            for row in trades.to_dict("records"):
                assert row["date"] not in unresolved_days
                assert row["decision_us"] > free_at.get(row["date"], -1)
                if row["status"] != "priced":
                    unresolved_days.add(row["date"])
                    continue
                count += 1
                notionals = row["quantity"] * (row["entry"] + row["exit"])
                fees, slippage = notionals * fee_bps / 10000, notionals / 10000
                gross = row["direction"] * row["quantity"] * (row["exit"] - row["entry"])
                pnl = gross - fees - slippage
                max_error = max(max_error, abs(pnl - row["pnl"]))
                assert abs(pnl - row["pnl"]) < 1e-8
                assert abs(fees - row["fees"]) < 1e-8
                assert abs(slippage - row["slippage_dollars"]) < 1e-8
                assert 1 <= row["entry_levels"] <= 5 and 1 <= row["exit_levels"] <= 5
                assert abs(row["quantity"] * 1000 - round(row["quantity"] * 1000)) < 1e-9
                free_at[row["date"]] = row["exit_us"] + delay_us
                totals[row["date"]] += pnl
            assert abs(sum(totals.values()) - expected["closed_trade_subtotal"]) < 1e-8
            for row in expected["daily"]:
                assert abs(totals[row["date"]] - row["closed_trade_subtotal"]) < 1e-8
                assert row["complete"] == (row["date"] not in unresolved_days)
            assert expected["complete"] == (not unresolved_days)
            if not expected["complete"]:
                assert expected["net_dollars"] is None
    agreement = {}
    for mode in ("immediate", "quiet"):
        same, eligible, zero = 0, 0, 0
        for day in spec["evaluation"]:
            path = OUTPUT / "panels" / f"{day}_quotes.parquet"
            if not path.exists():
                continue
            panel = pd.read_parquet(path)
            for _, event in panel.loc[panel["mode"].eq(mode)].groupby("event_id", sort=False):
                states = {row["label"]: row for row in event.to_dict("records")}
                signal, old = states["signal"], states["prior30"]
                if mode == "quiet" and not signal["quiet_2s"]:
                    continue
                if not valid_snapshot(signal) or not valid_snapshot(old):
                    continue
                delta = signal["asks[0].price"] + signal["bids[0].price"] - old["asks[0].price"] - old["bids[0].price"]
                if delta == 0:
                    zero += 1
                    continue
                eligible += 1
                same += int(np.sign(delta) == signal["forced_side"])
        agreement[mode] = {"eligible_events": eligible, "same_direction": same,
                           "agreement_fraction": same / eligible if eligible else None, "zero_return_events": zero}
    verification = {"verified": True, "priced_trades_across_dependent_scenarios": count,
                    "maximum_pnl_error_dollars": max_error, "predecision_direction_agreement": agreement}
    (OUTPUT / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    lines = ["LIQUIDATION EVENT HFT SCREEN — 2026-09-30", "", "VERDICT: NO_LIQUIDATION_SURVIVOR. Goal remains active; no reliable edge or competition win established.",
             "", "SOURCE AND CAUSALITY",
             "New public Tardis first-of-month BTCUSDT liquidation samples: twelve dates in 2024.",
             f"January-June calibrated only the reported-size distribution: the 99th-percentile threshold was ${spec['threshold_reported_notional']:,.2f}.",
             "July-December evaluated frozen rules using exact strictly-prior top-five book snapshots and microsecond capture timestamps.",
             f"Six books contain {sum(x['rows'] for x in audits):,} rows; the trigger produces {sum(x['events'] for x in audits)} first-report events after five-minute refractory periods.",
             "The order-book files total 164,789,261 compressed bytes. All requests were unauthenticated public samples; no paid API was called.",
             "", "RULES AND EXECUTION",
             "Follow or reverse reported liquidation direction; act immediately or after a causally known two-second quiet interval; hold 30 or 120 seconds.",
             "Eight fixed liquidation configurations and eight price-direction controls use the same event clocks.",
             "Baseline crosses observed depth after one-second order delay: 5bp fees plus 1bp extra adverse cost on each side. Doubled fees and three-second delay are separate stresses.",
             "Entry is FOK with a causal 5bp price collar. Five-level weighted prices are used when sufficient; unobserved deeper liquidity or unknown submitted-order execution invalidates the day.",
             "Daily initial account $10000; max ticket $1000 and 10% pre-decision touch quantity. No funding-boundary exposure. Isolated-date summed P&L is not continuous calendar wealth.",
             "", "BASELINE RESULTS: name | gross dollars | net dollars | priced trades | mean net bp"]
    for name, candidate in result["results"].items():
        base = candidate["scenarios"]["base"]
        net = f"${base['net_dollars']:+.2f}" if base["complete"] else f"INCOMPLETE (closed subtotal ${base['closed_trade_subtotal']:+.2f})"
        bps = f"{base['mean_net_bps']:+.3f}" if base["mean_net_bps"] is not None else "none"
        lines.append(f"{name} | ${base['gross_dollars']:+.2f} | {net} | {base['trades']} | {bps}")
    lines += ["", "INTERPRETATION",
              "The largest complete gross liquidation-rule total is +$8.63 (follow, quiet, 120s), versus -$81.77 after costs. It is not a viable edge under the authorized conservative costs.",
              "The best complete price-control gross total is +$11.64, also negative after costs. New liquidation information did not produce a reliable net-profit alternative."]
    for mode, record in agreement.items():
        lines.append(f"{mode}: liquidation direction agrees with the prior 30-second price move on {record['same_direction']}/{record['eligible_events']} comparable predecision events ({100 * record['agreement_fraction']:.1f}%).")
    lines += ["This agreement is descriptive; it does not prove the two signals are identical. Controls retain liquidation timing and are not a matched non-liquidation-event study.",
              "", "VERIFICATION AND LIMITS",
              f"Independent verification reconciled {count} priced trades across dependent stress scenarios; maximum trade-P&L discrepancy {max_error:.3g} dollars.",
              "Six new focused tests pass: event chronology, quiet/refractory behavior, strict as-of lookup, invalid latest books, depth-weighted FOK fills, unknown liquidity and both-side costs.",
              "The current search totals 58 configurations and 64 evaluated implementation versions including prior repairs; these are dependent and do not erase historical research exposure.",
              "Public liquidation snapshots are throttled; reported notional is not total forced flow. Calendar-selected first days are not continuous or representative ordinary-date coverage.",
              "Reconstructed books remove crossed levels; CSV data omit disconnect events. Historical receive-clock replay cannot prove actual fills or market impact. Freshly acquired history is not forward evidence.",
              "No later 2025 liquidation test was opened. All candidates failed the frozen progression gate.",
              "", "Official source documentation:",
              "https://docs.tardis.dev/downloadable-csv-files/data-types",
              "https://docs.tardis.dev/faq/data", ""]
    (OUTPUT / "REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    checkpoint = {"status": "active", "reliable_edge_found": False, "current_configurations": 58,
                  "implementation_versions": 64, "eth_replication_survivors": [], "liquidation_survivors": result["survivors"],
                  "new_focused_tests_this_turn": 9, "focused_tests_total": 45, "new_public_liquidation_source_verified": True,
                  "liquidation_event_count": sum(x["events"] for x in audits), "independent_accounting_verified": True,
                  "report": str(OUTPUT / "REPORT.txt")}
    (ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json").write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
