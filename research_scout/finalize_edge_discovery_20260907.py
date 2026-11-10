"""Summarize source timing and known benchmark arithmetic, without price outcomes."""

from __future__ import annotations

import gzip
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import exchange_calendars as xc
import pandas as pd

from research_scout.audit_transcript_pilot_20260907 import (
    OUT,
    ROOT,
    TranscriptParser,
    save,
    sha,
)


def main():
    audit = json.loads((OUT / "pilot_audit.json").read_text(encoding="utf-8"))
    calendar = xc.get_calendar("XNYS", start="2021-01-01", end="2023-12-31")
    schedule = calendar.schedule
    opens = pd.DatetimeIndex(schedule["open"])
    closes = pd.DatetimeIndex(schedule["close"])
    full = pd.DatetimeIndex(
        [
            t
            for t, c in zip(opens, closes, strict=True)
            if c.tz_convert("America/New_York").strftime("%H:%M") == "16:00"
        ]
    )

    def next_open(value):
        ready = pd.Timestamp(value) + pd.Timedelta(minutes=30)
        return full[full.searchsorted(ready, side="right")]

    rows = []
    for row in audit["documents"]:
        if "published" not in row:
            continue
        parser = TranscriptParser()
        parser.feed(
            gzip.decompress((OUT / "pilot_raw" / f"{row['symbol']}.gz").read_bytes()).decode(
                "utf-8"
            )
        )
        call = None
        for block in parser.blocks[:5]:
            label = re.search(
                r"([A-Z][a-z]{2} \d{1,2}, \d{4}), (\d{1,2}:\d{2}) ([ap])\.m\. ET", block["text"]
            )
            if label:
                call = datetime.strptime(
                    label[1] + " " + label[2] + " " + label[3].upper() + "M", "%b %d, %Y %I:%M %p"
                ).replace(tzinfo=ZoneInfo("America/New_York"))
                break
        pub = pd.Timestamp(row["published"])
        mod = pd.Timestamp(row["modified"])
        rows.append(
            {
                "symbol": row["symbol"],
                "call_start_ny": call.isoformat() if call else None,
                "published_ny": pub.tz_convert("America/New_York").isoformat(),
                "modified_ny": mod.tz_convert("America/New_York").isoformat(),
                "hours_call_start_to_publication": round(
                    (pub - pd.Timestamp(call)).total_seconds() / 3600, 4
                )
                if call
                else None,
                "first_full_open_after_publication_buffer": str(
                    next_open(pub).tz_convert("America/New_York")
                ),
                "first_full_open_after_current_version_buffer": str(
                    next_open(max(pub, mod)).tz_convert("America/New_York")
                ),
                "current_version_changes_entry_day": bool(
                    next_open(pub) != next_open(max(pub, mod))
                ),
                "ticker_matches_headline": f"({row['symbol']})" in row["headline"],
            }
        )
    save(
        "publication_timing_audit.json",
        {
            "note": "Illustrative 30-minute buffer plus next full session; no return or trade signal. Call start is not call end. Current metadata is not independently archived vintage proof.",
            "documents": rows,
        },
    )
    # Use the already recorded benchmark; do not load any new market-price rows.
    closed = json.loads(
        (ROOT / "research_scout/new_information_tests_20260907/V96_evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    # Its value is retained explicitly in the prior final report and verification.
    benchmark = 132.3969124078269 / 100
    assert "132.3969124078269" in json.dumps(closed)
    hurdle_rows = [
        {
            "invested_days": n,
            "required_geometric_net_bps_per_invested_day": (benchmark ** (1 / n) - 1) * 10000,
            "required_geometric_gross_bps_at_5_each_side": (
                benchmark ** (1 / n) * (1.0005 / 0.9995) - 1
            )
            * 10000,
        }
        for n in [100, 250, 500]
    ]
    save(
        "opportunity_hurdles.json",
        {
            "benchmark": "Previously recorded 2021-2023 SPY legacy adjusted total-return proxy; no new strategy return.",
            "benchmark_factor": benchmark,
            "assumptions": "Fully invested on each invested day, zero idle-cash interest, fractional long shares. Required geometric average equals SPY; exceeding it is required to beat SPY. The gross column uses only a declared all-in 5bps each way profile. These are arithmetic requirements, not measured edges or forecasts.",
            "rows": hurdle_rows,
        },
    )
    protocol = json.loads((OUT / "discovery_protocol.json").read_text(encoding="utf-8"))
    unchanged = {
        p: sha((ROOT / p).read_bytes()) == expected
        for p, expected in protocol["local_price_file_hashes"].items()
    }
    save(
        "discovery_verdict.json",
        {
            "status": "new_research_lead_with_partial_source_feasibility",
            "edge_validated": False,
            "new_strategy_backtests": 0,
            "new_trade_signals": 0,
            "paid_data_or_inference_calls": 0,
            "fixed_pilot_companies": 12,
            "fixed_pilot_documents_retrieved": len(rows),
            "complete_parser_checks": sum(not r["problems"] for r in audit["documents"]),
            "parser_ok_and_no_version_induced_entry_change": [
                r["symbol"]
                for r in audit["documents"]
                if not r["problems"]
                and not next(
                    t["current_version_changes_entry_day"]
                    for t in rows
                    if t["symbol"] == r["symbol"]
                )
            ],
            "same_date_timing_changes": [
                r["symbol"] for r in rows if r["current_version_changes_entry_day"]
            ],
            "known_price_source_hashes_unchanged": unchanged,
            "missing_pilot_price_files": protocol["missing_local_daily_price_files"],
            "readiness": "Pilot demonstrates structured public text retrieval. Broad historical coverage, original versions, signal definition, trading economics and independent confirmation remain unestablished. No new V-number or failed-PnL claim is assigned.",
        },
    )
    print(
        json.dumps(
            {
                "publication_timing": rows,
                "hurdles": hurdle_rows,
                "all_original_hashes_unchanged": all(unchanged.values()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
