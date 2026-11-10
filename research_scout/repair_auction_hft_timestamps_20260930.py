"""Re-serialize the unchanged frozen replay with exact nullable integer clocks."""

import json
from pathlib import Path

import pandas as pd

from research.auction_hft_event import replay_day
from research.crypto_symbol_cache import digest
from research.precise_ledger import ledger_frame
from research_scout.run_auction_hft_20260930 import OUT, ROOT


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    for name, sha in spec["code_sha256"].items():
        assert digest(ROOT / name) == sha
    destination = OUT / "precise_ledgers"
    destination.mkdir(exist_ok=True)
    if (destination / "repair.json").exists():
        raise FileExistsError("Precise ledger repair already complete")
    inputs = pd.read_parquet(OUT / "auction_inputs.parquet")
    state = {(row["date"], row["label"]): row for row in inputs.to_dict("records")}
    records = {f"{rule}_{hold}s_{scenario}": [] for rule in spec["rules"] for hold in spec["holds_seconds"] for scenario in spec["scenarios"]}
    for day in spec["dates"]:
        quotes = pd.read_parquet(OUT / "panels" / f"{day}.parquet")
        for rule in spec["rules"]:
            for hold in spec["holds_seconds"]:
                for scenario, params in spec["scenarios"].items():
                    records[f"{rule}_{hold}s_{scenario}"].append(replay_day(day, quotes, state[day, "early"], state[day, "late"], rule, hold, params))
    manifests, max_clock_difference = [], 0
    for name, rows in records.items():
        frame = ledger_frame(rows)
        filename = f"{name}_attempts.parquet"
        old = pd.read_parquet(OUT / filename)
        other = [column for column in frame if not column.endswith("_ns")]
        pd.testing.assert_frame_equal(frame[other], old[other])
        for column in frame:
            if column.endswith("_ns"):
                for original, precise in zip(old[column].tolist(), frame[column].tolist(), strict=True):
                    if pd.isna(precise):
                        assert pd.isna(original)
                    else:
                        max_clock_difference = max(max_clock_difference, abs(int(original) - int(precise)))
        path = destination / filename
        frame.to_parquet(path, index=False)
        pd.testing.assert_frame_equal(pd.read_parquet(path), frame)
        manifests.append({"path": str(path.relative_to(ROOT)), "sha256": digest(path), "rows": len(frame)})
    helper = ROOT / "research/precise_ledger.py"
    result = {"verified": True, "reason": "The original heterogeneous DataFrame introduced NaN into optional nanosecond-clock columns, causing float64 rounding. Replaying the frozen inputs and writing nullable Int64 restores exact clocks.",
              "maximum_original_clock_rounding_ns": max_clock_difference,
              "every_nonclock_column_identical": True,
              "signals_fills_costs_pnl_unchanged": True,
              "original_ledgers_preserved": True, "files": manifests,
              "helper_sha256": digest(helper), "repair_code_sha256": digest(Path(__file__)),
              "original_spec_sha256": digest(OUT / "specification.json")}
    (destination / "repair.json").write_text(json.dumps(result, indent=2) + "\n")
    (OUT / "LEDGER_TIMESTAMP_ERRATUM.txt").write_text(
        f"Optional clock columns in the original ledgers were rounded by up to {max_clock_difference} nanoseconds when pandas inferred float64 for integer/empty rows.\n"
        "precise_ledgers/ restores exact nullable integer timestamps by rerunning the unchanged frozen replay against the same cached inputs. Every non-clock field is identical, including signals, quantities, statuses, fees and P&L. Original files remain preserved.\n"
        "This serialization repair creates no independent profitability evidence. Eight repeated implementations are conservatively retained in the experiment history.\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, indent=2))


if __name__ == "__main__":
    main()
