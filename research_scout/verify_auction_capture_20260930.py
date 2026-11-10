"""Independent interval cashflow and native capture-window checks."""

from __future__ import annotations

import json

import databento as db
import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.run_auction_capture_20260930 import OUT, PREVIOUS, ROOT


def sound(frame):
    values = frame[["bid", "ask", "bid_qty", "ask_qty"]].to_numpy(float)
    return bool(len(frame) and not frame.missing_boundary.any()
                and not (frame["flags"].to_numpy(int) & 12).any()
                and np.isfinite(values).all() and (values > 0).all() and (values[:, :2] < 1e7).all()
                and (frame.bid < frame.ask).all())


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    result = json.loads((OUT / "results.json").read_text())
    for filename, sha in spec["code_sha256"].items():
        assert digest(ROOT / filename) == sha
    assert digest(PREVIOUS / "specification.json") == spec["previous_spec_sha256"]
    assert digest(PREVIOUS / "auction_inputs.parquet") == spec["auction_inputs_sha256"]
    assert json.loads((PREVIOUS / "verification.json").read_text())["verified"]
    cache, signals = {}, {}
    native_dates = {}
    for day in spec["dates"]:
        native_dates.setdefault(day[:4], day)
    native_groups, native_rows = 0, 0
    for audit in result["source_audits"]:
        day = audit["date"]
        filename = OUT / "envelopes" / f"{day}.parquet"
        assert digest(filename) == audit["cache_sha256"]
        assert digest(ROOT / audit["source_path"]) == audit["source_sha256"]
        envelope = pd.read_parquet(filename)
        cache[day] = {(symbol, label, int(width)): group for (symbol, label, width), group
                      in envelope.groupby(["symbol", "label", "alignment_ms"], sort=False)}
        old = pd.read_parquet(PREVIOUS / "panels" / f"{day}.parquet")
        signals[day] = {(r["symbol"], r["label"]): r for r in old.to_dict("records")}
        if day in native_dates.values():
            raw = db.DBNStore.from_file(str(ROOT / audit["source_path"])).to_df().reset_index()
            for (symbol, _, _), group in cache[day].items():
                source = raw.loc[raw.symbol.astype(str).eq(symbol) & (raw["flags"].to_numpy(int) & 128 != 0)].reset_index(drop=True)
                source["source_position"] = np.arange(len(source))
                low, high = int(group.window_low_ns.iloc[0]), int(group.window_high_ns.iloc[0])
                low_time, high_time = pd.Timestamp(low, tz="UTC"), pd.Timestamp(high, tz="UTC")
                before = source.loc[source.ts_recv.lt(low_time)].tail(1)
                inside = source.loc[source.ts_recv.ge(low_time) & source.ts_recv.le(high_time)]
                if before.empty or source.ts_recv.iloc[-1] <= high_time:
                    assert group.missing_boundary.all()
                else:
                    expected = pd.concat([before, inside])
                    assert not group.missing_boundary.any()
                    assert expected.source_position.tolist() == group.source_position.tolist()
                    assert expected.ts_recv.dt.as_unit("ns").astype("int64").tolist() == group.receive_ns.tolist()
                    assert expected.ts_event.dt.as_unit("ns").astype("int64").tolist() == group.event_ns.tolist()
                    for col, native in (("bid", "bid_px_00"), ("ask", "ask_px_00"), ("bid_qty", "bid_sz_00"), ("ask_qty", "ask_sz_00"), ("flags", "flags")):
                        np.testing.assert_allclose(group[col].to_numpy(float), expected[native].to_numpy(float), rtol=0, atol=0, equal_nan=True)
                    native_rows += len(group)
                native_groups += 1
    print(f"Verified {len(cache)} cache/source hashes and {native_groups} native calendar-sampled envelopes", flush=True)
    bounded, unknown, rejected, mixed, max_error = 0, 0, 0, 0, 0.
    ledger_hashes = {}
    for name, candidate in result["results"].items():
        base = None
        old = pd.read_parquet(PREVIOUS / "precise_ledgers" / f"{name}_base_attempts.parquet")
        decisions = ["date", "symbol", "underlying_prediction", "projected_return", "quantity", "signal_ask", "signal_ask_qty", "expected_net"]
        hold = int(name.rsplit("_", 1)[1][:-1])
        for scenario_name, summaries in candidate["scenarios"].items():
            scenario = spec["scenarios"][scenario_name]
            path = OUT / f"{name}_{scenario_name}_attempts.parquet"
            ledger_hashes[path.name] = digest(path)
            frame = pd.read_parquet(path)
            assert frame.date.tolist() == spec["dates"]
            pd.testing.assert_frame_equal(frame[decisions], old[decisions])
            if scenario_name == "base":
                base = frame
            for row in frame.to_dict("records"):
                if row["status"] in {"no_causal_signal", "predecision_unknown", "predecision_size", "below_cost_gate"}:
                    assert row["complete"] and row["pnl_lower"] == row["pnl_upper"] == 0
                    continue
                day, symbol, q = row["date"], row["symbol"], row["quantity"]
                delay, width = scenario["delay_s"], scenario["alignment_ms"]
                assert row["entry_target_ns"] == row["decision_ns"] + 250000000 + delay * 1000000000
                assert row["entry_ack_ns"] == row["entry_target_ns"] + delay * 1000000000
                assert row["exit_target_ns"] == row["entry_ack_ns"] + (hold + delay) * 1000000000
                assert row["exit_ack_ns"] == row["exit_target_ns"] + delay * 1000000000
                signal = signals[day][symbol, "signal"]
                assert q == np.floor(min(10000 / (1.01 * signal["ask"]), signal["ask_qty"] * .1))
                limit = np.floor(signal["ask"] * 1.0005 * 100) / 100
                assert row["limit"] == limit
                entry = cache[day][symbol, f"entry_{delay}", width]
                end = cache[day][symbol, f"exit_{delay}_{hold}", width]
                assert entry.target_ns.eq(row["entry_target_ns"]).all()
                assert end.target_ns.eq(row["exit_target_ns"]).all()
                if not sound(entry):
                    assert row["status"] == "unresolved_entry"
                else:
                    possible = entry.loc[entry.ask.le(limit + 1e-10)]
                    if possible.empty:
                        assert row["status"] == "rejected_fok" and row["complete"]
                        assert row["pnl_lower"] == row["pnl_upper"] == 0
                        rejected += 1
                        continue
                    if possible.ask_qty.lt(q).any():
                        assert row["status"] == "unresolved_entry_depth" and row["possible_open_quantity"] == q
                    elif not sound(end) or end.bid_qty.lt(q).any():
                        assert row["status"] == "unresolved_exit" and row["possible_open_quantity"] == q
                    else:
                        # Enumerate the cross-product of observed PRICE branches,
                        # independently of the replay's min/max shortcut.
                        buys = np.unique(possible.ask.to_numpy(float))[:, None]
                        sells = np.unique(end.bid.to_numpy(float))[None, :]
                        fees = (2 * max(1., .0075 * q) + q * (.00003 * sells + .0002)) * scenario["fee_multiplier"]
                        pnls = q * (sells - buys) - fees - q * (buys + sells) * scenario["adverse_bps"] / 10000
                        can_reject = bool(entry.ask.gt(limit + 1e-10).any())
                        lower, upper = float(pnls.min()), float(pnls.max())
                        assert abs(row["filled_pnl_lower"] - lower) < 1e-8
                        assert abs(row["filled_pnl_upper"] - upper) < 1e-8
                        if can_reject:
                            lower, upper = min(lower, 0.), max(upper, 0.)
                            mixed += 1
                        expected_status = "bounded_fill_or_reject" if can_reject else "bounded_fill"
                        assert row["status"] == expected_status and row["complete"]
                        max_error = max(max_error, abs(row["pnl_lower"] - lower), abs(row["pnl_upper"] - upper))
                        assert max_error < 1e-8
                        assert q * buys.max() + max(1., q * .0075) * scenario["fee_multiplier"] <= 10000 + 1e-8
                        bounded += 1
                        continue
                assert not row["complete"] and pd.isna(row["pnl_lower"]) and pd.isna(row["pnl_upper"])
                unknown += 1
            for key, group in {"all": frame, "development_2023_2024": frame.loc[frame.date.lt("2025-01-01")],
                               "selection_2025": frame.loc[frame.date.ge("2025-01-01")]}.items():
                summary = summaries[key]
                complete = bool(group.complete.all())
                assert summary["complete_under_model"] == complete
                assert abs(summary["resolved_subtotal_lower"] - group.pnl_lower.sum()) < 1e-8
                assert abs(summary["resolved_subtotal_upper"] - group.pnl_upper.sum()) < 1e-8
                assert (summary["net_lower"] is not None) == complete
            if scenario_name == "alignment_100ms":
                both = frame.complete & base.complete
                assert (frame.loc[both, "pnl_lower"] <= base.loc[both, "pnl_lower"] + 1e-8).all()
                assert (frame.loc[both, "pnl_upper"] >= base.loc[both, "pnl_upper"] - 1e-8).all()
        print(f"Verified cash and branches: {name}", flush=True)
    advance = []
    for name, candidate in result["results"].items():
        scenarios = candidate["scenarios"]
        base, dev = scenarios["base"]["selection_2025"], scenarios["base"]["development_2023_2024"]
        passed = (all(s["selection_2025"]["complete_under_model"] and s["selection_2025"]["net_lower"] > 0 for s in scenarios.values())
                  and dev["complete_under_model"] and dev["net_lower"] > 0
                  and base["known_fill_dates"] >= 50 and base["without_best_five_lower"] > 0)
        assert candidate["needs_additional_evidence"] == passed
        if passed:
            advance.append(name)
    assert advance == result["candidates_for_additional_evidence"]
    report = {"verified": True, "source_and_cache_hashes_checked": len(cache), "native_calendar_sample_dates": list(native_dates.values()),
              "native_envelopes_checked": native_groups, "native_state_rows_checked": native_rows,
              "bounded_dependent_scenario_attempts": bounded, "mixed_fill_or_reject_attempts": mixed,
              "unresolved_attempts_retained": unknown, "known_rejections": rejected,
              "maximum_cash_error_dollars": max_error, "ledger_sha256": ledger_hashes,
              "decisions_identical_to_original": True, "candidates_for_additional_evidence": advance,
              "scope": "Full cached branch/cash audit; native envelope verification on first eligible session of each year only. Model intervals are not guaranteed physical execution bounds or venue-fill validation.",
              "edge_established": False}
    (OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "ledger_sha256"}, indent=2))


if __name__ == "__main__":
    main()
