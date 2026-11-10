"""Apply the frozen three-instrument causal flow confirmation."""

import gzip
import json
from collections import Counter
from datetime import UTC, datetime

from research.market_lag_flow import joint_confirmation
from research.perp_shock_flow import confirm, parse
from research.precise_ledger import ledger_frame
from research_scout.prepare_market_lag_flow_20261002 import OUT, ROOT, sha


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    assert sources["complete"] and sources["specification_sha256"] == sha(OUT / "specification.json")
    parent_audits = {}
    for parent in spec["quote_parents"]:
        folder = ROOT / parent["path"]
        audit = json.loads((folder / "independent_verification.json").read_text())
        assert audit["verified"] and audit["results_sha256"] == parent["results_sha256"] == sha(folder / "screen_results.json")
        assert sha(folder / "selected.parquet") == parent["selection_sha256"]
        parent_audits[str((folder / "independent_verification.json").relative_to(ROOT))] = sha(folder / "independent_verification.json")
    code = ["research/perp_shock_flow.py", "research/market_lag_flow.py", "research/precise_ledger.py",
            "research/spot_perp_supply.py", "tests/unit/test_market_lag_flow.py", "research_scout/screen_market_lag_flow_20261002.py"]
    dump(OUT / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "source_manifest_sha256": sha(OUT / "source_manifest.json"),
         "parent_audits_sha256": parent_audits, "code_sha256": {p: sha(ROOT / p) for p in code},
         "new_focused_tests_passed": 4, "economic_implementations": 0})
    (OUT / "ledgers").mkdir(exist_ok=True)
    windows, joint_rows, counts = [], [], Counter()
    for source in sources["files"]:
        assert source["complete"] and sha(ROOT / source["path"]) == source["compressed_sha256"]
        with gzip.open(ROOT / source["path"], "rt", encoding="utf-8") as stream:
            trades, disconnects, source_counts = parse(stream, source["date"], source["offset"], source["symbols"])
        counts.update(source_counts)
        bundles = []
        for event in spec["events"]:
            if event["date"] != source["date"] or event["offset_minutes"] != source["offset"]:
                continue
            parts, component_records = [], []
            for symbol in ("BTCUSDT", "ETHUSDT", event["symbol"]):
                component_event = {**event, "symbol": symbol}
                stats, ledger = confirm(trades, disconnects, component_event)
                parts.append(stats)
                path = OUT / "ledgers" / f"{event['date']}_{symbol}_{event['decision_ns']}.parquet"
                ledger_frame(ledger).to_parquet(path, index=False)
                component_records.append({"event": component_event, "result": stats, "ledger_path": str(path.relative_to(ROOT)),
                                          "ledger_sha256": sha(path)})
                print(json.dumps({k: stats[k] for k in ("symbol", "native_market_trade_count", "total_notional_usdt", "aligned_fraction", "source_integrity_ok")}), flush=True)
            joint = {**event, **joint_confirmation(event, parts)}
            joint_rows.append(joint)
            bundles.append({"event": event, "components": component_records, "joint": joint})
            print(json.dumps(joint), flush=True)
        windows.append({"date": source["date"], "offset": source["offset"], "source_counts": source_counts, "bundles": bundles})
    selected = [r for r in joint_rows if r["selected"]]
    ledger_frame(joint_rows).to_parquet(OUT / "joint.parquet", index=False)
    ledger_frame(selected).to_parquet(OUT / "selected.parquet", index=False)
    results = {"candidate_events": len(joint_rows), "component_checks": len(joint_rows) * 3,
               "selected_events": len(selected), "source_counts": dict(counts), "windows": windows,
               "implementation_sha256": sha(OUT / "implementation.json"), "joint_sha256": sha(OUT / "joint.parquet"),
               "selected_sha256": sha(OUT / "selected.parquet"), "economic_implementations": 0,
               "future_returns_evaluated": False, "selection_2025_opened": False, "reliable_edge_established": False}
    dump(OUT / "screen_results.json", results)


if __name__ == "__main__":
    main()
