"""Fetch free Databento dataset-condition metadata for an audit artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402


def _api_key(dotenv_path: Path) -> str:
    key = os.environ.get("DATABENTO_API_KEY")
    if key:
        return key
    for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", 1)
            if name.strip() == "DATABENTO_API_KEY":
                return value.strip().strip("\"'")
    raise RuntimeError("DATABENTO_API_KEY is not set")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="GLBX.MDP3")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    client = db.Historical(_api_key(args.dotenv))
    conditions = client.metadata.get_dataset_condition(
        dataset=args.dataset,
        start_date=args.start,
        end_date=args.end,
    )
    payload = {
        "purpose": "Free Databento dataset-condition metadata",
        "dataset": args.dataset,
        "start": args.start,
        "end": args.end,
        "conditions": conditions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
