"""Freeze a past-only two-sided flow admission on every native DEEP budget candidate."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research_scout/iex_deep_hft_20261002"
OUT = ROOT / "research_scout/iex_flow_hft_20261002"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result = json.loads((PARENT / "screen_results.json").read_text())
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == digest(PARENT / "screen_results.json")
    OUT.mkdir(exist_ok=True)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis": "A cost-positive displayed spread needs recent trading at both fixed proposed limits before a short-hold capture policy is economically worth replaying.",
        "parent_screen_sha256": digest(PARENT / "screen_results.json"),
        "parent_audit_sha256": digest(PARENT / "independent_verification.json"),
        "dates": json.loads((PARENT / "specification.json").read_text())["dates"],
        "intact_dates": sorted(result["session_hashes"]),
        "unknown_admission_dates": [r["date"] for r in result["errors"]],
        "candidate_count": result["candidates"],
        "candidate_scope": "Every one of the52 parent DEEP cost/activity candidates, including originally unselected names. No filtering by later return, entry or outcome.",
        "causality": "Keep original09:31decision, capture cutoffd-250ms, native event/send<=cutoff, original fixed bid/ask and quantity. Only native T events in[cutoff-30s,cutoff], captured strictly before cutoff. Positive price/size, flags&0x58==0. Remove trades broken by a B received before cutoff. Repeated unbroken trade IDs fail.",
        "predicate": "At least3 distinct native event timestamps at/below proposed buy bid and at least3 at/above proposed sell ask. Each side's cumulative printed quantity must be at least5 times the fixed causal order quantity. Equality at price and quantity thresholds qualifies. No future prices inspected by this admission.",
        "ranking": "Among qualified candidates retain unchanged descending displayed net budgetbp, descending prior eligible notional, ascending symbol; at mostone daily candidate. Missing source day remains unknown.",
        "interpretation": "Printed activity is evidence of past price/volume opportunity, not queue priority, aggressor direction or achievable fills. All thresholds are exploratory after prior research. No economic variant is executed by this screen.",
        "acquisition": "Reuse immutable local native DEEP prefixes; no new network or paid data.",
        "implementation_sha256": digest(ROOT / "research/iex_two_sided_activity.py"),
        "deep_decoder_sha256": digest(ROOT / "research/iex_deep_supply.py"),
        "packet_decoder_sha256": digest(ROOT / "research/iex_native_prefix.py"),
        "economic_configurations_executed": 0, "returns_calculated": False,
        "actual_execution_verified": False, "reliable_edge_established": False,
    }
    path = OUT / "specification.json"
    assert not path.exists()
    path.write_text(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"path": str(path), "sha256": digest(path), "candidates": result["candidates"]}))


if __name__ == "__main__":
    main()
