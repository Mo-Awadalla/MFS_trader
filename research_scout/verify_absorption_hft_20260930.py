"""Check observed events, native as-of quotes and every submitted cashflow."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research.liquidation_event_replay import FIELDS
from research_scout.run_absorption_hft_20260930 import ASSETS, DATES, OUT, ROOT


def valid(row, physical):
    values = np.array([row[key] for key in FIELDS], float)
    if (not np.isfinite(values).all() or (values <= 0).any()
            or row["bids[0].price"] >= row["asks[0].price"]):
        return False
    for side, sign in (("bids", -1), ("asks", 1)):
        if not (np.diff([row[f"{side}[{i}].price"] for i in range(5)]) * sign > 0).all():
            return False
    if physical:
        return bool(not row["exchange_clock_ambiguous"] and 0 <= row["exchange_age_us"] <= 250000
                    and row["source_delay_us"] >= -1000)
    return bool(0 <= row["quote_age_us"] <= 1000000 and -1000 <= row["source_delay_us"] <= 2000000)


def walk(row, direction, q, limit=None):
    if not valid(row, True):
        return "unknown", None
    side = "asks" if direction == 1 else "bids"
    remainder, value = q, 0.
    for level in range(5):
        price, available = row[f"{side}[{level}].price"], row[f"{side}[{level}].amount"]
        if limit is not None and direction * (price - limit) > 1e-10:
            return "reject", None
        take = min(available, remainder)
        value += take * price
        remainder -= take
        if remainder <= 1e-12:
            return "fill", value
    return "unknown", None


def check_events(events, book, trade, tick):
    supports = events.loc[events.mechanism.eq("hold_fade")]
    assert not supports.received_us.diff().dropna().lt(60000000).any()
    indexed = supports.set_index("received_us").to_dict("index")
    for event in events.to_dict("records"):
        now = event["received_us"]
        assert (now - 60000000) // 3600000000 == (now + 115000000) // 3600000000
        if event["mechanism"] == "break_follow":
            parent = indexed[event["parent_us"]]
            assert 0 < now - event["parent_us"] <= 10000000
            assert event["direction"] == -parent["direction"]
            direction = parent["direction"]
            first_cross = None
            for clock in range(event["parent_us"] + 1000000, now + 1, 1000000):
                i = clock // 100000 - 1
                vals = np.array([book[k][i] for k in ("bid", "ask", "bid_qty", "ask_qty")])
                fresh = (np.isfinite(vals).all() and (vals > 0).all() and vals[0] < vals[1]
                         and 0 <= clock - book["local_us"][i] <= 500000
                         and -1000 <= book["local_us"][i] - book["exchange_us"][i] <= 1000000)
                crossed = (book["bid"][i] < parent["defended_price"] - tick / 2 if direction > 0
                           else book["ask"][i] > parent["defended_price"] + tick / 2)
                if fresh and crossed:
                    first_cross = clock
                    break
            assert first_cross == now
            continue
        i, direction = now // 100000 - 1, event["direction"]
        span = slice(i - 20, i + 1)
        clocks = np.arange(i - 19, i + 2, dtype=np.int64) * 100000
        vals = np.column_stack([book[k][span] for k in ("bid", "ask", "bid_qty", "ask_qty")])
        assert np.isfinite(vals).all() and (vals > 0).all() and (vals[:, 0] < vals[:, 1]).all()
        assert ((clocks - book["local_us"][span] >= 0) & (clocks - book["local_us"][span] <= 500000)).all()
        lag = book["local_us"][span] - book["exchange_us"][span]
        assert ((lag >= -1000) & (lag <= 1000000)).all()
        chosen = (trade["local_us"] >= now - 2000000) & (trade["local_us"] < now)
        assert (trade["exchange_us"][chosen] < now).all()
        lag = trade["local_us"][chosen] - trade["exchange_us"][chosen]
        assert ((lag >= -1000) & (lag <= 1000000)).all()
        price_key, depth_key = ("bid", "bid_qty") if direction > 0 else ("ask", "ask_qty")
        level, depth = book[price_key][i - 20], book[depth_key][i - 20]
        at_level = chosen & (trade["sell"] == (direction > 0)) & (np.abs(trade["price"] - level) <= tick * .4)
        volume, total = float(trade["amount"][at_level].sum()), float(trade["amount"][chosen].sum())
        assert volume >= 5 * depth - 1e-8 and volume / total >= .8 - 1e-12 and volume * level >= 10000 - 1e-8
        assert event["defended_price"] == level and event["anchor_depth"] == depth
        assert abs(event["at_level_volume"] - volume) < 1e-6
        assert abs(event["total_volume"] - total) < 1e-6
        if direction > 0:
            assert book["bid"][span].min() >= level - tick * .4
        else:
            assert book["ask"][span].max() <= level + tick * .4
    return len(supports), len(events) - len(supports)


def native_quotes(audit, panel):
    raw = pd.read_csv(ROOT / audit["book_source_path"], usecols=["local_timestamp", "timestamp", *FIELDS])
    start = pd.Timestamp(audit["date"], tz="UTC").value // 1000
    raw["local_timestamp"] -= start
    raw["timestamp"] -= start
    assert not raw.local_timestamp.diff().dropna().lt(0).any()
    count = 0
    for signal, column in ((True, "local_timestamp"), (False, "timestamp")):
        target = panel.loc[panel.label.eq("signal") == signal].sort_values("target_us")
        merged = pd.merge_asof(target[["target_us"]], raw.sort_values(column, kind="stable"),
                               left_on="target_us", right_on=column, direction="backward", allow_exact_matches=False)
        np.testing.assert_array_equal(target.quote_local_us.to_numpy(), merged.local_timestamp.fillna(-1).to_numpy())
        np.testing.assert_array_equal(target.quote_exchange_us.to_numpy(), merged.timestamp.fillna(-1).to_numpy())
        for field in FIELDS:
            np.testing.assert_allclose(target[field].to_numpy(), merged[field].to_numpy(), rtol=0, atol=0, equal_nan=True)
        count += len(target)
    return count


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    result = json.loads((OUT / "results.json").read_text())
    for filename, sha in spec["code_sha256"].items():
        assert digest(ROOT / filename) == sha
    panels, events_by_day = {}, {}
    parents, breaks, native_targets = 0, 0, 0
    for audit in result["source_audits"]:
        symbol, day = audit["symbol"], audit["date"]
        assert digest(ROOT / audit["book_source_path"]) == audit["book"]["source_sha256"]
        assert digest(ROOT / audit["book_cache_path"]) == audit["book"]["cache_sha256"]
        ta = audit["trades"]
        assert digest(ROOT / ta["source_path"]) == ta["source_sha256"]
        assert digest(ROOT / ta["cache_path"]) == ta["cache_sha256"]
        paths = {kind: OUT / symbol / "panels" / f"{day}_{kind}.parquet" for kind in ("events", "quotes")}
        for kind in paths:
            assert digest(paths[kind]) == audit[f"{kind}_sha256"]
        events, panel = pd.read_parquet(paths["events"]), pd.read_parquet(paths["quotes"])
        with np.load(ROOT / audit["book_cache_path"]) as raw:
            book = {key: raw[key] for key in raw.files}
        with np.load(ROOT / ta["cache_path"]) as raw:
            tape = {key: raw[key] for key in raw.files}
        n, m = check_events(events, book, tape, ASSETS[symbol]["tick_size"])
        parents, breaks = parents + n, breaks + m
        if day == DATES[0]:
            native_targets += native_quotes(audit, panel)
        panels[symbol, day] = {(r["event_id"], r["label"]): r for r in panel.to_dict("records")}
        events_by_day[symbol, day] = events
        print(f"Audited source events {symbol} {day}: {n} parents / {m} breaks", flush=True)
    fills, unknown, rejects, max_error = 0, 0, 0, 0.
    for symbol, candidates in result["results"].items():
        for name, candidate in candidates.items():
            mechanism, hold = name.rsplit("_", 1)
            hold = int(hold[:-1])
            for scenario_name, summaries in candidate["scenarios"].items():
                s = spec["scenarios"][scenario_name]
                ledger = pd.read_parquet(OUT / symbol / f"{name}_{scenario_name}_attempts.parquet")
                for day in DATES:
                    group = ledger.loc[ledger.date.eq(day)]
                    expected = events_by_day[symbol, day]
                    expected = expected.loc[expected.mechanism.eq(mechanism)]
                    assert group.event_id.tolist() == expected.event_id.tolist()
                    halted, cash, free_at = False, 10000., -1
                    for row in group.to_dict("records"):
                        if halted:
                            assert row["status"] == "skipped_unresolved_inventory" and not row["complete"] and pd.isna(row["pnl"])
                            continue
                        d, qid, direction = row["received_us"], row["event_id"], row["direction"]
                        delay = s["delay_us"]
                        assert row["send_us"] == d + 250000 and row["send_us"] > free_at
                        assert row["entry_us"] == d + 250000 + delay
                        assert row["entry_ack_us"] == row["entry_us"] + delay
                        assert row["exit_us"] == row["entry_ack_us"] + hold * 1000000 + delay
                        assert row["exit_ack_us"] == row["exit_us"] + delay
                        signal = panels[symbol, day][qid, "signal"]
                        if not valid(signal, False):
                            assert row["status"] == "predecision_unknown" and row["pnl"] == 0
                            continue
                        side = "asks" if direction > 0 else "bids"
                        price, depth = signal[f"{side}[0].price"], signal[f"{side}[0].amount"]
                        step, tick = ASSETS[symbol]["quantity_step"], ASSETS[symbol]["tick_size"]
                        q = math.floor(min(1000 / price, .1 * depth) / step + 1e-10) * step
                        assert abs(q - row["quantity"]) < 1e-10
                        if q <= 0 or q * price < 100:
                            assert row["status"] == "predecision_size" and row["pnl"] == 0
                            continue
                        if cash < q * price * 1.02:
                            assert row["status"] == "predecision_capital" and row["pnl"] == 0
                            continue
                        raw_limit = price * (1 + direction * .0005)
                        limit = (math.floor(raw_limit / tick) if direction > 0 else math.ceil(raw_limit / tick)) * tick
                        assert abs(row["limit"] - limit) < 1e-9
                        entry = panels[symbol, day][qid, f"entry_{delay}"]
                        status, entry_value = walk(entry, direction, q, limit)
                        free_at = row["entry_ack_us"]
                        if status == "reject":
                            assert row["status"] == "rejected_fok" and row["complete"] and row["pnl"] == 0
                            rejects += 1
                            continue
                        if status == "unknown":
                            assert row["status"] == "unresolved_entry" and row["possible_open_quantity"] == q
                        else:
                            assert abs(row["entry_notional"] - entry_value) < 1e-8
                            end = panels[symbol, day][qid, f"exit_{delay}_{hold}"]
                            status, exit_value = walk(end, -direction, q)
                            if status == "unknown":
                                assert row["status"] == "unresolved_exit" and row["open_quantity"] == q
                            else:
                                assert row["status"] == "priced" and row["complete"] and row["closed_quantity"] == q
                                pnl = direction * (exit_value - entry_value) - (entry_value + exit_value) * (s["taker_bps"] + s["adverse_bps"]) / 10000
                                max_error = max(max_error, abs(row["pnl"] - pnl))
                                assert max_error < 1e-8
                                cash += pnl
                                assert abs(row["cash_after"] - cash) < 1e-8
                                free_at = row["exit_ack_us"]
                                fills += 1
                                continue
                        assert not row["complete"] and pd.isna(row["pnl"])
                        halted = True
                        unknown += 1
                    summary = next(item for item in summaries["all"]["daily"] if item["date"] == day)
                    assert summary["complete"] == (not halted)
                    assert abs(summary["closed_subtotal"] - (cash - 10000)) < 1e-8
                    assert (summary["net_dollars"] is None) == halted
                for period, dates in (("all", DATES), ("development", DATES[:3]), ("selection", DATES[3:])):
                    group = ledger.loc[ledger.date.isin(dates)]
                    summary = summaries[period]
                    assert summary["complete"] == bool(group.complete.all())
                    assert abs(summary["closed_subtotal"] - group.pnl.sum()) < 1e-8
            print(f"Audited all execution scenarios: {symbol} {name}", flush=True)
    passing = []
    for symbol, candidates in result["results"].items():
        for name, candidate in candidates.items():
            good = True
            for period in ("development", "selection"):
                scenario = candidate["scenarios"]
                base = scenario["base"][period]
                good &= (all(v[period]["complete"] and v[period]["net_dollars"] > 0 for v in scenario.values())
                         and base["trades"] >= 50 and base["positive_dates"] >= 2 and base["without_best_date"] > 0)
            assert bool(good) == candidate["needs_additional_evidence"]
            if good:
                passing.append(f"{symbol}/{name}")
    assert passing == result["candidates_for_additional_evidence"]
    audit = {"verified": True, "support_events_checked": parents, "break_events_checked": breaks,
             "native_quote_target_checks": native_targets, "native_quote_dates": [DATES[0]],
             "native_quote_symbols": list(ASSETS), "priced_dependent_scenario_trades": fills,
             "unresolved_attempts_retained": unknown, "known_fok_rejections": rejects,
             "maximum_cash_error_dollars": max_error, "candidates_for_additional_evidence": passing,
             "scope": "All declared event conditions, first observed break clocks, cached order branches and cashflows checked. Does not independently prove exhaustiveness of event detection. Native quotes independently reconstructed for both instruments on the first calendar date; other dates rely on hashed cache/stream integrity. Replay fills are historical proxies, not actual live execution.",
             "reliable_edge_established": False}
    (OUT / "verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
