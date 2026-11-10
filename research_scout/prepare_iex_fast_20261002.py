"""Freeze native stock displacement admission before observing subsequent returns."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research_scout/iex_deep_hft_20261002"
OUT = ROOT / "research_scout/iex_fast_hft_20261002"
CODE = ("research/iex_fast_displacement.py", "research/iex_deep_supply.py",
        "research/iex_native_prefix.py", "research_scout/screen_iex_fast_20261002.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def main():
    old = json.loads((PARENT / "screen_results.json").read_text())
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(PARENT / "screen_results.json")
    probe = PARENT / "price_probe_v1"
    results = json.loads((probe / "results.json").read_text())
    audit = json.loads((probe / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(probe / "results.json")
    sources = {}
    for day, expected in old["session_hashes"].items():
        parent_path = PARENT / "sessions" / (day + ".json")
        assert sha(parent_path) == expected
        parent = json.loads(parent_path.read_text())
        source_path = parent_path
        if day in results["session_hashes"]:
            source_path = probe / "sessions" / (day + ".json")
            assert sha(source_path) == results["session_hashes"][day]
        source = json.loads(source_path.read_text())
        assert sha(Path(source["prefix_path"])) == source["prefix_sha256"]
        sources[day] = {"prefix_path": source["prefix_path"], "prefix_sha256": source["prefix_sha256"],
                        "source": source["source"], "source_record": str(source_path),
                        "source_record_sha256": sha(source_path),
                        "first_decision_ns": parent["decision_ns"] - 30_000_000_000,
                        "final_decision_ns": parent["decision_ns"]}
    OUT.mkdir(exist_ok=True)
    path = OUT / "specification.json"
    assert not path.exists()
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis": "Recent, liquid stock price displacements confirmed by trades and both displayed quote sides may predict a seconds-long continuation or reversal large enough to cover conservative costs.",
        "dates": json.loads((PARENT / "specification.json").read_text())["dates"],
        "sources": sources, "unknown_admission_dates": ["2023-11-29"],
        "grid": "09:30:30 through09:31:00 ET inclusive every100ms; information cutoff decision-1ms. Source packets captured strictly before cutoff; all observed native event/send clocks<=cutoff. Each reference snapshot is at cutoff-1s using the identical causal rule. Native stream contiguous from sequence1/offset0; atomic DEEP final PLU only; any pending atomic state rejects that symbol.",
        "scope": "All uppercase ASCII alphabetic1-5char native symbols, explicit test flag excluded. Both snapshots H=T/O=N, positive uncrossed $5-$1000 cent quotes and positive touch sizes. Confirm stock/ETF identity before any economic replay.",
        "freshness": "Current and reference completed quotes: both capture and native event ages<=250ms. Current eligible trade<=100ms; reference eligible trade<=250ms. Latest eligible trade as observed at each snapshot; both must lie inside their contemporaneous BBO. A later causally known break invalidates the saved reference. Eligible T:positive price/quantity,flags&0x58==0; known B removed. No unbroken duplicate trade IDs in the active1s window.",
        "signal": "Absolute latest trade price change>=30bp versus reference. Both bid and ask strictly move in the same direction. Prior1s native eligible trade window inclusive requires>=5 distinct native event times and >=$25000 notional. Current spread<=5bp, reference spread<=50bp.",
        "sizing": "Buy limit is102% of current ask rounded up to whole cent. Fixed quantity=min(floor$10000/limit,floor10% current bid size,floor10% current ask size). Do not resize using future depth or prices.",
        "cost_hurdle": "Aggressive current ask-to-bid roundtrip:spread+two max($1,$.005/share) commissions+1bp adverse allowance on each notional+sale levy .00003 sale notional+.000166/share. No rebates. Cost<=12bp of entry notional and observed move>=3times this cost. Exact Decimal accounting.",
        "selection": "Two separate long-only policies:follow_rise and fade_fall. Each has one slot,global6s cooldown,symbol30s cooldown,max6signals/date. Each grid ranks eligible candidates by descending(movebp-3costbp),descending prior1s notional,ascending symbol. Selection solely causal; a selected event starts its cooldown regardless of later fill.",
        "planned_execution": "If supply exists, freeze a separate depth-aware aggressive IOC entry and forced exit5s later, all inventory<30s; baseline1ms and5/25/250ms assumed one-way arrival delays including350us exchange speed bump, plus doubled-cost stresses. Venue/simulator access and actual fast latency are unverified; any result is conditional. Economic replay must separately account for depth, ambiguous clocks and unknown residual inventory.",
        "limits": "2023 dates repeatedly used for discovery; no untouched validation claim. IEX-only book lacks NBBO, private acceptance and hidden liquidity. Missing Nov29 initial history remains unknown. No future returns inspected by this screen; no economic implementation yet.",
        "acquisition": "Reuse immutable, generation-pinned local IEX prefixes only; no new download or paid API.",
        "code_sha256": {name: sha(ROOT / name) for name in CODE},
        "parent_screen_sha256": sha(PARENT / "screen_results.json"),
        "parent_audit_sha256": sha(PARENT / "independent_verification.json"),
        "extended_source_audit_sha256": sha(probe / "independent_verification.json"),
        "economic_configurations_executed": 0, "returns_calculated": False,
        "actual_execution_verified": False, "reliable_edge_established": False,
        "attribution": "Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data Terms of Use.",
        "terms": "https://www.iex.io/legal/hist-data-terms",
    }
    write(path, spec)
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert state["focused_tests_total"] == 411
    state.update(updated_at_utc=datetime.now(UTC).isoformat(), focused_tests_total=421,
                 active_research_jobs=["Native DEEP fast displacement admission"],
                 iex_fast_specification=str(path), iex_fast_economic_configurations_executed=0,
                 remaining_evidence_work="Frozen fast stock displacement supply screen;10 focused tests passed. No future return evaluated; all existing edge conclusions remain negative or unresolved.")
    write(checkpoint, state)
    print(json.dumps({"path": str(path), "sha256": sha(path), "intact_dates": len(sources)}))


if __name__ == "__main__":
    main()
