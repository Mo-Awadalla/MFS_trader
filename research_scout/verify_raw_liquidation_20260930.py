"""Independent event, physical fill, partial inventory and cash reconciliation."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.audit_force_order_full_20260930 import ASSETS, DATES, OUT, ROOT


def at(frame, clock, axis):
    index = np.searchsorted(frame[axis].to_numpy(), clock, side="left") - 1
    return frame.iloc[index] if index >= 0 else None


def depth_value(frame, clock, direction, quantity, limit=None):
    row = at(frame, clock, "exchange_us")
    if row is None or not 0 <= clock - row.exchange_us <= 250000 or row.local_us - row.exchange_us < -1000:
        return "unknown", None, row
    bids = np.array([row[f"bids[{level}].price"] for level in range(5)])
    asks = np.array([row[f"asks[{level}].price"] for level in range(5)])
    sizes_all = np.array([row[f"{side}[{level}].amount"] for level in range(5) for side in ("bids", "asks")])
    if (not np.isfinite(np.r_[bids, asks, sizes_all]).all() or (sizes_all <= 0).any()
            or (bids <= 0).any() or (asks <= 0).any() or bids[0] >= asks[0]
            or (np.diff(bids) >= 0).any() or (np.diff(asks) <= 0).any()):
        return "unknown", None, row
    side = "asks" if direction == 1 else "bids"
    prices = np.array([row[f"{side}[{level}].price"] for level in range(5)])
    sizes = np.array([row[f"{side}[{level}].amount"] for level in range(5)])
    needed = np.maximum(quantity - np.r_[0., np.cumsum(sizes)[:-1]], 0.)
    if limit is not None and ((direction * (prices - limit) > 1e-10) & (needed > 1e-12)).any():
        return "rejected", None, row
    taken = np.minimum(sizes, needed)
    if taken.sum() < quantity - 1e-12:
        return "unknown", None, row
    return "filled", float((taken * prices).sum()), row


def main():
    spec = json.loads((OUT / "strategy_specification.json").read_text())
    result = json.loads((OUT / "results.json").read_text())
    field_audit = json.loads((OUT / "field_audit.json").read_text())
    assert digest(OUT / "field_audit.json") == spec["field_audit_sha256"]
    assert digest(OUT / "orders.parquet") == spec["orders_sha256"]
    assert digest(OUT / "download_manifest.json") == field_audit["download_manifest_sha256"]
    for source, sha in spec["code_sha256"].items():
        assert digest(ROOT / source) == sha
    books, tapes, events_by_day, raw_sources = {}, {}, {}, set()
    for audit in result["source_audits"]:
        symbol, day, kind = audit["symbol"], audit["date"], audit["kind"]
        panel = OUT / symbol / "panels" / f"{day}_{kind}.parquet"
        assert digest(panel) == audit["panel_sha256"]
        source = ROOT / audit["source_path"]
        if str(source) not in raw_sources:
            assert digest(source) == audit["source_sha256"]
            raw_sources.add(str(source))
        events = OUT / symbol / "panels" / f"{day}_events.parquet"
        assert digest(events) == audit["events_sha256"]
        events_by_day[symbol, day] = pd.read_parquet(events)
        frame = pd.read_parquet(panel)
        assert frame.local_us.is_monotonic_increasing and frame.exchange_us.is_monotonic_increasing
        if kind == "book":
            books[symbol, day] = frame
        else:
            assert frame.id.is_unique
            tapes[symbol, day] = frame
    raw = pd.read_parquet(OUT / "orders.parquet")
    keep = np.array([row.local_timestamp >= pd.Timestamp(row.date, tz="UTC").value // 1000 + 300000000
                     for row in raw.itertuples()])
    for interval in spec["recovery_warmups"]:
        keep &= ~raw.local_timestamp.between(interval["recovery_local_timestamp"],
                                             interval["warmup_end_local_timestamp"], inclusive="left").to_numpy()
    raw = raw.loc[keep & raw.status.eq("FILLED").to_numpy()].copy()
    events_checked = 0
    for symbol in ASSETS:
        calibration = raw.loc[raw.symbol.eq(symbol) & raw.date.isin(DATES[:6])]
        threshold = float(np.quantile(calibration.filled_quantity * calibration.average_price, .99))
        assert abs(threshold - spec["threshold_executed_order_notional"][symbol]) < 1e-8
        for day in DATES[6:]:
            start = pd.Timestamp(day, tz="UTC").value // 1000
            source = raw.loc[raw.symbol.eq(symbol) & raw.date.eq(day)]
            selected, refractory = [], -1
            for row in source.itertuples():
                received = row.local_timestamp - start
                if row.filled_quantity * row.average_price < threshold or received < 60000000 or received > 86220000000 or received <= refractory:
                    continue
                selected.append((received, 1 if row.side == "buy" else -1, row.filled_quantity * row.average_price))
                refractory = received + 300000000
            actual = events_by_day[symbol, day]
            assert len(selected) == len(actual)
            for (received, side, notional), row in zip(selected, actual.itertuples(), strict=True):
                assert row.received_us == received and row.forced_side == side
                assert abs(row.reported_notional - notional) < 1e-8
                events_checked += 1
    priced, maker_fills, nofills, max_error = 0, 0, 0, 0.
    for candidate in result["results"].values():
        symbol, name = candidate["symbol"], candidate["name"]
        passive = name.startswith("passive_")
        hold = int(name.split("_")[-1][:-1])
        settings = spec["passive_scenarios"] if passive else spec["taker_scenarios"]
        for scenario_name, expected in candidate["scenarios"].items():
            params = settings[scenario_name]
            delay = params["delay_us"]
            attempts = pd.read_parquet(OUT / symbol / f"{name}_{scenario_name}_attempts.parquet")
            totals, free, unknown = dict.fromkeys(DATES[6:], 0.), {}, set()
            for row in attempts.to_dict("records"):
                day, status = row["date"], row["status"]
                assert day not in unknown
                event = events_by_day[symbol, day].set_index("event_id").loc[row["event_id"]]
                assert event.received_us == row["received_us"]
                assert row["send_us"] == row["received_us"] + 250000
                if status == "skipped_busy":
                    assert row["send_us"] <= free[day]
                    continue
                assert row["send_us"] > free.get(day, -1)
                if status.startswith("skipped_") or status.startswith("predecision_"):
                    continue
                book = books[symbol, day]
                signal = at(book, row["received_us"], "local_us")
                assert signal.local_us == row["signal_local_us"] and signal.local_us < row["received_us"]
                assert row["intended_quantity"] <= .1 * row["signal_depth"] + 1e-10
                signal_price = row["entry"] if passive else row["signal_price"]
                assert row["intended_quantity"] * signal_price <= 1000 + 1e-8
                assert abs(row["intended_quantity"] / ASSETS[symbol]["quantity_step"] - round(row["intended_quantity"] / ASSETS[symbol]["quantity_step"])) < 1e-7
                if passive:
                    assert row["activation_us"] == row["send_us"] + delay
                    assert row["cancel_arrival_us"] == row["activation_us"] + 5000000
                    assert row["cancel_ack_us"] == row["cancel_arrival_us"] + delay
                    assert row["exit_send_us"] == row["cancel_ack_us"] + hold * 1000000
                    arrival_status, _, arrival = depth_value(book, row["activation_us"], row["direction"], 1e-12)
                    if status == "unresolved_post_only":
                        assert arrival_status == "unknown"
                        unknown.add(day)
                        continue
                    assert arrival_status == "filled"
                    crosses = row["entry"] >= arrival["asks[0].price"] if row["direction"] == 1 else row["entry"] <= arrival["bids[0].price"]
                    if status == "post_only_rejected":
                        assert crosses
                        free[day] = row["free_at_us"]
                        continue
                    assert not crosses
                    tape = tapes[symbol, day]
                    signed = tape.side.eq("sell" if row["direction"] == 1 else "buy")
                    gap = row["direction"] * (tape.price - row["entry"])
                    through = gap.le(0) if params["fill_mode"] == "touch_partial" else gap.lt(0)
                    eligible = tape.loc[signed & through & tape.exchange_us.gt(row["activation_us"]) & tape.exchange_us.lt(row["cancel_arrival_us"])]
                    if status == "no_proxy_fill":
                        assert eligible.empty
                        free[day] = row["free_at_us"]
                        nofills += 1
                        continue
                    assert not eligible.empty
                    quantity = row["intended_quantity"] if params["fill_mode"] == "through_full" else min(row["intended_quantity"], eligible.amount.sum())
                    assert abs(quantity - row.get("quantity", row.get("open_quantity"))) < 1e-8
                    entry_value = quantity * row["entry"]
                    eligible = eligible.set_index("id")
                    for fill in row["entry_fills"]:
                        source = eligible.loc[fill["source_id"]]
                        assert fill["time_us"] == source.exchange_us and fill["source_price"] == source.price
                        assert fill["source_amount"] == source.amount and fill["price"] == row["entry"]
                        if params["fill_mode"] != "through_full":
                            assert fill["quantity"] <= source.amount + 1e-10
                        maker_fills += 1
                    assert abs(sum(fill["quantity"] for fill in row["entry_fills"]) - quantity) < 1e-10
                else:
                    assert row["entry_us"] == row["send_us"] + delay
                    assert row["entry_ack_us"] == row["entry_us"] + delay
                    assert row["exit_send_us"] == row["entry_ack_us"] + hold * 1000000
                    quantity = row["quantity"]
                    entry_status, entry_value, arrival = depth_value(book, row["entry_us"], row["direction"], quantity, row["limit"])
                    free[day] = row["entry_ack_us"]
                    if status == "rejected_fok":
                        assert entry_status == "rejected"
                        continue
                    if status == "unresolved_entry":
                        assert entry_status == "unknown"
                        unknown.add(day)
                        continue
                    assert entry_status == "filled"
                    assert abs(entry_value / quantity - row["entry"]) < 1e-8
                assert row["exit_us"] == row["exit_send_us"] + delay
                exit_status, exit_value, end = depth_value(book, row["exit_us"], -row["direction"], quantity)
                if status == "unresolved_exit":
                    assert exit_status == "unknown" and abs(row["open_quantity"] - quantity) < 1e-10
                    unknown.add(day)
                    continue
                assert status == "priced" and exit_status == "filled"
                assert abs(row["closed_quantity"] - quantity) < 1e-10
                assert abs(exit_value / quantity - row["exit"]) < 1e-8
                gross = row["direction"] * (exit_value - entry_value)
                if passive:
                    cost = entry_value * params["maker_bps"] / 10000 + exit_value * (params["taker_bps"] + 1) / 10000
                else:
                    cost = (entry_value + exit_value) * (params["taker_bps"] + 1) / 10000
                pnl = gross - cost
                max_error = max(max_error, abs(pnl - row["pnl"]))
                assert abs(pnl - row["pnl"]) < 1e-8
                totals[day] += pnl
                free[day] = row["exit_us"] + delay
                priced += 1
            assert expected["complete"] == (not unknown)
            assert abs(expected["closed_subtotal"] - sum(totals.values())) < 1e-8
            for day in expected["daily"]:
                assert day["complete"] == (day["date"] not in unknown)
                assert abs(day["closed_subtotal"] - totals[day["date"]]) < 1e-8
    advance = [key for key, candidate in result["results"].items()
               if all(s["complete"] and s["net_dollars"] > 0 for s in candidate["scenarios"].values())
               and candidate["scenarios"]["base"]["net_without_best_date"] > 0]
    assert advance == result["candidates_for_additional_evidence"]
    audit = {"verified": True, "native_events_reconstructed": events_checked,
             "priced_trades_across_dependent_scenarios": priced, "maker_fill_records": maker_fills,
             "no_fill_attempts_checked": nofills, "maximum_cash_error_dollars": max_error,
             "candidates_for_additional_evidence": advance, "edge_established": False}
    (OUT / "verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
