"""Freeze a CPI content-error HFT protocol before opening market outcomes."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.cpi_model_error import model_error_event
from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/macro_surprise_hft_20260930"


def main():
    path = OUT/"specification.json"
    if path.exists():
        raise RuntimeError("Frozen protocol exists")
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(), "family": "CPI error against prior public Cleveland Fed model",
        "relation_to_prior": "V45 used ten-minute price direction after announcement calendars, with minutes-to-hours holds, and failed. This test uses actual first-release CPI content against dated earlier public-model forecasts and holds seconds. It is still part of the global multi-search history; new independence is not claimed.",
        "partition": {"development_release_years": [2017, 2018, 2019, 2020, 2021, 2022, 2023],
                      "selection_release_years": [2024, 2025], "selection_opened": False},
        "source": "Cleveland Fed historical monthly chart JSON. Extract first actual CPI/core CPI series on their dated release day; round to one decimal using decimal half-up to match announced summary precision. Last nonempty forecast strictly earlier date, at most5calendar days old, separately for headline/core. Do not use same-day10am updates. Independently reconcile first-announced CPI values/date/08:30ET with archived BLS releases before any market evaluation. Sourcevintages are supplied by the current official historical chart; independently archived dissemination/capture not established.",
        "signal": "Core announced minus last prior forecast <=-0.10 percentage points AND headline error<0: buySPY. Core error>=+0.10 AND headline error>0: buySH. Otherwise cash. The comparator is a public statistical model, NOT observed street consensus or a market-implied surprise. No price-direction filter.",
        "configurations": [{"hold_seconds": 15}, {"hold_seconds": 30}],
        "news_availability": "Nominal BLS08:30ET plus2seconds modeled publication/retrieval/parsing delay. This is a conditional latency assumption, not reconstructed historical receipt.10second news delay stress. Latest quote strictly before decision-1second source latency, must be post-release with valid regular two-sided uncrossed state, at most20bps ask/bid spread. Complete observed source prefix required; unchanged standing quotes not rejected for arbitrary age. Contradictory same-timestamp signal states are unknown, not optimistically selected.",
        "sizing": "Daily reset$10000 cash. Fixed integer floor(min(10000/(knownask*1.01),0.10*known ask shares)); >=$100 ticket.100-share historical round lot is a conditional SPY/SH size assumption to verify if any candidate advances. No future resizing; one order per release per configuration.",
        "entry": "Guarded FOK buy, limit floor-cent(knownask*1.001); arrival decision+250ms processing+1s outbound. Evaluate last quote strictly before target-1ms and all updates through target+1ms, including ties; require successor after window. Every quote must be valid. Allasks>limit implies rejected. Allasks<=limit with sufficient full quantity implies conditional fill; otherwise unresolved possible inventory. Premarket FOK support/routing is not established; this is a quote-reference benchmark.",
        "exit": "Entry ACK arrival+1sreturn.15/30s hold then250msprocessing+1soutbound. Full-quantity sale at all possible valid regular bid states in +/-1ms; any missing/invalid/shallow state unknown. Joint cash bounds enumerate all entryask/exitsell combinations. No paper-fill guarantee, protected-NBBO assumption or auction fill.",
        "costs": {"commission_per_share": .0075, "minimum_per_side": 1, "sell_rate": .00003,
                  "sell_per_share": .0002, "adverse_per_side": .0001},
        "scenarios": ["base", "double_fees", "3s_outgoing_and_return", "double_adverse", "100ms_alignment", "10s_news_delay"],
        "controls": "If a configuration passes initial economics, evaluate unconditional same-timeSPY and next-trading-day same-clock direction controls; do not promote controls as new winners. Sign-flipped symbol control requires its own predeclared data acquisition. All comparisons remain within exposed development.",
        "progression": "Complete lower net positive in every stress, >=12closedtrades on>=12release dates, bothSPY/SH sleeves positive, positive after removing best3dates, date-blockbootstrap97.5%lower bound positive (two configurations). Only then open2024-25 selection with unchanged rules. Require independent later profitability, uncertainty controls, source/routing confirmation and forward evidence before claiming reliability. Zero/unknown days remain in accounting; never remove bad paths or select date ranges to rescue P&L.",
        "download": {"window_et": ["08:29:45", "08:31:00"], "feed": "sip", "max_pages": 80,
                     "per_file_max_bytes": 20000000, "total_max_bytes": 1000000000,
                     "max_seconds_per_file": 120, "market_data_only": True, "paid_fallback": False},
        "source_sha256": {"source_audit/nowcast_month.json": digest(OUT/"source_audit/nowcast_month.json"),
                          "research/cpi_model_error.py": digest(ROOT/"research/cpi_model_error.py")},
        "sources": ["https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting",
                    "https://www.bls.gov/bls/news-release/cpi.htm",
                    "https://docs.alpaca.markets/us/docs/market-data-faq"],
        "execution_verified": False, "reliable_edge_established": False}
    path.write_text(json.dumps(spec, indent=2)+"\n")
    data = json.loads((OUT/"source_audit/nowcast_month.json").read_text())
    rows = []
    for chart in data:
        y, m = (int(v) for v in chart["chart"]["subcaption"].split("-"))
        if (y, m) < (2016, 12) or (y, m) > (2023, 11):
            continue
        event = model_error_event(chart)
        assert "2017-01-01" <= event["release_date"] <= "2023-12-31"
        rows.append(event)
    assert len(rows) == 84 and len({r["release_date"] for r in rows}) == 84
    panel = pd.DataFrame(rows)
    panel.to_parquet(OUT/"content_events.parquet", index=False)
    result = {"development_releases": len(panel), "content_triggers": int(panel.content_trigger.sum()),
              "trigger_symbols": panel.loc[panel.content_trigger, "symbol"].value_counts().to_dict(),
              "by_year": panel.groupby(panel.release_date.str[:4]).content_trigger.sum().to_dict(),
              "first_release_crosscheck_complete": False, "market_outcomes_opened": False,
              "panel_sha256": digest(OUT/"content_events.parquet")}
    (OUT/"content_results.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
