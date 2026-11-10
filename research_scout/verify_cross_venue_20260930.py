"""Independent fill cashflows, exposure, clock and frozen-source reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout/cross_venue_20260930"


def main():
    gate_spec = json.loads((BASE / "gate_specification.json").read_text())
    gate = json.loads((BASE / "gate_results.json").read_text())
    for name, expected in gate_spec["code_sha256"].items():
        assert digest(ROOT / name) == expected
    assert gate["opportunity_intervals"] == 4
    errors, known_fills, closed_attempts = [], 0, 0
    signal_panels, summaries = {}, {}
    for version in ("execution", "dual_clock"):
        folder = BASE / version
        spec = json.loads((folder / "specification.json").read_text())
        result = json.loads((folder / "results.json").read_text())
        summaries[version] = result["results"]
        for name, expected in spec["code_sha256"].items():
            source = ROOT / name
            if digest(source) != expected:
                source = folder / "code_snapshot" / Path(name).name
            assert source.exists() and digest(source) == expected, name
        assert digest(BASE / "opening_opportunities.parquet") == spec["events_sha256"]
        panels = []
        for audit in result["source_audits"]:
            p = folder / f"{audit['venue']}_{audit['date']}_quotes.parquet"
            assert digest(p) == audit["panel_sha256"]
            raw_base = ROOT / "research_scout/liquidation_event_20260930" if audit["venue"] == "binance" else BASE / "bybit"
            raw = raw_base / "raw/book_snapshot_5" / audit["date"] / "BTCUSDT.csv.gz"
            assert digest(raw) == audit["source_sha256"]
            panels.append(pd.read_parquet(p))
        panel = pd.concat(panels, ignore_index=True)
        signal = panel.loc[panel.label.eq("signal")].copy()
        assert (signal.quote_local_us < signal.target_us).all()
        signal_panels[version] = signal
        if version == "dual_clock":
            physical = panel.loc[~panel.label.eq("signal")]
            assert (physical.quote_exchange_us < physical.target_us).all()
            assert not (signal.clock_kind != "capture").any()
        for name, scenarios in result["results"].items():
            for scenario_name, expected in scenarios.items():
                prefix = folder / f"{name}_{scenario_name}"
                attempts = pd.read_parquet(str(prefix) + "_attempts.parquet")
                fills = pd.read_parquet(str(prefix) + "_fills.parquet")
                daily = pd.read_parquet(str(prefix) + "_daily.parquet")
                scenario = spec["scenarios"][scenario_name]
                totals = dict.fromkeys(spec["dates"], 0.)
                free, unresolved = {}, set()
                for attempt in attempts.to_dict("records"):
                    day, event = attempt["date"], int(attempt["event_id"])
                    assert day not in unresolved
                    if attempt["status"] == "skipped_busy":
                        assert attempt["send_us"] <= free[day]
                        continue
                    assert attempt["send_us"] > free.get(day, -1)
                    event_fills = fills.loc[fills.date.eq(day) & fills.event_id.eq(event)] if len(fills) else fills
                    for fill in event_fills.to_dict("records"):
                        known_fills += 1
                        assert abs(fill["notional"] - fill["quantity"] * fill["price"]) < 1e-8
                        assert abs(fill["fee"] - fill["notional"] * scenario["fee_bps"] / 10000) < 1e-10
                        assert abs(fill["adverse_cost"] - fill["notional"] / 10000) < 1e-10
                        assert abs(fill["quantity"] * 1000 - round(fill["quantity"] * 1000)) < 1e-8
                        states = panel.loc[panel.scenario.eq(scenario_name) & panel.horizon.eq(int(name.split('_')[1][:-1]))
                                           & panel.date.eq(day) & panel.event_id.eq(event) & panel.venue.eq(fill["venue"])
                                           & panel.label.eq(fill["label"])]
                        assert len(states) == 1
                        state = states.iloc[0]
                        assert fill["clock_us"] == state.target_us
                        if version == "dual_clock":
                            assert not state.exchange_clock_ambiguous
                            assert 0 <= state.exchange_age_us <= 250000
                        side = "asks" if fill["direction"] == 1 else "bids"
                        remaining, notional, levels = fill["quantity"], 0., 0
                        for level in range(5):
                            take = min(remaining, state[f"{side}[{level}].amount"])
                            price = state[f"{side}[{level}].price"]
                            if fill["label"] == "entry":
                                assert fill["direction"] * (price - attempt[f"{fill['venue']}_limit"]) <= 1e-8
                            notional += take * price
                            remaining -= take
                            levels = level + 1
                            if remaining <= 1e-12:
                                break
                        assert remaining <= 1e-12 and levels == fill["levels"]
                        assert abs(notional - fill["notional"]) < 1e-8
                        entry_arrivals = [attempt["send_us"] + scenario[f"{v}_us"] for v in ("binance", "bybit")]
                        ack = max(arrival + scenario[f"{v}_us"] for arrival, v in zip(entry_arrivals, ("binance", "bybit"), strict=True))
                        assert attempt["entry_ack_us"] == ack
                        if fill["label"] == "unwind":
                            assert fill["clock_us"] == ack + scenario[f"{fill['venue']}_us"]
                    if attempt["status"].startswith("unresolved"):
                        unresolved.add(day)
                        continue
                    if attempt["status"] == "both_rejected":
                        assert event_fills.empty and attempt["pnl"] == 0
                        free[day] = attempt["free_at_us"]
                        continue
                    if attempt["status"] not in ("closed_pair", "closed_single_leg"):
                        continue
                    closed_attempts += 1
                    count = 4 if attempt["status"] == "closed_pair" else 2
                    assert len(event_fills) == count
                    for _, group in event_fills.groupby("venue"):
                        assert abs((group.direction * group.quantity).sum()) < 1e-12
                    gross = -(event_fills.direction * event_fills.price * event_fills.quantity).sum()
                    fees = (event_fills.price * event_fills.quantity).sum() * scenario["fee_bps"] / 10000
                    adverse = (event_fills.price * event_fills.quantity).sum() / 10000
                    pnl = gross - fees - adverse
                    errors.append(abs(pnl - attempt["pnl"]))
                    assert errors[-1] < 1e-8
                    totals[day] += pnl
                    free[day] = attempt["free_at_us"]
                for d in daily.to_dict("records"):
                    assert d["complete"] == (d["date"] not in unresolved)
                    assert abs(d["closed_subtotal"] - totals[d["date"]]) < 1e-8
                assert expected["complete"] == (not unresolved)
                assert abs(expected["closed_subtotal"] - sum(totals.values())) < 1e-8
                assert expected["net_dollars"] is None if unresolved else abs(expected["net_dollars"] - sum(totals.values())) < 1e-8
    key = ["date", "event_id", "scenario", "horizon", "venue", "target_us"]
    fields = ["quote_local_us", "quote_exchange_us", *[f"{s}s[{i}].{f}" for i in range(5) for s in ("bid", "ask") for f in ("price", "amount")]]
    a, b = [signal_panels[v].set_index(key)[fields].sort_index() for v in ("execution", "dual_clock")]
    pd.testing.assert_frame_equal(a, b)
    base_signal = b.reset_index()
    base_signal = base_signal.loc[base_signal.scenario.eq("base") & base_signal.horizon.eq(30)]
    event_rows = []
    for event in json.loads((BASE / "dual_clock/specification.json").read_text())["events"]:
        rows = base_signal.loc[base_signal.event_id.eq(event["event_id"])].set_index("venue")
        long = "binance" if event["direction"] == "buy_binance_sell_bybit" else "bybit"
        short = "bybit" if long == "binance" else "binance"
        assert rows.loc[long, "asks[0].price"] == event["long_ask"]
        assert rows.loc[short, "bids[0].price"] == event["short_bid"]
        assert event["intended_btc"] <= .1 * min(rows.loc[long, "asks[0].amount"], rows.loc[short, "bids[0].amount"]) + 1e-12
        event_rows.append({"event_id": event["event_id"], "date": event["date"],
                           "bybit_capture_delay_ms": (rows.loc["bybit", "quote_local_us"] - rows.loc["bybit", "quote_exchange_us"]) / 1000})
    # Two holds do not create independent observations when no pair ever fills.
    for scenario in summaries["dual_clock"]["hold_30s"]:
        assert summaries["dual_clock"]["hold_30s"][scenario] == summaries["dual_clock"]["hold_120s"][scenario]
    audit = {"verified": True, "known_fills_across_dependent_versions_and_scenarios": known_fills,
             "closed_attempts_across_dependent_versions_and_scenarios": closed_attempts,
             "maximum_pnl_reconciliation_error": max(errors, default=0.),
             "all_frozen_signals_identical_between_execution_versions": True,
             "signal_capture_delays": event_rows, "edge_established": False}
    (BASE / "verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    erratum = ["RECEIPT-TIME EXECUTION ERRATUM", "",
               "The execution/ artifacts are preserved as a receipt-time proxy, not valid executable-edge evidence.",
               "The single apparent optimistic paired trade used a Bybit book captured almost a second after its exchange timestamp.",
               "dual_clock/ replays exactly the same signals and orders using exchange-time book states for fills, while decisions retain capture-time information.",
               "No paired trade completes after this correction. Every tested scenario loses on failed-pair single-leg unwinds.", ""]
    (BASE / "execution/ERRATUM.txt").write_text("\n".join(erratum), encoding="utf-8")
    lines = ["CROSS-VENUE BTCUSDT HFT — 2026-09-30", "", "VERDICT: NO RELIABLE EDGE. Goal remains active.",
             "", "Four opening-gap intervals cleared a fixed 33bp admission threshold across six July-December 2024 monthly-first-day samples.",
             "Three intervals fell within 18 seconds on October 1; these are not four independent market regimes.",
             "Costs: 6bp taker fee plus 1bp adverse allowance at every fill; two entries plus two exits cost about 28bp of one-leg notional.",
             "Capital: $10000 prefunded, $5000 per venue. Max $1000 per leg, equal BTC and at most 10% of both observed touch quantities.",
             "", "THE APPARENT WINNER WAS A TIMING ARTIFACT",
             "A receipt-time 200ms simulation showed +$1.0956 at 30 seconds and +$1.4548 at 120 seconds, entirely from one pair.",
             "Its Bybit signal book was captured 873ms after the exchange timestamp; its alleged entry state was captured 966ms after the exchange timestamp.",
             "These receive-time prices did not establish prices available at the exchange when our order would arrive.",
             "The corrected replay preserves all initial signals, sizes, collars, costs and latencies; decisions use capture time, executions use exchange time.",
             "", "CORRECTED RESULTS (30s and 120s holds identical because no paired position opened)",
             "scenario | net dollars across six isolated dates | closed pairs | single-leg unwinds"]
    for scenario, result in summaries["dual_clock"]["hold_30s"].items():
        lines.append(f"{scenario} | {result['net_dollars']:+.6f} | {result['closed_pairs']} | {result['closed_single_legs']}")
    lines += ["", "Three baseline attempts were rejected at both venues. One left an unmatched leg that had to be unwound after acknowledgements and another outbound trip.",
              "Unknown submitted-order outcomes invalidate a day, rather than becoming zero-profit observations. All corrected scenario paths in this batch are complete.",
              "The optimistic 200ms case is a diagnostic, not the baseline; it also loses. No fee, threshold or latency was relaxed to rescue the result.",
              "", "VERIFICATION",
              f"Independent reconciliation verified {known_fills} known fills across dependent scenarios and preserved versions, with maximum P&L discrepancy ${max(errors, default=0.):.3g}.",
              "Every signal book was identical between versions. Raw/cache/code hashes, strict clock ordering, causal collars, five-level weighted prices, per-venue flatness, acknowledgement timing and daily totals checked.",
              "Thirteen focused cross-venue tests pass, including partial venue failure, unknown execution, future capture isolation and exchange-clock backtrack handling.",
              "", "LIMITS AND SEARCH RECORD",
              "Calendar-selected historical samples and hypothetical fills cannot establish actual execution or broad statistical reliability. Neither public book timestamps nor captured prices are private order-execution logs.",
              "Orders are non-atomic across venues. No transfer, margin liquidation, exchange price-band rejection, queue impact or live routing is proven by this small replay.",
              "This adds two hold configurations, evaluated under both receipt- and exchange-time implementations: 60 configurations and 68 implementation versions in the current search. These are dependent, and earlier research exposure remains.",
              "The older cadence-blocked V21/V22/V24/V31/V46/V64 records are not negative-return evidence. They use slower intraday constructions and minute quote coverage; they do not presently validate an HFT edge.",
              "No later cross-venue validation dates were opened after this failure. No paid data API or trading order was sent.",
              "", "Source documentation:", "https://docs.tardis.dev/faq/data", "https://bybit-exchange.github.io/docs/v5/order/create-order", ""]
    (BASE / "REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    checkpoint = {"status": "active", "reliable_edge_found": False, "current_configurations": 60,
                  "implementation_versions": 68, "focused_tests_total": 58,
                  "cross_venue_opening_intervals": 4, "cross_venue_completed_pairs_after_correction": 0,
                  "cross_venue_base_net_dollars": summaries["dual_clock"]["hold_30s"]["base"]["net_dollars"],
                  "independent_accounting_verified": True, "report": str(BASE / "REPORT.txt"),
                  "remaining_evidence_work": "Consider exchange-time execution reconciliation for earlier receive-clock liquidation replay; do not label cadence-only rejections economic failures."}
    (ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json").write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
