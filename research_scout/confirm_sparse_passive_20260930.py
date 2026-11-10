"""Fixed-parameter later-period stress of the only positive passive baseline."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import research_scout.run_crypto_passive_partial_20260930 as runner

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/crypto_passive_confirmation_20260930"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "specification.json").exists():
        raise FileExistsError("Confirmation already started")
    original = json.loads((runner.OUTPUT / "specification.json").read_text())
    scenarios = {name: rule for name, rule in original["scenarios"].items() if name.startswith("follow_16bps_")}
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "source_specification": str(runner.OUTPUT / "specification.json"),
            "candidate": "follow_16bps", "scenarios": scenarios, "selection": runner.SELECTION,
            "purpose": "Distinguish a negative economic result from insufficient observations. This rule failed its development evidence gate but was positive under every frozen stress. Test the same parameters on later dates without claiming promotion or changing the historical gate.",
            "history": "Nine development trades, two positive dates, all four scenario totals positive; inadequate evidence and low absolute profit. This choice is outcome-conditioned among six rules; it does not reset multiplicity or prior historical exposure.",
            "gate": "Every scenario must be complete and have positive total P&L to merit considering further data. Even then this is not an edge pass: original count, uncertainty and reliability requirements remain unmet unless separately demonstrated.",
            "later_march_data": "Not opened by this confirmation. A failure ends this confirmation without tuning.",
            "code_sha256": original["code_sha256"]}
    (OUTPUT / "specification.json").write_text(json.dumps(spec, indent=2) + "\n")
    runner.OUTPUT = OUTPUT
    summary = runner.run_section(runner.SELECTION, scenarios, "selection")
    passes = all(item["complete"] and item["net_dollars"] > 0 for item in summary.values())
    result = {"stage_passed": passes, "edge_established": False,
              "verdict": "INSUFFICIENT_EVIDENCE_REQUIRES_MORE_DATES" if passes else "FAILED_LATER_PERIOD_STRESS",
              "results": summary}
    (OUTPUT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    for name, value in summary.items():
        print(f"{name}: net={value['net_dollars']}, trades={value['trades']}, complete={value['complete']}", flush=True)
    print(result["verdict"], flush=True)


if __name__ == "__main__":
    main()
