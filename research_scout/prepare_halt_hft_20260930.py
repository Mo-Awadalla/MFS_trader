"""Freeze halt-event cohort and economics before opening quote/trade outcomes."""

import json
from datetime import UTC, datetime
from pathlib import Path

import exchange_calendars as xc
import pandas as pd

from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/halt_hft_20260930"


def main():
    spec_path = OUT / "specification.json"
    if spec_path.exists():
        raise RuntimeError("Frozen protocol already exists")
    source = OUT / "source_audit/nyse_halts.csv"
    raw = pd.read_csv(source, keep_default_na=False)
    calendar = xc.get_calendar("XNYS", start="2023-01-01", end="2024-12-31")
    sessions = pd.Series(calendar.sessions.strftime("%Y-%m-%d"))
    dates = sessions.groupby(sessions.str[:7]).first().tolist()
    x = raw.loc[raw["Halt Date"].isin(dates) & raw.Reason.eq("LULD pause")].copy()
    x = x.loc[x.Exchange.isin(["Nasdaq", "NYSE", "NYSE American"])
              & x.Symbol.str.fullmatch("[A-Z]{1,5}")
              & x.Name.str.contains(r"Common|Ordinary Share", case=False, regex=True)
              & ~x.Name.str.contains(r"Warrant|Preferred|Depositary|\bUnit\b", case=False, regex=True)]
    # First halt is selected before clock/duration filtering, never replaced by a later one.
    x = x.sort_values(["Halt Date", "Halt Time", "Symbol"]).drop_duplicates(["Halt Date", "Symbol"])
    rows = []
    for r in x.to_dict("records"):
        day = r["Halt Date"]
        if r["Resume Date"] != day or not r["NYSE Resume Time"]:
            continue
        halt = pd.Timestamp(day + " " + r["Halt Time"], tz="America/New_York").tz_convert("UTC")
        resume = pd.Timestamp(day + " " + r["NYSE Resume Time"], tz="America/New_York").tz_convert("UTC")
        close = calendar.session_close(day)
        if not (pd.Timestamp(day + " 09:35", tz="America/New_York") <= halt <= close-pd.Timedelta(minutes=10)
                and resume <= close-pd.Timedelta(minutes=5) and 295 <= (resume-halt).total_seconds() <= 900):
            continue
        rows.append({"date": day, "symbol": r["Symbol"], "name": r["Name"], "exchange": r["Exchange"],
                     "halt_ns": halt.value, "archive_resume_ns": resume.value,
                     "start_ns": (halt-pd.Timedelta(seconds=45)).value,
                     "end_ns": (resume+pd.Timedelta(seconds=75)).value})
    panel = pd.DataFrame(rows)
    panel.to_parquet(OUT / "cohort.parquet", index=False)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "purpose": "Conditional source-clock economics after a stock volatility halt; no auction fill assumed.",
        "dates": dates, "cohort_events": len(panel),
        "cohort": "First LULD halt per historical common/ordinary-share symbol per first XNYS session of each month in 2023/2024. Listing venue Nasdaq,NYSE,NYSE American; symbol A-Z 1-5 letters, excludes names indicating warrant,preferred,depositary,unit. First halt selected before time/duration filters. Halt >=09:35 and <=close-10min, same-day resume <=close-5min, archived duration295..900s. Existing and delisted symbols retained; no current ticker universe.",
        "development": "2023; fetch/evaluate first. Selection2024 stays closed unless development passes.2025/2026 outcomes not used.",
        "prior_exposure": "Source metadata and total cohort counts inspected; no quote/trade outcomes opened. Extensive other HFT searches remain part of selection history. Registry search found no exact LULD rule but novelty is not established exhaustively.",
        "configurations": [{"family": f, "hold_seconds": h} for f in ["up_continuation", "down_rebound"] for h in [15, 30]],
        "reopening": "First primary-listing-venue trade carrying condition5 within archive resume +/-5s; positive price/size, no late/sold/average/prior-reference flags. A reported reopening is a signal anchor only, never our entry. Archive used for cohort/quality alignment; live administrative publication timing is unverified.",
        "signal": "Prehalt mid return from halt-30s to halt-1s >=100bp for up_continuation or <=-100bp for down_rebound. Both require reopening price >=last prehalt mid*1.005. Latest strictly-prior quotes at those times must be valid and no more than5s old. Reopening trade availability is modeled as source time+1s; decision5s later. Latest quote strictly before decision-1s must be post-reopening, valid, <=1s old relative to cutoff, bid>=reopening price, ask2..500, spread<=50bp. No outcome-dependent signal changes.",
        "size": "Fixed integer floor(min(10000/(ask*1.01),10% known ask depth)); >=$100 ticket.100-share historical round lot for this price range and dates is a stated conditional assumption requiring source verification. No future resizing. One position globally per rule/scenario, $10000 reset each date; do not enter while pending or inventory open; require current cash to cover frozen quantity at limit plus fees. Stop that date on unknown possible inventory.",
        "entry": "FOK limit floor-to-cent(known ask*1.001), arrival decision+250ms processing+1s outbound. Model all quote states across +/-1ms around arrival. All states over limit: no fill; all valid with ask<=limit and enough depth: conditional full fill at each possible ask. Mixed/inadequate/invalid states: unknown possible inventory. No liquidity or fill guarantee follows from SIP quotes.",
        "exit": "Entry ACK at entry arrival+1s return latency; hold15/30s then250ms processing+1s outbound. Sell full frozen quantity across all SIP states in +/-1ms. Require positive regular noncrossed quote and full bid depth in every state. Any subsequent halt interval intersecting entry-to-exit path, expanded1s for archive precision, leaves inventory unresolved; no forced sale through a pause. Exit ACK adds1s return. No future quantity clipping.",
        "quote_windows": "Last quote strictly before low endpoint plus all updates through high endpoint inclusive; keep ties. Require successor after high to bracket the observed stream. No arbitrary standing quote age gate for execution. Missing feed state is unknown, not no-fill.",
        "costs": {"commission_per_share": 0.0075, "minimum_per_side": 1.0,
                  "sell_notional_rate": 0.00003, "sell_per_share": 0.0002, "adverse_per_side": 0.0001},
        "scenarios": ["base", "double_fees", "3s_outgoing_and_return", "double_adverse", "100ms_alignment"],
        "gate": "Proceed only if development is fully resolved, positive lower net in every scenario, >=20 priced trades on>=6 dates, >=3 positive dates, positive lower net after removing best3 dates, and a positive95% date-block bootstrap lower bound after multiplicity adjustment for4 configurations. Selection2024 must independently pass the same gate. Economics never establishes actual routing/fills; source capture and venue evidence would still be required. Do not drop unknown inventory paths or retune failed rules.",
        "download": {"feed": "sip", "initial_year": "2023", "per_file_max_bytes": 20000000,
                     "max_pages": 40, "max_total_response_bytes": 1000000000, "max_seconds_per_file": 120,
                     "workers": 2, "datasets": ["quotes", "trades"],
                     "access": "Existing Alpaca credentials for read-only historical data.alpaca.markets endpoints; free historical access, no upgrade, account calls or orders."},
        "source_sha256": {"nyse_halts.csv": digest(source), "cohort.parquet": digest(OUT/"cohort.parquet")},
        "sources": ["https://www.nyse.com/trade/trading-halts",
                    "https://www.nyse.com/api/trade-halts/historical/download",
                    "https://www.nasdaqtrader.com/content/technicalsupport/specifications/utp/utdfspecification.pdf",
                    "https://docs.alpaca.markets/us/docs/market-data-faq",
                    "https://docs.alpaca.markets/us/v1.1/changelog/marketdata-bid-and-ask-size-display-change"],
        "strategy_execution_verified": False, "reliable_edge_established": False}
    spec_path.write_text(json.dumps(spec, indent=2)+"\n")
    print(json.dumps({"events": len(panel), "by_year": panel.date.str[:4].value_counts().to_dict(),
                      "specification_sha256": digest(spec_path)}))


if __name__ == "__main__":
    main()
