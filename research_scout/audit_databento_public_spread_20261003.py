"""Recompute every admission from raw CSV, stdlib integers and Decimal cash."""

import calendar
import csv
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

from research_scout.databento_public_spread_supply_20261003 import OUT, PARENT
from research_scout.prepare_databento_fast_20261002 import sha, write

DAY = calendar.timegm((2025, 9, 16, 0, 0, 0)) * 1000000000


def clock(text):
    assert text[:11] == "2025-09-16T" and text[-1] == "Z"
    whole, fraction = text[11:-1].split(".")
    hour, minute, second = (int(part) for part in whole.split(":"))
    assert len(fraction) <= 9
    return DAY + (3600 * hour + 60 * minute + second) * 1000000000 + int(fraction.ljust(9, "0"))


def price(text):
    if not text:
        return None
    whole, fraction = text.split(".")
    assert len(fraction) <= 9
    return int(whole) * 1000000000 + int(fraction.ljust(9, "0"))


def main():
    results = json.loads((OUT / "results.json").read_text())
    specification = json.loads((OUT / "specification.json").read_text())
    acquisition = json.loads((PARENT / "acquisition.json").read_text())
    source = next(s for s in acquisition["sources"] if s["schema"] == "mbp1")
    assert sha(Path(source["path"])) == source["sha256"]
    assert results["specification_sha256"] == sha(OUT / "specification.json")
    assert not (OUT / "independent_verification.json").exists()
    counters, eligible, best, best_ratio = Counter(), [], None, None
    start = calendar.timegm(datetime(2025, 9, 16, 9, 30, 5, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC).timetuple()) * 1000000000
    end = calendar.timegm(datetime(2025, 9, 16, 15, 59, 30, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC).timetuple()) * 1000000000
    with Path(source["path"]).open(newline="", encoding="utf-8") as handle:
        reader = enumerate(csv.DictReader(handle))
        upcoming = next(reader, None)
        upcoming_clock = clock(upcoming[1]["ts_recv"]) if upcoming else None
        latest = None
        for decision in range(start, end + 1, 10000000):
            counters["grid_cells"] += 1
            cutoff = decision - 1000000
            while upcoming and upcoming_clock < cutoff:
                latest = upcoming
                upcoming = next(reader, None)
                upcoming_clock = clock(upcoming[1]["ts_recv"]) if upcoming else None
            assert latest is not None
            index, row = latest
            bid, ask = price(row["bid_px_00"]), price(row["ask_px_00"])
            bq, aq = int(row["bid_sz_00"]), int(row["ask_sz_00"])
            if (bid is None or ask is None or not 5000000000 <= bid < ask <= 1000000000000
                    or bid % 10000000 or ask % 10000000 or bq <= 0 or aq <= 0 or not int(row["flags"]) & 128):
                counters["invalid_or_incomplete_book"] += 1
                continue
            if not (0 < cutoff - clock(row["ts_recv"]) <= 5000000 and 0 < cutoff - clock(row["ts_event"]) <= 5000000):
                counters["quote_age_rejected"] += 1
                continue
            if D(ask - bid) * 20000 / D(bid + ask) > 50:
                counters["spread_rejected"] += 1
                continue
            collar_cents = (ask // 10000000 * 102 + 99) // 100
            quantity = min(bq // 10, aq // 10, 1000000 // collar_cents)
            if quantity <= 0:
                counters["quantity_rejected"] += 1
                continue
            counters["computed_budgets"] += 1
            entry, sale = D(quantity) * D(bid) / 1000000000, D(quantity) * D(ask) / 1000000000
            net = sale - entry - 2 * max(D(1), D("0.005") * quantity)
            net -= D("0.0001") * (entry + sale) + D("0.00003") * sale + D("0.000166") * quantity
            net_units = int(net * 100000000000000)
            assert D(net_units) / 100000000000000 == net
            ratio = Fraction(net_units, quantity * bid)
            record = {"decision_ns": decision, "quote_source_row": index, "bid_price_int": bid, "ask_price_int": ask,
                      "quantity": quantity, "net_cash_units": net_units, "entry_notional_price_units": quantity * bid,
                      "projected_net_usd": net, "projected_net_bp": D(net_units) / (10 * D(quantity * bid))}
            if best_ratio is None or ratio > best_ratio:
                best, best_ratio = record, ratio
            counters["positive_budgets"] += int(net > 0)
            if net >= D("0.0002") * entry:
                counters["eligible_cells"] += 1
                eligible.append(record)
        final_index = upcoming[0] if upcoming else latest[0]
        for index, _ in reader:
            final_index = index
        assert final_index + 1 == specification["source"]["rows"]
    for key in ("grid_cells", "invalid_or_incomplete_book", "quote_age_rejected", "spread_rejected", "quantity_rejected",
                "computed_budgets", "positive_budgets", "eligible_cells"):
        assert counters[key] == results[key], (key, counters[key], results[key])

    def normalize(record):
        return {k: D(v) if k in ("projected_net_usd", "projected_net_bp") else v for k, v in record.items()}

    assert best == normalize(results["best_budget"])
    assert eligible == [normalize(r) for r in results["eligible"]]
    report = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "counts": dict(counters),
              "csv_rows_verified": final_index + 1, "source_sha256": source["sha256"],
              "results_sha256": sha(OUT / "results.json"), "auditor_sha256": sha(Path(__file__)),
              "scope": "Independent full-grid recomputation from original CSV with stdlib capture-clock parsing, whole-integer prices and Decimal fees. No Arrow, NumPy, production snapshot helper or production budget function used for admission.",
              "returns_calculated": False, "actual_execution_verified": False, "paid_calls": 0}
    write(OUT / "independent_verification.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
