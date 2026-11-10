"""Versioned Nasdaq-code compatibility screen; preserve all original inputs."""

import json
from datetime import UTC, datetime

import pandas as pd

from research.alpaca_quote_units import sip_sizes_in_shares
from research.crypto_symbol_cache import digest
from research.halt_hft import signal
from research_scout.prepare_halt_hft_20260930 import OUT, ROOT

DEST = OUT / "source_normalized"


def sources(event):
    folder = OUT/"raw"/event["date"]
    quotes = pd.read_parquet(folder/f"{event['symbol']}_quotes.parquet")
    path = folder/f"{event['symbol']}_trades.parquet"
    meta = json.loads(path.with_suffix(".json").read_text())
    if meta["complete"]:
        assert digest(path) == meta["sha256"]
        trades = pd.read_parquet(path)
    else:
        recovery = OUT/"source_audit/recovery"/f"{event['date']}_{event['symbol']}_trades.json"
        provenance = json.loads(recovery.with_suffix(".metadata.json").read_text())
        assert digest(recovery) == provenance["sha256"] and provenance["status"] == 200
        payload = json.loads(recovery.read_text())
        assert payload["symbol"] == event["symbol"] and payload["trades"] is None and payload["next_page_token"] is None
        trades = pd.DataFrame({"timestamp": pd.Series([], dtype="datetime64[ns, UTC]")})
    normalized = trades.copy()
    if event["exchange"] == "Nasdaq" and "exchange" in normalized:
        normalized.loc[normalized.exchange.eq("T"), "exchange"] = "Q"
    return sip_sizes_in_shares(quotes, legacy_round_lot_shares=100, feed="sip"), trades, normalized


def main():
    DEST.mkdir(exist_ok=True)
    if (DEST/"screen.parquet").exists():
        raise RuntimeError("Preserve frozen revised screen")
    original = json.loads((OUT/"screen_implementation.json").read_text())
    for name, value in original["implementation"].items():
        assert digest(ROOT/name) == value
    correction = {"created_at_utc": datetime.now(UTC).isoformat(), "original_specification_sha256": digest(OUT/"specification.json"),
                  "implementation_sha256": digest(__file__),
                  "scope": "For Nasdaq-listed events only, treat Alpaca exchangeT (NASDAQ Int) andQ (NASDAQ OMX) as Nasdaq venue identifiers when locating a condition5 reopening print. No trade price/time, quote, family, threshold, fee or hold changes. Original feed preserved. Original strict-Q result superseded for this compatibility interpretation.",
                  "evidence": "Alpaca official SDK and OpenAPI name both codes as Nasdaq. Nasdaq confirms T is its CTS identifier. In these files,48 first-half2023 TapeC reopening reports carryT, while later reports carryQ. The provider's exact historical normalization transition and venue identity have not been independently confirmed; all revised economics remain conditional on compatibility interpretation.",
                  "empty_source_recovery": "GWII2023-02-01 andMSSA2023-07-03 HTTP200 bodies explicitly contain matching symbol,trades:null,next_page_token:null. Interpret as no provider trade records, not evidence that no real trades took place. Full raw bodies/hashes saved; original client failures preserved.",
                  "sources": ["https://github.com/alpacahq/alpaca-py/blob/master/alpaca/data/enums.py",
                              "https://github.com/alpacahq/alpaca-docs/blob/master/oas/data/openapi.yaml",
                              "https://www.nasdaqtrader.com/TraderNews.aspx?id=hta2007-007"],
                  "source_clock_capture_verified": False, "strategy_execution_verified": False}
    (DEST/"specification.json").write_text(json.dumps(correction, indent=2)+"\n")
    cohort = pd.read_parquet(OUT/"cohort.parquet")
    rows = []
    for event in cohort.loc[cohort.date.str.startswith("2023")].to_dict("records"):
        quotes, trades, normalized = sources(event)
        row = signal(event, quotes, normalized)
        row["provider_trade_records"] = len(trades)
        if "reopen_index" in row:
            row["original_reopening_exchange"] = str(trades.iloc[row["reopen_index"]]["exchange"])
        rows.append(row)
    panel = pd.DataFrame(rows)
    for column in ["reopen_ns", "decision_ns", "quote_ns", "reopen_index", "pre_index", "old_index", "quote_index", "quantity"]:
        if column in panel:
            panel[column] = pd.array([r.get(column) for r in rows], dtype="Int64")
    panel.to_parquet(DEST/"screen.parquet", index=False)
    result = {"events": len(panel), "eligible": int(panel.eligible.sum()), "outcomes": panel.reason.value_counts().to_dict(),
              "eligible_by_family": panel.loc[panel.eligible, "family"].value_counts().to_dict(),
              "eligible_dates": sorted(panel.loc[panel.eligible, "date"].unique().tolist()),
              "reopening_original_codes": panel.original_reopening_exchange.value_counts().to_dict(),
              "provider_empty_trade_windows": int(panel.provider_trade_records.eq(0).sum()),
              "profitability_tested": False, "reliable_edge_established": False,
              "panel_sha256": digest(DEST/"screen.parquet")}
    (DEST/"results.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
