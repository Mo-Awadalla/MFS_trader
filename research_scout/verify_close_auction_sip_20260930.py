"""Reconcile consolidated source units, state envelopes and conditional cash."""

import json

import databento as db
import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.run_close_auction_sip_20260930 import BENCH, DEFINITION, DEST, INPUT, ROOT


def main():
    spec = json.loads((DEST / "replay_specification.json").read_text())
    result = json.loads((DEST / "results.json").read_text())
    manifest = json.loads((DEST / "manifest.json").read_text())
    for path, sha in spec["code_sha256"].items():
        assert digest(ROOT / path) == sha
    for path, sha in result["output_sha256"].items():
        assert digest(DEST / path) == sha
    assert digest(DEST / "manifest.json") == spec["manifest_sha256"]
    assert digest(DEFINITION) == spec["source_definition_sha256"]
    signals = pd.read_parquet(INPUT / "screen.parquet")
    signals = signals.loc[signals.eligible].set_index("date").to_dict("index")
    auctions = pd.read_parquet(BENCH / "auction_references.parquet").set_index("date").to_dict("index")
    definition = db.DBNStore.from_file(str(DEFINITION)).to_df().reset_index()
    definition = definition.loc[definition.raw_symbol.eq("SPY")]
    tapes, times, expected_states = {}, {}, {}
    for source in manifest["files"]:
        assert digest(ROOT / source["path"]) == source["sha256"] and source["metadata"]["pagination_complete"]
        raw = pd.read_parquet(ROOT / source["path"])
        day = source["date"]
        clock = pd.to_datetime(raw.raw_timestamp, utc=True, format="ISO8601")
        pd.testing.assert_series_equal(clock, raw.timestamp, check_names=False)
        assert len(raw) == source["rows"] and clock.is_monotonic_increasing
        assert raw.page_index.diff().dropna().ge(0).all()
        prior = definition.loc[definition.ts_event.dt.as_unit("ns").astype("int64").lt(signals[day]["decision_ns"])].sort_values("ts_event")
        lot = int(prior.min_lot_size_round_lot.iloc[-1])
        assert lot == 100
        shares = raw.copy()
        factor = np.where(clock < pd.Timestamp("2025-11-03", tz="America/New_York"), lot, 1)
        shares["bid_size"] = raw.bid_size * factor
        shares["ask_size"] = raw.ask_size * factor
        tapes[day], times[day] = shares, clock.dt.as_unit("ns").astype("int64").to_numpy()
    panel = pd.read_parquet(DEST / "quote_envelopes.parquet")
    precise = panel.copy()
    exact = {k: [] for k in ("first_ns", "last_ns", "successor_ns")}
    clock_rounding_repairs, quote_states = 0, 0
    for row in panel.to_dict("records"):
        day, hold, scenario_name = row["date"], row["hold_s"], row["scenario"]
        scenario, frame, clock = spec["scenarios"][scenario_name], tapes[day], times[day]
        target = int(row["target_ns"])
        lo, hi = target - scenario["radius_ns"], target + scenario["radius_ns"]
        before = np.flatnonzero(clock < lo)
        after = np.flatnonzero(clock > hi)
        assert len(before) and len(after)
        ids = np.r_[before[-1], np.flatnonzero((clock >= lo) & (clock <= hi))]
        assert int(ids[0]) == row["first_index"] and int(after[0]) == row["stop_index"]
        selected = frame.iloc[ids]
        qty = int(signals[day]["quantity"])
        prices = selected[["bid_price", "ask_price", "bid_size", "ask_size"]].to_numpy(float)
        good = (np.isfinite(prices).all() and (prices > 0).all() and (prices[:, 0] < prices[:, 1]).all()
                and (prices[:, 1] < 1e7).all() and (prices[:, 2] >= qty).all()
                and all(json.loads(c) == ["R"] for c in selected.conditions)
                and selected.bid_exchange.str.len().gt(0).all() and selected.ask_exchange.str.len().gt(0).all())
        assert bool(row["complete"]) == bool(good)
        quote_states += len(selected)
        reconstructed = {"complete": bool(good), "bids": selected.bid_price.to_numpy(float)}
        expected_states[day, hold, scenario_name] = reconstructed
        for field, value in (("first_ns", int(clock[ids[0]])), ("last_ns", int(clock[ids[-1]])), ("successor_ns", int(clock[after[0]]))):
            if good:
                # Optional ns columns in the diagnostic panel were float-promoted
                # by missing-state rows. Repair only those annotations from raw
                # integer timestamps. Prices, indices, target clocks and P&L did
                # not depend on those annotations and must remain identical.
                assert abs(int(row[field]) - value) <= 128
                clock_rounding_repairs += int(int(row[field]) != value)
                exact[field].append(value)
            else:
                exact[field].append(None)
        if good:
            assert row["bid_lower"] == selected.bid_price.min() and row["bid_upper"] == selected.bid_price.max()
    for field, values in exact.items():
        precise[field] = pd.array(values, dtype="Int64")
    unchanged = [c for c in panel if c not in exact]
    pd.testing.assert_frame_equal(panel[unchanged], precise[unchanged])
    precise.to_parquet(DEST / "precise_quote_envelopes.parquet", index=False)
    priced, unknown, outside, max_error = 0, 0, 0, 0.
    for hold_name, rule in result["results"].items():
        hold = int(hold_name[:-1])
        for name, summaries in rule["scenarios"].items():
            scenario = spec["scenarios"][name]
            ledger = pd.read_parquet(DEST / f"{hold_name}_{name}_ledger.parquet")
            assert ledger.date.tolist() == list(signals)
            for row in ledger.to_dict("records"):
                day, q = row["date"], int(row["quantity"])
                au, signal = auctions[day], signals[day]
                assert q == signal["quantity"] and row["limit"] == signal["limit"] and row["auction_price"] == au["price"]
                assert not row["actual_strategy_execution_verified"]
                if au["price"] > signal["limit"] + 1e-9:
                    assert row["status"] == "outside_limit_no_reference_fill" and row["conditional_complete"]
                    assert row["conditional_pnl_lower"] == row["conditional_pnl_upper"] == 0
                    outside += 1
                    continue
                delay = scenario["delay_s"]
                ack = max(int(au["receive_ns"]), int(au["event_ns"]) + delay * 1000000000)
                assert row["ack_ns"] == ack and row["target_ns"] == ack + (hold + delay) * 1000000000 + 250000000
                state = expected_states[day, hold, name]
                if not state["complete"]:
                    assert not row["conditional_complete"] and row["possible_open_quantity"] == q
                    assert pd.isna(row["conditional_pnl_lower"]) and pd.isna(row["conditional_pnl_upper"])
                    unknown += 1
                    continue
                bids = state["bids"]
                comm = 2 * max(1., .0075 * q) * scenario["fee_multiplier"]
                sell = q * (bids * .00003 + .0002) * scenario["fee_multiplier"]
                adverse = q * (au["price"] + bids) * scenario["adverse_bps"] / 10000
                profits = q * (bids - au["price"]) - comm - sell - adverse
                assert row["conditional_complete"] and row["status"] == "conditional_full_allocation"
                max_error = max(max_error, abs(row["conditional_pnl_lower"] - profits.min()), abs(row["conditional_pnl_upper"] - profits.max()))
                assert max_error < 1e-8
                priced += 1
            for period in ("all", "development_2023_2024", "selection_2025"):
                f = ledger if period == "all" else ledger.loc[ledger.date.lt("2025-01-01") == period.startswith("development")]
                summary = summaries[period]
                complete = bool(f.conditional_complete.all())
                assert summary["conditional_complete"] == complete and (summary["net_lower"] is None) == (not complete)
                assert (summary["net_upper"] is None) == (not complete)
                assert abs(summary["closed_lower"] - f.conditional_pnl_lower.sum()) < 1e-8
                assert abs(summary["closed_upper"] - f.conditional_pnl_upper.sum()) < 1e-8
                if complete:
                    assert abs(summary["without_best_three"] - (f.conditional_pnl_lower.sum() - f.conditional_pnl_lower.nlargest(3).sum())) < 1e-8
    candidates = []
    for name, rule in result["results"].items():
        passed = True
        for period in ("development_2023_2024", "selection_2025"):
            base = rule["scenarios"]["base"][period]
            passed &= (all(s[period]["conditional_complete"] and s[period]["net_lower"] > 0 for s in rule["scenarios"].values())
                       and base["positive_dates"] >= 3 and base["without_best_three"] > 0)
        assert passed == rule["advance_to_allocation_evidence"]
        if passed:
            candidates.append(name)
    assert candidates == result["advance_to_allocation_evidence"]
    verification = {"verified": True, "source_dates": len(tapes), "native_sip_quotes": sum(len(t) for t in tapes.values()),
                    "envelopes_checked": len(panel), "dependent_quote_states_checked": quote_states,
                    "dependent_conditional_cashflows_checked": priced, "unknown_conditional_paths_retained": unknown,
                    "outside_limit_dependent_paths": outside, "maximum_cash_error": max_error,
                    "optional_clock_annotations_repaired": clock_rounding_repairs,
                    "clock_repair_scope": "Ancillary optional first/last/successor source ns annotations only; maximum128ns original float promotion. Exact integer quote indices, target/ACK clocks, prices, sizes and P&L unchanged. Original panel retained.",
                    "precise_envelopes_sha256": digest(DEST / "precise_quote_envelopes.parquet"),
                    "advance_to_allocation_evidence": candidates, "actual_strategy_execution_verified": False,
                    "reliable_edge_established": False}
    (DEST / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
