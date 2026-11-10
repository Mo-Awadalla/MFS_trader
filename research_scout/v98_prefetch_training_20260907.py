"""Overlap source-only training admission and historical GETs with text collection.

This scheduling helper leaves the frozen models and eligibility rules unchanged.
It reuses completed source years only. The final plan adopts exact matching
requests; any surplus prefetch stays separate and is never silently substituted.
"""

import argparse
import json

from research_scout import v98_earnings_answers_20260907 as source
from research_scout import v98_market_data_20260907 as market


def prefetch():
    base = source.OUT
    manifest = source.read("source_manifest.json")
    spec = source.read("specification.json")
    cached = {}
    for path in (base / "raw/transcripts").glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        cached[row["url"]] = row
    years = []
    selected = []
    for year in ["2018", "2019", "2020"]:
        subset = [r for r in manifest if f"/{year}/" in r["url"]]
        if subset and all(r["url"] in cached for r in subset):
            years.append(year)
            selected.extend(subset)
    if not selected:
        raise ValueError("No complete source year to prefetch")
    subdirectory = base / "training_prefetch"
    if (subdirectory / "specification.json").exists():
        raise ValueError("Existing prefetch kept; resume its collection explicitly if needed")
    source.OUT = subdirectory
    market.OUT = subdirectory
    source.save("specification.json", spec)
    source.save("source_manifest.json", selected)
    source.save("transcript_retrieval.json", [cached[r["url"]] for r in selected])
    source.save(
        "prefetch_scope.json",
        {
            "years": years,
            "rule_changes": False,
            "purpose": "Schedule independent public-text and market-data collection concurrently. No performance analysis.",
        },
    )
    print(f"Prefetch completed source years {years}; {len(selected)} candidates", flush=True)
    source.parse_sources()
    market.plan()
    market.collect(1)
    if not source.read("market_probe.json")[0]["complete"]:
        raise ValueError("Historical access probe failed")
    market.collect()


def adopt():
    base = source.OUT
    planned = {r["day"]: r for r in source.read("market_request_plan.json")}
    path = base / "training_prefetch/market_retrieval.json"
    if not path.exists():
        raise ValueError("Prefetch has not completed")
    records = json.loads(path.read_text(encoding="utf-8"))
    adopted, unused = [], []
    for row in records:
        match = planned.get(row["day"])
        if row["complete"] and match and match["params"] == row["params"]:
            dest = base / "market_raw" / row["day"] / "retrieval.json"
            if dest.exists():
                raise ValueError("Refuse to overwrite existing retrieval provenance")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(row, indent=2), encoding="utf-8")
            adopted.append(row["day"])
        else:
            unused.append(row["day"])
    source.save(
        "prefetch_adoption.json",
        {
            "exact_request_matches": adopted,
            "not_adopted": unused,
            "raw_files_retained_in_original_prefetch_directory": True,
        },
    )
    print(
        f"Adopted {len(adopted)} exact matching historical request batches; {len(unused)} retained separately",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prefetch", "adopt"])
    args = parser.parse_args()
    {"prefetch": prefetch, "adopt": adopt}[args.stage]()
