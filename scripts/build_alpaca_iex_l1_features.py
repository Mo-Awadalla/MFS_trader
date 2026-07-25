"""Build the frozen five-minute feature-plumbing artifact from an IEX L1 manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.alpaca_iex_l1_features import FREQUENCY, build_iex_5min_features
from storage.microstructure_io import read_events, sha256_file, write_events

SCHEMA_VERSION = "alpaca_iex_l1_features:v1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def _max_or_zero(series: pd.Series) -> float:
    values = series.dropna()
    return float(values.max()) if not values.empty else 0.0


def main() -> int:
    args = _parse_args()
    manifest_path = args.manifest.resolve()
    source = json.loads(manifest_path.read_text(encoding="utf-8"))
    if source.get("provider") != "alpaca" or source.get("feed") != "iex":
        print("BLOCKED: source manifest must be Alpaca IEX")
        return 2
    for event_type in ("trades", "quotes"):
        download = source["downloads"][event_type]
        quality = source["quality"][event_type]
        if not download.get("pagination_complete") or quality.get("result") == "FAIL":
            print(f"BLOCKED: source {event_type} data did not pass feasibility gates")
            return 2

    output_path = manifest_path.parent / f"features_{FREQUENCY}.parquet"
    feature_manifest_path = manifest_path.parent / f"features_{FREQUENCY}_manifest.json"
    if feature_manifest_path.exists() and not args.refresh:
        print(f"BLOCKED: feature artifact already exists; use --refresh to replace {feature_manifest_path}")
        return 2

    trades = read_events(manifest_path.parent / source["files"]["trades"]["path"])
    quotes = read_events(manifest_path.parent / source["files"]["quotes"]["path"])
    features = build_iex_5min_features(trades, quotes)
    serializable = features.reset_index()
    file_metadata = write_events(serializable, output_path)
    file_metadata["path"] = output_path.name

    target_rows = int(features["next_midpoint_return"].notna().sum()) if not features.empty else 0
    minimum_match = (
        float(features.loc[features["trade_count"] > 0, "quote_match_fraction"].min())
        if not features.empty and (features["trade_count"] > 0).any()
        else 0.0
    )
    invalid_spreads = (
        int((features["terminal_spread_bps"].dropna() < 0).sum()) if not features.empty else 0
    )
    negative_quote_ages = (
        int(
            (features["maximum_trade_quote_age_ms"].dropna() < 0).sum()
            + (features["terminal_quote_age_ms"].dropna() < 0).sum()
        )
        if not features.empty
        else 0
    )
    maximum_trade_quote_age_ms = _max_or_zero(features["maximum_trade_quote_age_ms"])
    maximum_terminal_quote_age_ms = _max_or_zero(features["terminal_quote_age_ms"])
    quote_state_counts = {
        state: int(features[f"{state}_quote_count"].sum())
        for state in ("normal", "locked", "crossed", "one_sided", "invalid")
    }
    quality_pass = (
        len(features) >= 2
        and target_rows >= 1
        and minimum_match >= 0.95
        and invalid_spreads == 0
        and negative_quote_ages == 0
    )
    feature_manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "purpose": "feature plumbing only; not alpha evidence or a Strategy Experiment",
        "source_manifest": manifest_path.name,
        "source_manifest_sha256": sha256_file(manifest_path),
        "provider": "alpaca",
        "feed": "iex",
        "frequency": FREQUENCY,
        "signal_timestamp_semantics": (
            "right edge of a left-closed interval; all feature events occur before that edge"
        ),
        "trade_classification": (
            "eligible regular-sale trade price versus latest regular-open normal IEX quote "
            "strictly before the trade timestamp; equal-timestamp ordering and quotes older "
            "than two seconds are excluded; no tick-rule fallback is used"
        ),
        "forward_target": "next contiguous interval terminal-midpoint return; diagnostic only",
        "feature_rows": len(features),
        "target_rows": target_rows,
        "minimum_quote_match_fraction": minimum_match,
        "invalid_terminal_spreads": invalid_spreads,
        "negative_quote_ages": negative_quote_ages,
        "maximum_trade_quote_age_ms": maximum_trade_quote_age_ms,
        "maximum_terminal_quote_age_ms": maximum_terminal_quote_age_ms,
        "quote_state_counts": quote_state_counts,
        "quality_result": "PASS" if quality_pass else "FAIL",
        "file": file_metadata,
        "restrictions": [
            "IEX venue-local result only; not consolidated US flow.",
            "Do not tune frequency or classification rules on this consumed sample.",
            "Provider condition codes are preserved and the frozen tape-specific eligibility policy is applied.",
            "No portfolio return, cost, or SPY claim is produced by this artifact.",
        ],
    }
    temporary = feature_manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(feature_manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(feature_manifest_path)

    print(
        f"features rows={len(features)} targets={target_rows} "
        f"min_quote_match={minimum_match:.4f} quality={feature_manifest['quality_result']}"
    )
    print(f"manifest={feature_manifest_path}")
    if not quality_pass:
        print("FEATURE FEASIBILITY BLOCKED")
        return 1
    print("FEATURE FEASIBILITY PASS: leakage-controlled five-minute rows built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
