"""Independently check auction snapshots, sampled native quotes and every cashflow."""

from __future__ import annotations

import json

import databento as db
import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.run_auction_hft_20260930 import AUCTION, OUT, ROOT


def valid(row, max_age):
    prices_sizes = [row[key] for key in ("bid", "ask", "bid_qty", "ask_qty")]
    return (not row["ambiguous"] and not row["bad_flags"]
            and np.isfinite(prices_sizes).all() and min(prices_sizes) > 0
            and max(prices_sizes[:2]) < 1e7 and row["bid"] < row["ask"]
            and 0 <= row["age_ns"] <= max_age and row["source_delay_ns"] >= -1000000)


def fee_total(q, entry, exit_price, multiplier=1, adverse=1):
    return (2 * max(1., q * .0075) + q * (.00003 * exit_price + .0002)) * multiplier + q * (entry + exit_price) * adverse / 10000


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "results.json").read_text())
    repair = json.loads((OUT / "precise_ledgers/repair.json").read_text())
    assert repair["every_nonclock_column_identical"] and repair["signals_fills_costs_pnl_unchanged"]
    for source in repair["files"]:
        assert digest(ROOT / source["path"]) == source["sha256"]
    for name, sha in spec["code_sha256"].items():
        assert digest(ROOT / name) == sha
    assert digest(AUCTION) == spec["auction_source_sha256"] == results["auction_audit"]["source_sha256"]
    auction_path = OUT / "auction_inputs.parquet"
    assert digest(auction_path) == results["auction_audit"]["panel_sha256"]
    auction = pd.read_parquet(auction_path)
    archived = json.loads((ROOT / "research_scout/spy_auction_snapshots_v34.json").read_text())["snapshots"]
    previous = {(row["session_date"], row["cutoff"]): row for row in archived}
    for row in auction.to_dict("records"):
        old = previous[row["date"], "09:28:00" if row["label"] == "early" else "09:29:50"]
        assert row["receive_ns"] == pd.Timestamp(old["ts_recv"]).value
        assert row["event_ns"] == pd.Timestamp(old["ts_event"]).value
        for key in ("ref_price", "ind_match_price", "paired_qty", "total_imbalance_qty", "market_imbalance_qty", "auction_type", "side", "auction_status", "freeze_status"):
            assert row[key] == old[key]
        assert row["receive_ns"] < row["target_ns"]
    panels, audits = {}, {a["date"]: a for a in results["source_audits"]}
    # Calendar-fixed native spot checks; not selected for returns, fills or P&L.
    calendar_sample = {}
    for day in spec["dates"]:
        calendar_sample.setdefault(day[:7], day)
    raw_targets = 0
    for day in spec["dates"]:
        audit = audits[day]
        path = OUT / "panels" / f"{day}.parquet"
        assert digest(path) == audit["panel_sha256"]
        source = ROOT / audit["source_path"]
        assert digest(source) == audit["source_sha256"]
        panel = pd.read_parquet(path)
        panels[day] = {(row["symbol"], row["label"]): row for row in panel.to_dict("records")}
        for row in panel.to_dict("records"):
            source_time = row["receive_ns"] if row["clock"] == "capture" else row["event_ns"]
            if source_time >= 0:
                assert source_time < row["target_ns"]
                assert row["age_ns"] == row["target_ns"] - source_time
                assert row["source_delay_ns"] == row["receive_ns"] - row["event_ns"]
        if day in calendar_sample.values():
            raw = db.DBNStore.from_file(str(source)).to_df().reset_index()
            for row in panel.to_dict("records"):
                frame = raw.loc[raw.symbol.astype(str).eq(row["symbol"]) & (raw["flags"].to_numpy(int) & 128 != 0)]
                column = "ts_recv" if row["clock"] == "capture" else "ts_event"
                eligible = frame.loc[frame[column].lt(pd.Timestamp(row["target_ns"], tz="UTC"))]
                if eligible.empty:
                    assert row["receive_ns"] == -1
                    continue
                last = eligible.loc[eligible[column].eq(eligible[column].max())].iloc[-1]
                assert row["receive_ns"] == last.ts_recv.value and row["event_ns"] == last.ts_event.value
                for target, raw_key in (("bid", "bid_px_00"), ("ask", "ask_px_00"), ("bid_qty", "bid_sz_00"), ("ask_qty", "ask_sz_00")):
                    assert row[target] == last[raw_key] or (pd.isna(row[target]) and pd.isna(last[raw_key]))
                assert row["bad_flags"] == bool(int(last["flags"]) & (4 | 8))
                raw_targets += 1
    priced, unknown, rejections, max_cash_error = 0, 0, 0, 0.
    for name, candidate in results["results"].items():
        hold = int(name.rsplit("_", 1)[1][:-1])
        base_decisions = None
        for scenario_name, expected in candidate["scenarios"].items():
            scenario = spec["scenarios"][scenario_name]
            delay = scenario["delay_s"]
            frame = pd.read_parquet(OUT / "precise_ledgers" / f"{name}_{scenario_name}_attempts.parquet")
            assert frame.date.tolist() == spec["dates"]
            decision_columns = [key for key in ("date", "symbol", "underlying_prediction", "projected_return", "quantity", "signal_ask", "signal_ask_qty", "expected_net") if key in frame]
            decisions = frame[decision_columns]
            if base_decisions is None:
                base_decisions = decisions
            else:
                pd.testing.assert_frame_equal(base_decisions, decisions)
            for row in frame.to_dict("records"):
                status, day = row["status"], row["date"]
                if status in {"no_causal_signal", "predecision_unknown", "predecision_size"}:
                    assert row["complete"] and row["pnl"] == 0.
                    continue
                q = row["quantity"]
                signal = panels[day][row["symbol"], "signal"]
                assert valid(signal, 1000000000)
                assert q == np.floor(min(10000 / (signal["ask"] * 1.01), signal["ask_qty"] * .1))
                projected = signal["bid"] * (1 + row["projected_return"])
                expected_cash = q * (projected - signal["ask"]) - fee_total(q, signal["ask"], projected)
                assert abs(row["expected_net"] - expected_cash) < 1e-8
                if status == "below_cost_gate":
                    assert expected_cash <= q * signal["ask"] / 10000
                    assert row["complete"] and row["pnl"] == 0.
                    continue
                assert expected_cash > q * signal["ask"] / 10000
                entry = panels[day][row["symbol"], f"entry_{delay}"]
                end = panels[day][row["symbol"], f"exit_{delay}_{hold}"]
                assert row["entry_target_ns"] == row["decision_ns"] + 250000000 + delay * 1000000000
                assert row["entry_ack_ns"] == row["entry_target_ns"] + delay * 1000000000
                assert row["exit_target_ns"] == row["entry_ack_ns"] + (hold + delay) * 1000000000
                assert row["exit_ack_ns"] == row["exit_target_ns"] + delay * 1000000000
                limit = np.floor(signal["ask"] * 1.0005 * 100) / 100
                assert abs(row["limit"] - limit) < 1e-8
                if status == "unresolved_entry":
                    assert not valid(entry, 250000000)
                elif status == "rejected_fok":
                    assert valid(entry, 250000000) and entry["ask"] > limit + 1e-10
                    assert row["complete"] and row["pnl"] == 0.
                    rejections += 1
                    continue
                elif status == "unresolved_entry_depth":
                    assert valid(entry, 250000000) and entry["ask"] <= limit + 1e-10 and q > entry["ask_qty"]
                else:
                    assert valid(entry, 250000000) and entry["ask"] <= limit + 1e-10 and q <= entry["ask_qty"]
                    assert row["entry"] == entry["ask"]
                    if status == "unresolved_exit":
                        assert not valid(end, 250000000) or q > end["bid_qty"]
                        assert row["open_quantity"] == q
                    else:
                        assert status == "priced" and valid(end, 250000000) and q <= end["bid_qty"]
                        assert row["exit"] == end["bid"] and row["closed_quantity"] == q
                        assert q * row["entry"] + max(1., q * .0075) <= 10000 + 1e-8
                        cash = q * (end["bid"] - entry["ask"]) - fee_total(q, entry["ask"], end["bid"], scenario["fee_multiplier"], scenario["adverse_bps"])
                        max_cash_error = max(max_cash_error, abs(row["pnl"] - cash))
                        assert abs(row["pnl"] - cash) < 1e-8
                        assert row["complete"]
                        priced += 1
                        continue
                assert not row["complete"] and pd.isna(row["pnl"])
                unknown += 1
            groups = {"all": frame, "development_2023_2024": frame.loc[frame.date.lt("2025-01-01")],
                      "selection_2025": frame.loc[frame.date.ge("2025-01-01")]}
            for key, group in groups.items():
                summary = expected[key]
                complete = bool(group.complete.all())
                assert summary["complete"] == complete
                assert abs(summary["closed_subtotal"] - group.pnl.sum()) < 1e-8
                assert summary["trades"] == int(group.status.eq("priced").sum())
                assert (summary["net_dollars"] is not None) == complete
    advance = []
    for name, candidate in results["results"].items():
        scenarios = candidate["scenarios"]
        base = scenarios["base"]["selection_2025"]
        development = scenarios["base"]["development_2023_2024"]
        if (all(s["selection_2025"]["complete"] and s["selection_2025"]["net_dollars"] > 0 for s in scenarios.values())
                and development["complete"] and development["net_dollars"] > 0
                and base["trades"] >= 50 and base["net_without_best_five_dates"] > 0):
            advance.append(name)
    assert advance == results["candidates_for_additional_evidence"]
    report = {"verified": True, "archived_auction_snapshots_reconciled": len(auction),
              "quote_sources_hash_verified": len(audits), "calendar_selected_native_check_sessions": len(calendar_sample),
              "native_quote_targets_checked": raw_targets, "priced_trades_across_dependent_scenarios": priced,
              "unresolved_attempts_retained": unknown, "fok_rejections_checked": rejections,
              "maximum_cash_error_dollars": max_cash_error, "candidates_for_additional_evidence": advance,
              "edge_established": False,
              "scope": "Cash and cached execution checks cover every attempted path. Native as-of quote spot checks cover the first eligible date of each calendar month; this is not exhaustive native re-extraction of every target. Aggregated anonymized BBO remains a proxy, not proof of live venue execution."}
    (OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
