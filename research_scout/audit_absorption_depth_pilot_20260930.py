"""Source-field pilot, preserving the original publication-clock backtest."""

import json

import pandas as pd

from research.crypto_symbol_cache import digest
from research.standing_depth_audit import parse_depth, unchanged_topfive
from research_scout.probe_absorption_depth_20260930 import OUT, ROOT, STUDY


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    manifest = json.loads((OUT / "pilot_manifest.json").read_text())
    assert manifest["complete"] and len(manifest["files"]) == 2
    findings = []
    for item in manifest["files"]:
        source = ROOT / item["path"]
        assert digest(source) == item["sha256"]
        target = next(t for t in spec["targets"] if t["symbol"] == item["symbol"])
        panel = pd.read_parquet(STUDY / item["symbol"] / "panels" / f"{item['date']}_quotes.parquet")
        quote = panel.loc[panel.target_us.eq(target["target_us"]) & panel.clock_kind.eq("exchange")].iloc[0].to_dict()
        rows = parse_depth(source.read_bytes(), item["date"], item["symbol"])
        tick = .1 if item["symbol"] == "BTCUSDT" else .001
        result = unchanged_topfive(rows, quote, tick)
        result.update(symbol=item["symbol"], date=item["date"], target_us=target["target_us"],
                      source_age_us=quote["exchange_age_us"], source_sha256=item["sha256"], native_messages=len(rows))
        findings.append(result)
    report = {"findings": findings, "original_results_modified": False,
              "scope": "Only first chronological aged target per instrument. Does not validate other targets or constitute a corrected P&L replay. Native Binance E is event publication time; T is transaction time. The pilot distinguishes the two rather than calling the normalized timestamp a matching-engine clock.",
              "consequence": "The original simulation is a publication-clock proxy with an over-restrictive 250ms expiry, not proven transaction-time execution. No candidate passed. Any next execution implementation must correctly apply sequenced native T updates, including changes whose E follows order time, and preserve deeper-liquidity unknowns and timestamp-tie uncertainty."}
    (OUT / "pilot_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
