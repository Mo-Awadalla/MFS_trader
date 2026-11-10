"""Independent raw-line, book-transition, fill-branch and cash reconciliation."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.fetch_absorption_native_20260930 import OUT
from research_scout.run_absorption_hft_20260930 import ASSETS, DATES, ROOT, SCENARIOS
from research_scout.run_absorption_hft_20260930 import OUT as STUDY
from research_scout.verify_absorption_hft_20260930 import valid


def state_audit(state, quote):
    assert state["complete"], state.get("reason")
    proof, target, tick = state["proof"], state["target_us"], state["tick"]
    first = proof[0]
    assert first["local_us"] == quote["quote_local_us"] == state["source_local_us"]
    assert first["E_us"] == quote["quote_exchange_us"] == state["source_E_us"]
    assert first["T_us"] == state["source_T_us"] < target
    values = {s: {int(round(quote[f"{name}[{i}].price"] / tick)): quote[f"{name}[{i}].amount"] for i in range(5)}
              for s, name in (("b", "bids"), ("a", "asks"))}
    boundary = {"b": min(values["b"]), "a": max(values["a"])}
    assert boundary == state["boundary"]
    for side in values:
        for p, q in first[side]:
            key = round(float(p) / tick)
            if (side == "b" and key >= boundary[side]) or (side == "a" and key <= boundary[side]):
                assert math.isclose(float(q), values[side].get(key, 0.), rel_tol=1e-9, abs_tol=1e-9)
    variants, ties, before = [], 0, 0

    def save():
        snapshot = {s: [[p, q] for p, q in sorted(values[s].items(), reverse=s == "b")] for s in values}
        if snapshot not in variants:
            variants.append(snapshot)

    for prior, row in zip(proof, proof[1:], strict=False):
        assert not row["disconnect"]
        assert row["pu"] == prior["u"] and prior["u"] < row["u"] and row["U"] <= row["u"]
        assert row["T_us"] >= prior["T_us"] and row["local_us"] >= prior["local_us"]
        if row["T_us"] > target:
            assert row == proof[-1]
            save()
            break
        if row["T_us"] == target:
            ties += 1
            save()
        else:
            before += 1
        for side in values:
            updates = {round(float(p) / tick): float(q) for p, q in row[side]
                       if ((side == "b" and round(float(p) / tick) >= boundary[side])
                           or (side == "a" and round(float(p) / tick) <= boundary[side]))}
            values[side].update(updates)
            values[side] = {p: q for p, q in values[side].items() if q > 0}
        if values["a"] and values["b"]:
            assert min(values["a"]) > max(values["b"])
    assert proof[-1]["T_us"] > target
    assert variants == state["states"] and ties == state["timestamp_ties"] and before == state["updates_before_target"]


def price_variants(state, direction, quantity, limit=None):
    if not state["complete"]:
        return [("unknown", None)]
    output = []
    side = "a" if direction > 0 else "b"
    for variant in state["states"]:
        levels = np.array(variant[side], dtype=float).reshape(-1, 2)
        prices = levels[:, 0] * state["tick"]
        allowed = np.ones(len(prices), dtype=bool) if limit is None else direction * (prices - limit) <= 1e-8
        p, q = prices[allowed], levels[:, 1][allowed]
        cumulative = np.cumsum(q)
        if len(cumulative) and cumulative[-1] >= quantity - max(1e-10, quantity * 1e-10):
            takes = np.diff(np.r_[0., np.minimum(cumulative, quantity)])
            output.append(("fill", float(np.dot(p, takes))))
        elif limit is not None and ((~allowed).any() or direction * (state["boundary"][side] * state["tick"] - limit) >= -1e-8):
            output.append(("reject", None))
        else:
            output.append(("unknown", None))
    return output


def main():
    spec = json.loads((OUT / "replay_specification.json").read_text())
    result = json.loads((OUT / "results.json").read_text())
    manifest = json.loads((OUT / "manifest.json").read_text())
    assert digest(OUT / "manifest.json") == spec["raw_manifest_sha256"]
    for path, sha in spec["code_sha256"].items():
        assert digest(ROOT / path) == sha
    panels, signals, events, raw_needed = {}, {}, {}, defaultdict(dict)
    clocks, amended, stale, tied, target_count = [], 0, 0, 0, 0
    for audit in result["source_audits"]:
        symbol, day = audit["symbol"], audit["date"]
        assert digest(ROOT / audit["states_path"]) == audit["states_sha256"]
        states = json.loads(gzip.decompress((ROOT / audit["states_path"]).read_bytes()))
        states = {int(k): v for k, v in states.items()}
        qpath = STUDY / symbol / "panels" / f"{day}_quotes.parquet"
        epath = STUDY / symbol / "panels" / f"{day}_events.parquet"
        assert digest(qpath) == audit["quotes_sha256"] and digest(epath) == audit["events_sha256"]
        quotes = pd.read_parquet(qpath)
        executions = quotes.loc[quotes.clock_kind.eq("exchange")].drop_duplicates("target_us").set_index("target_us").to_dict("index")
        assert set(states) == set(executions)
        for target, state in states.items():
            quote = executions[target]
            state_audit(state, quote)
            target_count += 1
            tied += int(state["timestamp_ties"] > 0)
            clocks.append(state["source_E_us"] - state["source_T_us"])
            stale += int(quote["quote_age_us"] > 250000)
            initial = {s: [[round(quote[f"{name}[{i}].price"] / state["tick"]), quote[f"{name}[{i}].amount"]] for i in range(5)]
                       for s, name in (("b", "bids"), ("a", "asks"))}
            amended += int(any(v != initial for v in state["states"]))
            for row in state["proof"]:
                found = raw_needed[row["file"]].setdefault(row["line"], row)
                assert found == row
        panels[symbol, day] = states
        signals[symbol, day] = quotes.loc[quotes.label.eq("signal")].set_index("event_id").to_dict("index")
        events[symbol, day] = pd.read_parquet(epath)
        print(f"Checked native state transitions {symbol} {day}: {len(states)}", flush=True)
    raw_lines = 0
    for file in manifest["files"]:
        path = ROOT / file["path"]
        assert digest(path) == file["compressed_sha256"]
        payload = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(payload).hexdigest() == file["decoded_sha256"]
        needed = raw_needed.pop(file["path"], {})
        start = pd.Timestamp(file["date"], tz="UTC").value // 1000
        for number, line in enumerate(payload.splitlines()):
            if number not in needed:
                continue
            expected = needed.pop(number)
            stamp, data = line.split(b" ", 1)
            raw = json.loads(data)["data"]
            assert raw["s"] == file["symbol"] and raw["e"] == "depthUpdate"
            assert pd.Timestamp(stamp.decode()).value // 1000 - start == expected["local_us"]
            for clock in ("E", "T"):
                assert int(raw[clock]) * 1000 - start == expected[clock + "_us"]
            for key in ("U", "u", "pu"):
                assert int(raw[key]) == expected[key]
            for key in ("b", "a"):
                assert raw[key] == expected[key]
            raw_lines += 1
        assert not needed
    assert not raw_needed
    counts, max_error = Counter(), 0.
    for symbol, candidates in result["results"].items():
        for name, candidate in candidates.items():
            mechanism, hold = name.rsplit("_", 1)
            hold = int(hold[:-1])
            for scenario_name, summaries in candidate["scenarios"].items():
                scenario = SCENARIOS[scenario_name]
                ledger = pd.read_parquet(OUT / symbol / f"{name}_{scenario_name}_attempts.parquet")
                for day in DATES:
                    frame = ledger.loc[ledger.date.eq(day)]
                    expected = events[symbol, day].loc[events[symbol, day].mechanism.eq(mechanism)]
                    assert frame.event_id.tolist() == expected.event_id.tolist()
                    lo, hi, halted, free = 10000., 10000., False, -1
                    for row in frame.to_dict("records"):
                        if halted:
                            assert row["status"] == "skipped_unresolved_inventory" and not row["complete"]
                            assert pd.isna(row["pnl_lower"]) and pd.isna(row["pnl_upper"])
                            continue
                        direction, delay = row["direction"], scenario["delay_us"]
                        assert row["send_us"] == row["received_us"] + 250000 > free
                        assert row["entry_us"] == row["send_us"] + delay
                        assert row["entry_ack_us"] == row["entry_us"] + delay
                        assert row["exit_us"] == row["entry_ack_us"] + hold * 1000000 + delay
                        assert row["exit_ack_us"] == row["exit_us"] + delay
                        signal = signals[symbol, day][row["event_id"]]
                        if not valid(signal, False):
                            assert row["status"] == "predecision_unknown"
                            continue
                        side = "asks" if direction > 0 else "bids"
                        price, depth = signal[f"{side}[0].price"], signal[f"{side}[0].amount"]
                        tick, step = ASSETS[symbol]["tick_size"], ASSETS[symbol]["quantity_step"]
                        quantity = math.floor(min(1000 / price, .1 * depth) / step + 1e-10) * step
                        assert abs(row["quantity"] - quantity) < 1e-10
                        collar = price * (1 + direction * .0005) / tick
                        limit = (math.floor(collar) if direction > 0 else math.ceil(collar)) * tick
                        assert abs(limit - row["limit"]) < 1e-9
                        if quantity <= 0 or quantity * price < 100:
                            assert row["status"] == "predecision_size" and row["pnl_lower"] == row["pnl_upper"] == 0
                            continue
                        assert lo >= quantity * price * 1.02, "Unexpected capital branch; audit it before accepting"
                        ent = price_variants(panels[symbol, day][row["entry_us"]], direction, quantity, limit)
                        free = row["entry_ack_us"]
                        if any(x[0] == "unknown" for x in ent):
                            assert row["status"] == "unresolved_entry" and row["possible_open_quantity"] == quantity
                            halted = True
                        elif all(x[0] == "reject" for x in ent):
                            assert row["status"] == "rejected_fok" and row["complete"] and row["pnl_lower"] == row["pnl_upper"] == 0
                            counts["rejected_fok"] += 1
                            continue
                        else:
                            optional = any(x[0] == "reject" for x in ent)
                            assert bool(row["entry_optional"]) == optional
                            filled = [x[1] for x in ent if x[0] == "fill"]
                            assert abs(min(filled) - row["entry_notional_lower"]) < 1e-8
                            assert abs(max(filled) - row["entry_notional_upper"]) < 1e-8
                            ex = price_variants(panels[symbol, day][row["exit_us"]], -direction, quantity)
                            if any(x[0] != "fill" for x in ex):
                                assert row["status"] == "unresolved_exit" and row["possible_open_quantity"] == quantity
                                assert row["open_quantity"] == (0 if optional else quantity)
                                halted = True
                            else:
                                rate = (scenario["taker_bps"] + scenario["adverse_bps"]) / 10000
                                possible = [direction * (end - begin) - rate * (end + begin) for begin in filled for _, end in ex]
                                if optional:
                                    possible.append(0.)
                                    counts["mixed_fill_rejection"] += 1
                                lower, upper = min(possible), max(possible)
                                max_error = max(max_error, abs(lower - row["pnl_lower"]), abs(upper - row["pnl_upper"]))
                                assert max_error < 1e-8 and row["status"] == "bounded" and row["complete"]
                                assert row["closed_quantity"] == quantity
                                lo, hi = lo + lower, hi + upper
                                assert abs(lo - row["cash_lower"]) < 1e-8 and abs(hi - row["cash_upper"]) < 1e-8
                                free = row["exit_ack_us"]
                                counts["bounded_attempts"] += 1
                                continue
                        assert halted and not row["complete"] and pd.isna(row["pnl_lower"]) and pd.isna(row["pnl_upper"])
                        counts["unresolved_attempts"] += 1
                    summary = next(x for x in summaries["all"]["daily"] if x["date"] == day)
                    assert summary["complete"] == (not halted)
                    assert (summary["net_lower"] is None) == halted and (summary["net_upper"] is None) == halted
                    assert abs(summary["closed_lower"] - (lo - 10000)) < 1e-8
                    assert abs(summary["closed_upper"] - (hi - 10000)) < 1e-8
                for period, dates in (("all", DATES), ("development", DATES[:3]), ("selection", DATES[3:])):
                    subset = ledger.loc[ledger.date.isin(dates)]
                    summary = summaries[period]
                    assert summary["complete"] == bool(subset.complete.all())
                    assert abs(summary["closed_lower"] - subset.pnl_lower.sum()) < 1e-8
                    assert abs(summary["closed_upper"] - subset.pnl_upper.sum()) < 1e-8
            print(f"Reconciled all cash branches {symbol} {name}", flush=True)
    candidates = []
    for symbol, rules in result["results"].items():
        for name, rule in rules.items():
            passed = True
            for period in ("development", "selection"):
                b = rule["scenarios"]["base"][period]
                passed &= (all(s[period]["complete"] and s[period]["net_lower"] > 0 for s in rule["scenarios"].values())
                           and b["mandatory_trades"] >= 50 and b["positive_dates"] >= 2 and b["without_best_date"] > 0)
            assert passed == rule["needs_additional_evidence"]
            if passed:
                candidates.append(f"{symbol}/{name}")
    assert sorted(candidates) == sorted(result["candidates_for_additional_evidence"])
    verification = {"verified": True, "native_targets_checked": target_count, "native_raw_files_hashed": len(manifest["files"]),
                    "unique_raw_proof_lines_reconciled": raw_lines, "target_tie_branches": tied,
                    "formerly_stale_targets_with_continuous_native_state": stale,
                    "targets_with_any_native_state_different_from_E_asof_snapshot": amended,
                    "source_E_minus_T_us_percentiles": {str(p): float(np.percentile(clocks, p)) for p in (0, 50, 90, 99, 100)},
                    **counts, "maximum_cash_error_dollars": max_error, "candidates": candidates,
                    "scope": "All requested native targets and every submitted cash branch independently reconciled. Raw proof lines matched to original compressed files; every source file hashed. Conditional feed-state execution only, no live-fill guarantee; globally exposed discovery dates.",
                    "reliable_edge_established": False}
    (OUT / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
