"""Freeze then replay one passive spread hypothesis on the free Nasdaq sample."""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from research.nasdaq_passive_probe import CASES, schedule, simulate
from research_scout.audit_databento_public_book_20261003 import rows
from research_scout.inspect_databento_public_sample_20261003 import OUT as PARENT
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write

OUT = PARENT / "passive_probe_v1"
SUPPLY = PARENT / "spread_supply"


def prepare():
    assert not (OUT / "specification.json").exists()
    inventory = json.loads((PARENT / "inventory.json").read_text())
    book_audit = json.loads((PARENT / "book_verification_v3.json").read_text())
    supply_audit = json.loads((SUPPLY / "independent_verification.json").read_text())
    supply = json.loads((SUPPLY / "results.json").read_text())
    assert book_audit["verified"] and supply_audit["verified"] and len(supply["eligible"]) == 1
    assert book_audit["source_inventory_sha256"] == sha(PARENT / "inventory.json")
    source = next(s for s in inventory["sources"] if s["schema"] == "mbo")
    pins = (PARENT / "inventory.json", PARENT / "book_verification_v3.json",
            SUPPLY / "specification.json", SUPPLY / "results.json", SUPPLY / "independent_verification.json",
            ROOT / "research/nasdaq_mbo_book.py", ROOT / "research/nasdaq_passive_probe.py",
            ROOT / "research_scout/audit_databento_public_book_20261003.py",
            ROOT / "research_scout/prepare_databento_fast_20261002.py",
            ROOT / "tests/unit/test_nasdaq_passive_probe.py", Path(__file__))
    specification = {
        "created_at_utc": datetime.now(UTC).isoformat(), "hypothesis_count": 1,
        "kind": "Conditional displayed-queue passive buy then passive sell with mandatory IOC exit; strict HFT.",
        "source": source, "events": supply["eligible"], "cases": [asdict(c) for c in CASES],
        "pinned_sha256": {str(p.relative_to(ROOT)): sha(p) for p in pins},
        "entry": "At decision+50us+one-way latency, post the fixed signal bid and quantity. All existing displayed IDs at that price are ahead. No quote-touch fill or later quantity enlargement.",
        "exit": "Send entry cancel at decision+1s+50us; exchange arrival adds outbound latency. Wait for cancellation acknowledgement and earlier reliable ordered fill reports, each with the same one-way latency; process50us and send a fixed signal-ask limit for the final entry-filled quantity. Never overlap active entry and exit orders.",
        "flatten": "Send ask cancel at decision+5s+50us; exchange arrival adds latency. After its acknowledgement plus50us and outbound latency, sell remaining inventory by IOC against displayed bids down to floor(0.98*initial_bid_cents) cents. Insufficient depth preserves unknown residual inventory and unknown PnL. All complete holdings must be<30s.",
        "exact_schedule": "With d=decision,p=50000ns,L=one-way latency,delta=native-minus-client clock shift: post_bid=d+p+L+delta;cancel_bid=d+1s+p+L+delta;post_ask=d+1s+2p+3L+delta;cancel_ask=d+5s+p+L+delta;force=d+5s+2p+3L+delta.",
        "queue": "Only a resting-side F at our price or worse can support a conditional fill after every initial same-price ID is gone and no better displayed price remains. T/non-displayed prints and C alone never fill us. F of an ahead ID leaves queue unchanged until its C; C reduces once. M price change or size increase loses priority. Off-display execution reaching our level, unresolved priority, active reset, invalid book, relevant equal-native-clock action, truncated lifecycle or marketable passive posting is unknown.",
        "cash": "Exact Decimal cash. For each submitted order that actually fills, commission=max(1USD,0.005USD/share), aggregated across its partial fills. Bid, passive ask and forced IOC are separate orders and may incur three minimums. Adverse cost1bp each filled notional; sales cost0.00003notional+0.000166/share. fees2x doubles commissions; adverse2x doubles adverse costs. No rebates. Unknown inventory is never valued as zero.",
        "counterfactual": "Virtual orders do not mutate the historical book. Matching assumes the same subsequent incoming flow despite our additional displayed order and displacement of historical fills. This is a conditional scenario, not an actual-execution guarantee or a rigorous PnL bound. Posting at the intended price, own order acceptance, routing/NBBO compliance, hidden liquidity interactions and client/private-notification latency are not verified by this public source.",
        "stress": "Eight predeclared scenarios reuse this ONE event:1/5/25/250ms latency,2x commissions,2x adverse costs,clock-1ms,+1ms. They are not eight independent observations.",
        "selection": "One vendor-selected NVDA date and one event; cannot establish reliability even if every conditional case profits. Do not retune this event from forward outcomes. Additional independent dates and actual-execution evidence are required before promotion.",
        "validation": "14 focused queue, cost, clock, cancellation and unknown-state tests and Ruff passed before freeze. Independent original-CSV execution/cash audit required after replay.",
        "network_calls": 0, "paid_calls": 0, "actual_execution_verified": False}
    OUT.mkdir(exist_ok=True)
    write(OUT / "specification.json", specification)
    print(json.dumps({"specification_sha256": sha(OUT / "specification.json"), "events": len(supply["eligible"])}))


def run():
    assert not (OUT / "results.json").exists() and not (OUT / "started.json").exists()
    spec = json.loads((OUT / "specification.json").read_text())
    for path, expected in spec["pinned_sha256"].items():
        assert sha(ROOT / path) == expected, path
    source = spec["source"]
    assert sha(Path(source["typed_path"])) == source["typed_sha256"]
    assert spec["cases"] == [asdict(c) for c in CASES]
    event = spec["events"][0]
    end = max(schedule(event["decision_ns"], c)[-1][0] for c in CASES)
    prefix, previous = [], None
    for record in rows(source["typed_path"]):
        assert record["source_row"] == len(prefix)
        assert (record["publisher_id"], record["instrument_id"], record["symbol"]) == (2, 11667, "NVDA")
        if previous is None:
            assert record["action"] == "R" and record["flags"] == 8
        else:
            assert not record["flags"] & 12
            assert all(record[k] >= previous[k] for k in ("ts_event", "ts_recv", "sequence"))
            assert record["ts_recv"] - record["ts_event"] == record["ts_in_delta"]
        prefix.append(record)
        previous = record
        if record["ts_event"] > end:
            break
    assert prefix[-1]["ts_event"] > end
    write(OUT / "started.json", {"started_at_utc": datetime.now(UTC).isoformat(),
                                "specification_sha256": sha(OUT / "specification.json"),
                                "economic_configurations_started": 1, "implementation_versions_started": 1})
    results = [simulate(prefix, event, c) for c in CASES]
    result = {"completed_at_utc": datetime.now(UTC).isoformat(), "specification_sha256": sha(OUT / "specification.json"),
              "source_prefix_rows": len(prefix), "source_last_row": prefix[-1]["source_row"],
              "source_last_event_ns": prefix[-1]["ts_event"], "event": event, "cases": results,
              "economic_configurations_executed": 1, "implementation_versions_executed": 1,
              "independent_execution_cash_audit_verified": False,
              "actual_execution_verified": False, "reliable_edge_established": False, "network_calls": 0, "paid_calls": 0}
    write(OUT / "results.json", result)
    print(json.dumps({"source_prefix_rows": len(prefix), "cases": [
        {k: r[k] for k in ("case", "status", "unknown_reason", "bought", "sold", "cash")} for r in results]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run"))
    argument = parser.parse_args()
    prepare() if argument.action == "prepare" else run()
