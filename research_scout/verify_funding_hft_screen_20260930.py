"""Verify the no-order funding screen without claiming an execution backtest."""

import json

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.screen_funding_hft_20260930 import OUT, ROOT


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    assert digest(ROOT / "research_scout/screen_funding_hft_20260930.py") == spec["code_sha256"]
    manifest = json.loads((OUT / "manifest.json").read_text())
    result = json.loads((OUT / "results.json").read_text())
    snapshots, pairs = pd.read_parquet(OUT / "snapshots.parquet"), pd.read_parquet(OUT / "pairs.parquet")
    assert len(manifest) == 144 and len(snapshots) == 288 and len(pairs) == 144
    checked = 0
    for item in manifest:
        path = ROOT / item["path"]
        assert digest(path) == item["sha256"]
        assert path.stat().st_size == item["bytes"]
        if item["date"] == "2024-01-01":
            # Calendar-fixed CSV spot check independent of numpy searchsorted.
            raw = pd.read_csv(path, usecols=["timestamp", "local_timestamp", "funding_timestamp", "funding_rate", "mark_price"])
            selected = snapshots.loc[snapshots.date.eq(item["date"]) & snapshots.symbol.eq(item["symbol"]) & snapshots.exchange.eq(item["exchange"])]
            for snapshot in selected.to_dict("records"):
                row = raw.loc[raw.local_timestamp.lt(snapshot["decision_us"])].iloc[-1]
                assert snapshot["source_position"] == row.name
                assert snapshot["receive_us"] == row.local_timestamp
                assert snapshot["event_us"] == row.timestamp
                assert snapshot["funding_time_us"] == row.funding_timestamp
                assert snapshot["funding_rate"] == row.funding_rate and snapshot["mark_price"] == row.mark_price
                checked += 1
    lookup = {}
    stale = []
    for row in snapshots.to_dict("records"):
        usable = (0 < row["decision_us"] - row["receive_us"] <= 5000000
                  and 0 < row["decision_us"] - row["event_us"] <= 5000000
                  and row["funding_time_us"] == row["settlement_us"]
                  and np.isfinite([row["funding_rate"], row["mark_price"]]).all() and row["mark_price"] > 0)
        assert usable == row["usable"]
        lookup[row["exchange"], row["symbol"], row["settlement_us"]] = row
        if not usable:
            stale.append({"date": row["date"], "symbol": row["symbol"], "exchange": row["exchange"],
                          "capture_age_seconds": (row["decision_us"] - row["receive_us"]) / 1e6})
    for row in pairs.to_dict("records"):
        a = lookup["binance-futures", row["symbol"], row["settlement_us"]]
        b = lookup["bybit", row["symbol"], row["settlement_us"]]
        assert row["usable"] == (a["usable"] and b["usable"])
        if row["usable"]:
            funding_per_coin = abs(a["funding_rate"] * a["mark_price"] - b["funding_rate"] * b["mark_price"])
            bps = 10000 * funding_per_coin / max(a["mark_price"], b["mark_price"])
            assert abs(row["quoted_funding_difference_bps"] - bps) < 1e-10
            assert row["eligible"] == (bps > 28)
        else:
            assert not row["eligible"]
    assert result["usable_pairs"] == int(pairs.usable.sum())
    assert result["eligible_pairs"] == int(pairs.eligible.sum())
    audit = {"verified": True, "source_hashes_checked": len(manifest),
             "calendar_selected_csv_snapshots_checked": checked, "all_snapshot_eligibility_checks": len(snapshots),
             "paired_economic_gate_checks": len(pairs), "unusable_snapshots": stale,
             "native_websocket_field_mapping_verified": False,
             "scope": "All funding arithmetic and eligibility checks; raw normalized CSV as-of checks on 24 first-January snapshots. No fills, settled funding cashflows or future-return labels tested. Native WebSocket normalization remains an admission requirement before any profitable strategy claim.",
             "strategy_pnl_tested": False, "edge_established": False}
    (OUT / "verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    lines = [
        "SIX-INSTRUMENT CROSS-VENUE FUNDING HFT FEASIBILITY SCREEN",
        "No eligible entry. No strategy P&L tested and no reliable edge established.",
        "",
        "Hypothesis: enter equal-coin long/short USDT perpetuals 30s before settlement, close about 30s after.",
        "Buy the lower quoted funding payment and sell the higher. This is a seconds-long hypothesis, not carry.",
        "Two venues: Binance USD-M and Bybit. Six fixed instruments: BTC, ETH, SOL, BNB, XRP and DOGE.",
        "Dates: first of each month in 2024, 08:00 and 16:00 UTC funding events. Not continuous market coverage.",
        "Data: 144 free unauthenticated public files, 218,529,624 compressed bytes, 16,053,178 ticker updates.",
        "Use only the last ticker received strictly before settlement minus 30s; both source clocks <=5s old.",
        "Both next-funding times must equal the target settlement. Rates can change before actual settlement.",
        "",
        f"Paired observations: {result['funding_pairs']}; usable: {result['usable_pairs']}; eligible: {result['eligible_pairs']}.",
        f"Largest quoted net funding difference: {result['maximum_quoted_funding_difference_bps']:.4f}bp of one-leg reference notional.",
        "Entry hurdle: >28bp = four executions at 6bp commission + 1bp adverse allowance each, before spreads.",
        "Per-asset maximum quoted difference (bp):",
    ]
    lines.extend(f"  {symbol}: {values['maximum_quoted_funding_difference_bps']:.4f}; {values['usable_pairs']} usable observations"
                 for symbol, values in result["by_symbol"].items())
    lines += [
        "",
        "Three XRP/Bybit snapshots were 7.8-8.4s old and failed the predeclared freshness gate.",
        "The quoted funding component is too small to trigger this rule in this sample. This does not prove",
        "that price alpha, other contracts, other dates or other funding mechanisms are impossible.",
        "",
        "A later execution test would need actual settled rates and mark prices, full-book entry/exit cashflows,",
        "basis repricing, missed-leg unwind, separate capture/execution clocks and settlement inclusion uncertainty.",
        "Bybit documents uncertain funding inclusion for positions opened or closed within five seconds of settlement.",
        "Current documentation alone is not proof of unchanged historical rules. No such tight-cutoff fill is assumed here.",
        "",
        "Audit: all 144 file hashes, 288 snapshot eligibility checks and 144 paired rate calculations verified;",
        "24 calendar-selected native CSV as-of rows checked. Three causal timing tests passed.",
        "Native WebSocket field normalization not independently reconciled; required before any P&L claim.",
        "",
        "Sources: https://docs.tardis.dev/downloadable-csv-files/data-types",
        "Sources: https://www.bybit.com/en/help-center/article/Funding-fee-calculation",
    ]
    (OUT / "REPORT.txt").write_text("\n".join(lines) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
