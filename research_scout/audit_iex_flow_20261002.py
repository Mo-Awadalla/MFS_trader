"""Independently verify raw past-only two-sided flow counts and unchanged ranking."""

import gzip
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from research_scout.audit_iex_deep_20261002 import native, sha

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research_scout/iex_deep_hft_20261002"
OUT = ROOT / "research_scout/iex_flow_hft_20261002"


def one_day(day, expected_hash):
    path = OUT / "sessions" / (day + ".json")
    assert sha(path) == expected_hash
    result = json.loads(path.read_text())
    parent_path = PARENT / "sessions" / (day + ".json")
    assert sha(parent_path) == result["parent_session_sha256"]
    parent = json.loads(parent_path.read_text())
    candidates = parent["candidates"]
    assert len(candidates) == len(result["checks"])
    symbols = {c["symbol"] for c in candidates}
    source = Path(result["source_path"])
    assert sha(source) == parent["prefix_sha256"] == result["source_sha256"]
    cutoff = parent["decision_ns"] - 250_000_000
    assert cutoff == result["cutoff_ns"] and result["decision_ns"] == parent["decision_ns"]
    rows, count = [], 0
    if candidates:
        for row in native(source, cutoff):
            count += 1
            if row.get("symbol") not in symbols:
                continue
            if row["type"] == "B" or (row["type"] == "T" and row["event_ns"] >= cutoff - 30_000_000_000):
                rows.append(row)
        assert count == parent["messages_checked"]
    assert count == result["coverage"]["source_messages_checked"]
    records_path = Path(result["records_path"])
    assert sha(records_path) == result["records_sha256"]
    with gzip.open(records_path, "rt", encoding="utf-8") as handle:
        assert rows == [json.loads(line) for line in handle]
    qualified = []
    for old, reported in zip(candidates, result["checks"], strict=True):
        assert reported["candidate"] == old
        symbol, q = old["symbol"], old["quantity"]
        broken = {r["trade_id"] for r in rows if r["symbol"] == symbol and r["type"] == "B"}
        flow = [r for r in rows if r["symbol"] == symbol and r["type"] == "T"
                and r["flags"] & 88 == 0 and r["price"] > 0 and r["size"] > 0
                and r["trade_id"] not in broken]
        assert all(cutoff - 30_000_000_000 <= r["event_ns"] <= cutoff
                   and r["send_ns"] <= cutoff and r["capture_ns"] < cutoff for r in flow)
        assert len({r["trade_id"] for r in flow}) == len(flow)
        bid, ask = old["quote"]["bid_price"], old["quote"]["ask_price"]
        below = [r for r in flow if r["price"] <= bid]
        above = [r for r in flow if r["price"] >= ask]
        buy_times = len({r["event_ns"] for r in below})
        sell_times = len({r["event_ns"] for r in above})
        buy_qty, sell_qty = sum(r["size"] for r in below), sum(r["size"] for r in above)
        passes = buy_times >= 3 and sell_times >= 3 and buy_qty >= 5 * q and sell_qty >= 5 * q
        expected = {"symbol": symbol, "quantity": q, "qualified": passes,
                    "required_distinct_timestamps_each_side": 3, "required_volume_each_side": 5 * q,
                    "buy_limit_timestamps": buy_times, "sell_limit_timestamps": sell_times,
                    "buy_limit_print_volume": buy_qty, "sell_limit_print_volume": sell_qty,
                    "buy_limit_trades": below, "sell_limit_trades": above,
                    "eligible_prior_trade_count": len(flow),
                    "eligible_prior_notional_units": sum(r["size"] * r["price"] for r in flow),
                    "execution_verified": False, "returns_calculated": False}
        assert expected == reported["activity"]
        assert len(flow) == old["prior_trade_count"]
        assert Decimal(expected["eligible_prior_notional_units"]) / 10000 == Decimal(old["prior_trade_notional_usd"])
        if passes:
            qualified.append(old)
    qualified.sort(key=lambda r: (-Decimal(r["quoted_net_budget_bps"]),
                                  -Decimal(r["prior_trade_notional_usd"]), r["symbol"]))
    assert qualified == result["qualified"] and qualified[:1] == result["selected"]
    return {"date": day, "source_messages": count, "candidate_checks": len(candidates),
            "native_trade_break_rows": len(rows), "qualified": len(qualified),
            "session_sha256": expected_hash}


def main():
    result_path = OUT / "screen_results.json"
    result = json.loads(result_path.read_text())
    spec = json.loads((OUT / "specification.json").read_text())
    parent_audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert sha(PARENT / "independent_verification.json") == spec["parent_audit_sha256"]
    assert parent_audit["verified"] and result["unknown_admission_dates"] == [r["date"] for r in parent_audit["unknown_source_dates"]]
    assert not result["errors"] and result["intact_dates_screened"] == len(spec["intact_dates"])
    verified = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(one_day, d, h): d for d, h in result["session_hashes"].items()}
        for job in as_completed(jobs):
            row = job.result()
            verified.append(row)
            print(json.dumps(row), flush=True)
    assert sum(r["candidate_checks"] for r in verified) == result["candidate_checks"] == spec["candidate_count"]
    assert sum(r["qualified"] for r in verified) == result["qualified"]
    assert sum(r["source_messages"] for r in verified) == result["source_messages_checked"]
    selected = []
    for day in spec["intact_dates"]:
        session = json.loads((OUT / "sessions" / (day + ".json")).read_text())
        selected.extend({"date": day, **c} for c in session["selected"])
    assert selected == result["selected"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_messages_verified": sum(r["source_messages"] for r in verified),
             "native_trade_break_rows_verified": sum(r["native_trade_break_rows"] for r in verified),
             "candidate_checks_verified": sum(r["candidate_checks"] for r in verified),
             "qualified_verified": sum(r["qualified"] for r in verified),
             "selected_events_verified": len(selected), "unknown_admission_dates": result["unknown_admission_dates"],
             "results_sha256": sha(result_path), "auditor_sha256": sha(Path(__file__)),
             "native_decoder_sha256": sha(ROOT / "research_scout/audit_iex_deep_20261002.py"),
             "sessions": sorted(verified, key=lambda r: r["date"]),
             "economic_configurations_executed": 0, "returns_calculated": False,
             "actual_execution_verified": False, "reliable_edge_established": False}
    (OUT / "independent_verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "sessions"}), flush=True)


if __name__ == "__main__":
    main()
