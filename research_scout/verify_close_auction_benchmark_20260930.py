"""Verify clock repair, conditional auction prices, next-quote references and cash."""

import json
import math
import warnings

import databento as db
import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.benchmark_close_auction_20260930 import DEST, INPUT, OUT, ROOT, STATS


def clock_and_signals():
    original = json.loads((OUT / "screen_verification.json").read_text())
    assert original["verified"] and original["native_asof_states_rebuilt"] == 1316
    spec = json.loads((INPUT / "specification.json").read_text())
    assert digest(ROOT / "research_scout/correct_close_auction_clock_20260930.py") == spec["code_sha256"]
    for path, sha in spec["source_panel_sha256"].items():
        assert digest(OUT / path) == sha
    prior = pd.read_parquet(OUT / "auction_inputs.parquet")
    fixed = pd.read_parquet(INPUT / "auction_inputs.parquet")
    quotes = pd.read_parquet(OUT / "quote_inputs.parquet")
    signals = pd.read_parquet(INPUT / "screen.parquet")
    cols = [c for c in prior if c != "auction_time_ns"]
    pd.testing.assert_frame_equal(prior[cols], fixed[cols], check_dtype=False)
    np.testing.assert_array_equal(prior.auction_time_ns.to_numpy(np.int64), fixed.raw_auction_time_ns.to_numpy(np.int64))
    expected = []
    for a, q, s in zip(fixed.to_dict("records"), quotes.to_dict("records"), signals.to_dict("records"), strict=True):
        raw = pd.Timestamp(int(a["raw_auction_time_ns"]), tz="UTC")
        if raw.value == s["close_ns"]:
            repaired, mode = raw.value, "already_utc"
        else:
            assert raw.date().isoformat() == s["date"] and raw.time().isoformat() == "16:00:00"
            repaired = raw.tz_localize(None).tz_localize("America/New_York").value
            mode = "legacy_new_york_wall_time_encoded_as_utc"
        assert a["auction_time_ns"] == repaired == s["close_ns"] and a["clock_mode"] == mode == s["clock_mode"]
        valid = (all(0 < s["decision_ns"] - a[k] <= 2000000000 for k in ("receive_ns", "event_ns"))
                 and all(0 < s["decision_ns"] - q[k] <= 250000000 for k in ("receive_ns", "event_ns"))
                 and a["auction_type"] == "C" and a["auction_status"] in (0, 1) and a["freeze_status"] == 0)
        nums = np.array([q["bid_px_00"], q["ask_px_00"], a["ind_match_price"], q["bid_sz_00"], q["ask_sz_00"], a["paired_qty"]], float)
        valid &= (np.isfinite(nums).all() and (nums > 0).all() and max(nums[:3]) < 1e7
                  and nums[0] < nums[1] and int(q["flags"]) & (4 | 8) == 0)
        qualifies = False
        if valid:
            quantity = math.floor(min(10000 / (q["ask_px_00"] * 1.01), .1 * q["bid_sz_00"], .01 * a["paired_qty"]))
            if quantity > 0 and quantity * a["ind_match_price"] >= 100:
                bid, price = q["bid_px_00"], a["ind_match_price"]
                fee = 2 * max(1., .0075 * quantity) + quantity * (.00003 * bid + .0002)
                assert quantity == s["quantity"]
                trial = np.array([s["limit"], s["limit"] + .01])
                margin = quantity * (bid - trial) - fee - quantity * (bid + trial) * .0001 - quantity * trial * .0002
                assert margin[0] >= -1e-9 and margin[1] < 1e-9
                net = quantity * (bid - price) - fee - quantity * (bid + price) * .0001
                assert abs(net - s["hypothetical_net"]) < 1e-8
                qualifies = a["side"] == "A" and a["total_imbalance_qty"] > 0 and price < s["limit"] - 1e-8
        assert bool(s["eligible"]) == bool(qualifies)
        if qualifies:
            expected.append(s["date"])
    result = {"verified": True, "dates_checked": len(signals), "native_raw_asof_evidence": original,
              "eligible_dates": expected, "all_non_schedule_fields_unchanged": True,
              "profitability_tested": False}
    (INPUT / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return signals.loc[signals.eligible]


def check_exits(panel):
    checked = 0
    for source, expected in panel.groupby("source"):
        pending = expected.sort_values("target_ns").copy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for chunk in db.DBNStore.from_file(str(ROOT / source)).to_df(count=200000, pretty_ts=False, price_type="fixed", map_symbols=False):
                f = chunk.reset_index()
                f = f.loc[f.instrument_id.eq(15144) & ((f["flags"].astype(int) & 128) != 0)]
                if not len(f):
                    continue
                ready = pending.loc[pending.target_ns.le(int(f.ts_recv.iloc[-1]))]
                if len(ready):
                    raw = pd.merge_asof(ready[["target_ns"]].astype({"target_ns": "int64"}), f.astype({"ts_recv": "int64"}),
                                        left_on="target_ns", right_on="ts_recv", direction="forward", allow_exact_matches=True)
                    np.testing.assert_array_equal(ready.receive_ns.to_numpy(np.int64), raw.ts_recv.to_numpy(np.int64))
                    np.testing.assert_array_equal(ready.event_ns.to_numpy(np.int64), raw.ts_event.to_numpy(np.int64))
                    for recorded, native in (("bid", "bid_px_00"), ("ask", "ask_px_00")):
                        np.testing.assert_allclose(ready[recorded].to_numpy(float), raw[native].to_numpy(float) / 1e9, rtol=0, atol=1e-10)
                    for recorded, native in (("bid_qty", "bid_sz_00"), ("ask_qty", "ask_sz_00"), ("flags", "flags")):
                        np.testing.assert_array_equal(ready[recorded].to_numpy(), raw[native].to_numpy())
                    checked += len(ready)
                    pending = pending.drop(ready.index)
                if not len(pending):
                    break
        assert not len(pending)
        print(f"Verified every first-after-target exit reference: {source}, {len(expected)}", flush=True)
    assert checked == len(panel)
    return checked


def main():
    signals = clock_and_signals().set_index("date").to_dict("index")
    spec = json.loads((DEST / "specification.json").read_text())
    results = json.loads((DEST / "results.json").read_text())
    for path, sha in spec["code_sha256"].items():
        assert digest(ROOT / path) == sha
    for path, sha in spec["source_sha256"].items():
        assert digest(ROOT / path) == sha
    assert digest(STATS) == spec["statistics_sha256"]
    for file, sha in results["evidence_sha256"].items():
        assert digest(DEST / file) == sha
    auctions = pd.read_parquet(DEST / "auction_references.parquet")
    raw_stats = db.DBNStore.from_file(str(STATS)).to_df(pretty_ts=False, price_type="fixed", map_symbols=False).reset_index()
    raw_stats = raw_stats.loc[raw_stats.instrument_id.eq(15144) & raw_stats.stat_type.eq(11)]
    for row in auctions.to_dict("records"):
        assert row["valid"] and row["official_rows"] == 1
        same = raw_stats.loc[raw_stats.ts_recv.eq(row["receive_ns"])]
        assert len(same) == 1
        # A mixed signed/unsigned numeric Series can coerce nanoseconds to
        # float64. Read columns directly to preserve exact integer clocks.
        assert int(same["ts_event"].iloc[0]) == row["event_ns"] and int(same["quantity"].iloc[0]) == row["quantity"]
        assert abs(int(same["price"].iloc[0]) / 1e9 - row["price"]) < 1e-10
        assert int(same["publisher_id"].iloc[0]) == 43 and int(same["update_action"].iloc[0]) == 1
    exits = pd.read_parquet(DEST / "exit_references.parquet")
    native_exits = check_exits(exits)
    q = {(r["date"], r["delay_s"], r["hold_s"]): r for r in exits.to_dict("records")}
    a = auctions.set_index("date").to_dict("index")
    cash_rows, outside, unknown, max_error = 0, 0, 0, 0.
    for hold, rule in results["results"].items():
        for scenario_name, summaries in rule["scenarios"].items():
            scenario = spec["scenarios"][scenario_name]
            ledger = pd.read_parquet(DEST / f"{hold}_{scenario_name}_ledger.parquet")
            for row in ledger.to_dict("records"):
                s, au, delay = signals[row["date"]], a[row["date"]], scenario["delay_s"]
                qty, price = int(s["quantity"]), au["price"]
                assert row["quantity"] == qty and row["limit"] == s["limit"] and not row["strategy_execution_verified"]
                if price > s["limit"] + 1e-9:
                    assert row["status"] == "outside_limit_no_reference_fill" and row["conditional_pnl"] == 0
                    outside += 1
                    continue
                assert qty <= au["quantity"]
                qr = q[row["date"], delay, int(hold[:-1])]
                ack = max(int(au["receive_ns"]), int(au["event_ns"]) + delay * 1000000000)
                assert qr["ack_ns"] == ack and qr["target_ns"] == ack + (int(hold[:-1]) + delay) * 1000000000 + 250000000
                invalid_wait = not 0 <= qr["receive_ns"] - qr["target_ns"] <= 1000000000
                invalid_book = (qr["bid"] <= 0 or qr["ask"] <= qr["bid"] or qr["ask"] >= 1e7
                                or qr["bid_qty"] < qty or qr["ask_qty"] <= 0 or int(qr["flags"]) & (4 | 8)
                                or qr["event_ns"] > qr["receive_ns"] + 1000000)
                if invalid_wait or invalid_book:
                    assert not row["conditional_complete"] and pd.isna(row["conditional_pnl"])
                    assert row["possible_open_quantity"] == qty
                    unknown += 1
                    continue
                gross = qty * (qr["bid"] - price)
                fee = 2 * max(1., qty * .0075) * scenario["fee_multiplier"]
                levy = qty * (qr["bid"] * .00003 + .0002) * scenario["fee_multiplier"]
                adverse = qty * (price + qr["bid"]) * scenario["adverse_bps"] / 10000
                expected = gross - fee - levy - adverse
                max_error = max(max_error, abs(expected - row["conditional_pnl"]))
                assert max_error < 1e-9 and row["conditional_complete"]
                assert row["status"] == "conditional_full_allocation"
                cash_rows += 1
            for period in ("all", "development_2023_2024", "selection_2025"):
                f = ledger if period == "all" else ledger.loc[ledger.date.lt("2025-01-01") == period.startswith("development")]
                summary = summaries[period]
                assert summary["conditional_complete"] == bool(f.conditional_complete.all())
                assert (summary["conditional_net"] is None) == (not summary["conditional_complete"])
                assert abs(f.conditional_pnl.sum() - summary["conditional_closed_subtotal"]) < 1e-9
    advanced = []
    for name, rule in results["results"].items():
        passed = True
        for period in ("development_2023_2024", "selection_2025"):
            base = rule["scenarios"]["base"][period]
            passed &= (all(s[period]["conditional_complete"] and s[period]["conditional_net"] > 0 for s in rule["scenarios"].values())
                       and base["positive_dates"] >= 3 and base["without_best_three"] > 0)
        assert rule["advance_to_allocation_evidence"] == passed
        if passed:
            advanced.append(name)
    assert advanced == results["advance_to_allocation_evidence"]
    verification = {"verified": True, "corrected_signal_dates": len(signals), "native_auction_prices_checked": len(auctions),
                    "native_exit_references_checked": native_exits, "dependent_conditional_cashflows_checked": cash_rows,
                    "outside_limit_dependent_paths": outside, "unresolved_conditional_paths": unknown,
                    "maximum_cash_error": max_error, "advance_to_allocation_evidence": advanced,
                    "scope": "Clock encoding repair, unchanged signal inputs, all eligible official auction prices, every first-after-target exit reference and conditional cashflow reconciled. This does not establish auction allocation, routing, actual fills or strategy profitability.",
                    "strategy_execution_verified": False, "reliable_edge_established": False}
    (DEST / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
