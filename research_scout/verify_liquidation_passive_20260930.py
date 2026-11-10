"""Verify passive fills directly against raw-derived tapes and reconcile cash."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout/liquidation_event_20260930"
OUT = ROOT / "research_scout/liquidation_passive_20260930"


def audit_passive(output=OUT, event_base=BASE, symbol="BTCUSDT"):
    spec = json.loads((output / "specification.json").read_text())
    result = json.loads((output / "results.json").read_text())
    for path, sha in spec["code_sha256"].items():
        source = ROOT / path
        if digest(source) != sha:
            source = output / "code_snapshot" / Path(path).name
        assert source.exists() and digest(source) == sha
    tapes, books = {}, {}
    for audit in result["source_audits"]:
        day, kind = audit["date"], audit["kind"]
        cache = output / "panels" / f"{day}_{kind}.parquet"
        assert digest(cache) == audit["panel_sha256"]
        source = (event_base / "raw/book_snapshot_5" if kind == "book" else output / "raw/trades") / day / f"{symbol}.csv.gz"
        assert digest(source) == audit["source_sha256"]
        assert digest(event_base / "panels" / f"{day}_events.parquet") == audit["events_sha256"]
        if "event_sha256" in spec:
            assert audit["events_sha256"] == spec["event_sha256"][day]
        data = pd.read_parquet(cache)
        assert data.local_us.is_monotonic_increasing and data.exchange_us.is_monotonic_increasing
        if kind == "trades":
            assert data.id.is_unique
            tapes[day] = data
        else:
            books[day] = data
    priced_count, source_fills, max_error, nofill_checks = 0, 0, 0., 0
    for name, candidate in result["results"].items():
        for scenario_name, expected in candidate["scenarios"].items():
            attempts = pd.read_parquet(output / f"{name}_{scenario_name}_attempts.parquet")
            scenario = spec["scenarios"][scenario_name]
            totals = dict.fromkeys(spec["dates"], 0.)
            free, unresolved = {}, set()
            for row in attempts.to_dict("records"):
                day, status = row["date"], row["status"]
                assert day not in unresolved
                if status == "skipped_busy":
                    assert row["send_us"] <= free[day]
                    continue
                assert row["send_us"] > free.get(day, -1)
                if status.startswith("skipped_") or status.startswith("predecision_"):
                    continue
                delay = scenario["delay_us"]
                assert row["signal_local_us"] < row["received_us"]
                assert row["send_us"] == row["received_us"] + 250000
                assert row["activation_us"] == row["send_us"] + delay
                assert row["cancel_arrival_us"] == row["activation_us"] + 5_000_000
                assert row["cancel_ack_us"] == row["cancel_arrival_us"] + delay
                assert row["exit_send_us"] >= row["cancel_ack_us"]
                assert row["exit_us"] == row["exit_send_us"] + delay
                assert row["intended_quantity"] <= .1 * row["signal_depth"] + 1e-12
                assert row["intended_quantity"] * row["entry"] <= 1000 + 1e-8
                if status.startswith("unresolved"):
                    unresolved.add(day)
                    continue
                if status == "post_only_rejected":
                    free[day] = row["free_at_us"]
                    continue
                tape = tapes[day]
                inside = tape.exchange_us.gt(row["activation_us"]) & tape.exchange_us.lt(row["cancel_arrival_us"])
                signed = tape.side.eq("sell" if row["direction"] == 1 else "buy")
                distance = row["direction"] * (tape.price - row["entry"])
                crossed = distance.le(0) if scenario["fill_mode"] == "touch_partial" else distance.lt(0)
                eligible = tape.loc[inside & signed & crossed]
                if status == "no_proxy_fill":
                    assert eligible.empty
                    nofill_checks += 1
                    free[day] = row["free_at_us"]
                    continue
                assert status == "priced"
                priced_count += 1
                fills = row["entry_fills"]
                source_fills += len(fills)
                expected_qty = row["intended_quantity"] if scenario["fill_mode"] == "through_full" else min(row["intended_quantity"], eligible.amount.sum())
                actual_qty = sum(f["quantity"] for f in fills)
                assert abs(actual_qty - expected_qty) < 1e-10
                assert abs(actual_qty - row["quantity"]) < 1e-10
                assert abs(actual_qty - row["closed_quantity"]) < 1e-10
                eligible_by_id = eligible.set_index("id")
                for fill in fills:
                    source = eligible_by_id.loc[fill["source_id"]]
                    assert fill["time_us"] == source.exchange_us
                    assert fill["source_price"] == source.price and fill["source_amount"] == source.amount
                    if scenario["fill_mode"] != "through_full":
                        assert fill["quantity"] <= source.amount + 1e-12
                    assert fill["price"] == row["entry"]
                book = books[day]
                index = np.searchsorted(book.exchange_us.to_numpy(), row["exit_us"], side="left") - 1
                physical = book.iloc[index]
                assert physical.exchange_us == row["exit_quote_exchange_us"]
                assert 0 <= row["exit_us"] - physical.exchange_us <= 250000
                side = "bids" if row["direction"] == 1 else "asks"
                prices = np.array([physical[f"{side}[{level}].price"] for level in range(5)])
                sizes = np.array([physical[f"{side}[{level}].amount"] for level in range(5)])
                taken = np.minimum(sizes, np.maximum(actual_qty - np.r_[0., np.cumsum(sizes)[:-1]], 0.))
                assert abs(taken.sum() - actual_qty) < 1e-10
                exit_value = (taken * prices).sum()
                assert abs(exit_value / actual_qty - row["exit"]) < 1e-8
                entry_value = actual_qty * row["entry"]
                gross = row["direction"] * (exit_value - entry_value)
                maker, taker, adverse = entry_value * scenario["maker_bps"] / 10000, exit_value * scenario["taker_bps"] / 10000, exit_value / 10000
                pnl = gross - maker - taker - adverse
                max_error = max(max_error, abs(pnl - row["pnl"]))
                assert abs(pnl - row["pnl"]) < 1e-8
                assert abs(maker - row["maker_fee"]) < 1e-8 and abs(taker - row["taker_fee"]) < 1e-8
                totals[day] += pnl
                free[day] = row["free_at_us"]
                assert free[day] == row["exit_us"] + delay
            for day in expected["daily"]:
                assert day["complete"] == (day["date"] not in unresolved)
                assert abs(totals[day["date"]] - day["closed_subtotal"]) < 1e-8
            assert expected["complete"] == (not unresolved)
            assert abs(sum(totals.values()) - expected["closed_subtotal"]) < 1e-8
    eligible = [name for name, candidate in result["results"].items()
                if all(s["complete"] and s["net_dollars"] > 0 for s in candidate["scenarios"].values())
                and candidate["scenarios"]["base"]["net_without_best_date"] > 0]
    assert eligible == result["candidates_for_additional_evidence"]
    audit = {"verified": True, "priced_trades_across_dependent_scenarios": priced_count,
             "maker_fill_records_checked_against_source_tape": source_fills,
             "no_fill_attempts_verified_against_source_tape": nofill_checks,
             "maximum_pnl_error_dollars": max_error, "edge_established": False}
    (output / "verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    return audit


def main():
    audit = audit_passive()
    result = json.loads((OUT / "results.json").read_text())
    source_fills = audit["maker_fill_records_checked_against_source_tape"]
    nofill_checks = audit["no_fill_attempts_verified_against_source_tape"]
    max_error = audit["maximum_pnl_error_dollars"]
    lines = ["PASSIVE LIQUIDATION HFT — 2026-09-30", "", "VERDICT: NO CANDIDATE PROGRESSES. Goal remains active; user requires strictly HFT.",
             "", "Eight frozen variants: follow/reverse the unchanged liquidation direction; 8/16bp passive offset; 30/120-second holds after cancellation acknowledgement.",
             "The 124 event clocks and reported-notional threshold are unchanged from the earlier study. This is development on exposed dates, not untouched validation.",
             "Six public trade files total 197,337,074 compressed bytes, acquired without authentication or paid data. Source raw capture clocks, exchange clocks and trade IDs validated.",
             f"Book and trade audits cover {sum(a['raw_rows'] for a in result['source_audits']):,} raw rows; fixed event windows preserve causal decisions and physical exchange-time execution.",
             "", "EXECUTION",
             "3bp maker entry, 6bp taker exit, 1bp extra adverse exit allowance; actual five-level exit prices. One-second outbound baseline, three-second stress; doubled fees, full-first-through and touch-price fill sensitivities.",
             "Orders are post-only with fixed five-second resting windows. All inferred partial inventory remains until cancel acknowledgement, hold and market exit. Unknown submitted execution invalidates the day.",
             "$10000 daily starting cash, $1000 maximum order, <=10% predecision touch quantity. Isolated-date P&L is not a continuous competition wealth path.",
             "", "BASELINE: rule | gross dollars | net dollars | completed trades"]
    for name, candidate in result["results"].items():
        base = candidate["scenarios"]["base"]
        lines.append(f"{name} | {base['gross_closed_subtotal']:+.6f} | {base['net_dollars']:+.6f} | {base['trades']}")
    lines += ["", "Six baseline variants lose; two produce no modeled fills. Zero fills are an absence of executable evidence in these samples, not proof of universal negative profitability.",
              "The least-negative traded baseline is reverse/16bp/120s: +$2.2995 gross, -$0.6085 net on three trades. Doubled fees give -$3.2256; three-second delay -$1.9254; touch-price fills -$1.0145.",
              "Most posted quotes never traded. Lower entry fees did not overcome the sampled adverse price moves and exit costs.",
              "", "VERIFICATION AND LIMITS",
              f"Independent audit checked {source_fills} maker-fill records and {nofill_checks} no-fill attempts against the source tape across dependent scenarios. P&L reconciles within ${max_error:.3g}.",
              "Six focused tests cover strict trade-through boundaries and aggressor sides, partial inventory, cancellation timing, full-fill sensitivity, unknown executions and fixed event windows.",
              "Strict-through and touch-price assumptions are counterfactual models, not proof of actual queue priority or fills. No market-impact or live-routing evidence is available.",
              "Six calendar-selected dates cannot establish broad reliability. No later validation dates were opened after this failure; no candidate was rescued by cheaper costs or a changed event threshold.",
              "Current search: 68 configurations / 92 evaluated implementation versions, all dependent and retaining previous historical selection exposure. No reliable edge or competition win established.",
              "", "Official sources:", "https://docs.tardis.dev/downloadable-csv-files/data-types", "https://www.binance.com/en-BH/fee/futureFee", ""]
    (OUT / "REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint.update(current_configurations=68, implementation_versions=92, focused_tests_total=64,
                      user_constraints={"universe": ["stocks", "ETFs", "crypto"], "strictly_hft": True,
                                        "costs": "conservative", "primary_metrics": ["raw outperformance", "actual edge reliability"]},
                      passive_liquidation_candidates=[], passive_liquidation_accounting_verified=True,
                      report=str(OUT / "REPORT.txt"),
                      remaining_evidence_work="Keep strictly HFT. Investigate a distinct informational mechanism or justified cross-asset replication; exclude slower intraday cadence-blocked ETF rules.")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
