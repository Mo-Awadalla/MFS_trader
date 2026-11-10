"""Returns-blind feasibility audit for official macro-release delayed discovery v45."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay_audit

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research_scout" / "spy_official_macro_release_delayed_discovery_prereg_v45.json"
CENSUS = ROOT / "research_scout" / "census_macro_release_calendar_v45.json"
FOMC = ROOT / "research_scout" / "fomc_statement_calendar_v45.json"
OUTPUT = ROOT / "research_scout" / "spy_official_macro_release_returns_blind_audit_v45.json"
EQUS_SPY = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "EQUS.MINI"
    / "bars"
    / "spy_sh_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst"
)
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
EQUS_START = pd.Timestamp("2023-03-28")
CLOCKS = {
    "08:30:00": {
        "signal_start": time(9, 30),
        "signal_end": time(9, 39),
        "entry": time(9, 41),
        "exit": time(9, 55),
    },
    "10:00:00": {
        "signal_start": time(10, 0),
        "signal_end": time(10, 9),
        "entry": time(10, 11),
        "exit": time(13, 55),
    },
    "14:00:00": {
        "signal_start": time(14, 0),
        "signal_end": time(14, 9),
        "entry": time(14, 11),
        "exit": time(15, 30),
    },
}
CLOCK_ALIASES = {
    "8:30 AM": "08:30:00",
    "10:00 AM": "10:00:00",
    "2:00 PM": "14:00:00",
}


def load_episodes() -> list[dict[str, Any]]:
    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    fomc = json.loads(FOMC.read_text(encoding="utf-8"))
    grouped: dict[tuple[pd.Timestamp, str], set[str]] = {}
    sources: dict[tuple[pd.Timestamp, str], set[str]] = {}
    for row in census["events"]:
        day = pd.Timestamp(datetime.strptime(row["release_date"], "%B %d, %Y").date())
        clock = CLOCK_ALIASES[row["release_time_et"]]
        key = (day, clock)
        grouped.setdefault(key, set()).add(str(row["event_family"]))
        sources.setdefault(key, set()).add(str(row["source_url"]))
    for row in fomc["events"]:
        day = pd.Timestamp(row["release_date"])
        clock = CLOCK_ALIASES[fomc["release_time_et"]]
        key = (day, clock)
        grouped.setdefault(key, set()).add(str(fomc["event_family"]))
        sources.setdefault(key, set()).add(str(row["statement_url"]))
    return [
        {
            "date": day,
            "release_clock": clock,
            "families": sorted(grouped[(day, clock)]),
            "sources": sorted(sources[(day, clock)]),
        }
        for day, clock in sorted(grouped)
    ]


def valid_quote(row: Any) -> bool:
    if row is None:
        return False
    bid = float(row.bid_px_00)
    ask = float(row.ask_px_00)
    return bid > 0 and ask >= bid


def exact_quote(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    symbol: str,
    clock: time,
) -> Any | None:
    quotes = sessions.get(day, {}).get(symbol)
    if quotes is None:
        return None
    stamp = v16.stamp(day, clock, quotes.index.tz)
    row = base.quote_at(quotes, stamp, 0)
    return row if valid_quote(row) else None


def signal_direction(
    sessions: dict[pd.Timestamp, pd.DataFrame],
    day: pd.Timestamp,
    release_clock: str,
) -> int | None:
    setup = CLOCKS[release_clock]
    bars = sessions.get(day)
    if bars is None:
        return None
    start_stamp = v16.stamp(day, setup["signal_start"], bars.index.tz)
    end_stamp = v16.stamp(day, setup["signal_end"], bars.index.tz)
    start = base.exact_row(bars, start_stamp)
    end = base.exact_row(bars, end_stamp)
    if start is None or end is None:
        return None
    start_close = float(start.close)
    end_close = float(end.close)
    if min(start_close, end_close) <= 0:
        return None
    return int(end_close > start_close) - int(end_close < start_close)


def execution_complete(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    release_clock: str,
) -> bool:
    setup = CLOCKS[release_clock]
    return all(
        exact_quote(sessions, day, symbol, clock) is not None
        for symbol in ["UPRO", "SPXU"]
        for clock in [setup["entry"], setup["exit"]]
    )


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("V45 preregistration is required before audit")
    episodes = [row for row in load_episodes() if START <= row["date"] <= END]
    spy_sessions, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    equs_spy = base.split_sessions(base.load_dbn(EQUS_SPY, "SPY"))
    equs_spy_excluded = relay_audit.degraded(relay_audit.EQUS_CONDITIONS)
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        day = episode["date"]
        clock = episode["release_clock"]
        market_session = day in spy_sessions
        arca_direction = None
        arca_execution = False
        if market_session and day not in arca_excluded:
            arca_direction = signal_direction(spy_sessions, day, clock)
            arca_execution = execution_complete(arca, day, clock)
        equs_direction = None
        if day >= EQUS_START and day in equs_spy and day not in equs_spy_excluded:
            equs_direction = signal_direction(equs_spy, day, clock)
        rows.append(
            {
                **episode,
                "market_session": market_session,
                "arca_direction": arca_direction,
                "arca_execution_complete_for_both_actuators": arca_execution,
                "equs_direction": equs_direction,
                "signal_nonzero": arca_direction not in (None, 0),
                "complete": arca_direction is not None and arca_execution,
                "executable": arca_direction not in (None, 0) and arca_execution,
            }
        )

    frame = pd.DataFrame(rows)
    executable = frame.loc[frame.executable].copy()
    weeks = (END - START).days / 7.0
    complete_fraction = float(frame.complete.mean()) if len(frame) else 0.0
    trades_per_week = len(executable) / weeks
    years = {
        str(year): int((executable.date.dt.year == year).sum())
        for year in [2021, 2022, 2023]
    }
    clocks = {
        clock: int((executable.release_clock == clock).sum()) for clock in CLOCKS
    }
    directions = {
        "UPRO": int((executable.arca_direction > 0).sum()),
        "SPXU": int((executable.arca_direction < 0).sum()),
    }
    minority = min(directions.values()) / max(len(executable), 1)
    overlap = frame.loc[
        (frame.date >= EQUS_START)
        & frame.arca_direction.notna()
        & frame.equs_direction.notna()
    ].copy()
    feed_agreement = (
        float((overlap.arca_direction == overlap.equs_direction).mean())
        if len(overlap)
        else 0.0
    )
    non_market = int((~frame.market_session).sum())
    family_counts = Counter(
        family for families in executable.families for family in families
    )
    causality = all(
        setup["signal_start"] < setup["signal_end"]
        and (
            datetime.combine(datetime.min.date(), setup["signal_end"])
            + pd.Timedelta(minutes=1)
        ).time()
        < setup["entry"]
        < setup["exit"]
        for setup in CLOCKS.values()
    ) and CLOCKS["08:30:00"]["exit"] < time(10, 0) and CLOCKS["10:00:00"]["exit"] < time(14, 0)
    gates = {
        "complete_fraction_at_least_95_percent": complete_fraction >= 0.95,
        "at_least_two_executable_trades_per_calendar_week": trades_per_week >= 2.0,
        "at_least_100_executable_trades_each_development_year": all(
            value >= 100 for value in years.values()
        ),
        "all_release_clocks_represented": all(value > 0 for value in clocks.values()),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "arca_equs_direction_agreement_at_least_75_percent": feed_agreement >= 0.75,
        "strict_nonoverlapping_timestamp_causality": causality,
    }
    payload = {
        "status": "returns_blind_no_post_entry_return_or_pnl_computed",
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "scheduled_development_episodes": int(len(frame)),
        "non_market_date_clock_episodes": non_market,
        "complete_episodes": int(frame.complete.sum()),
        "complete_fraction": complete_fraction,
        "nonzero_signal_episodes": int(frame.signal_nonzero.sum()),
        "executable_trades": int(len(executable)),
        "executable_trades_per_calendar_week": trades_per_week,
        "year_counts": years,
        "release_clock_counts": clocks,
        "direction_counts": directions,
        "minority_direction_fraction": minority,
        "equs_overlap_comparisons": int(len(overlap)),
        "arca_equs_direction_agreement": feed_agreement,
        "executable_family_record_counts": dict(sorted(family_counts.items())),
        "predeclared_feasibility_gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
