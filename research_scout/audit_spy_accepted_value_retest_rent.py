"""Returns-blind audit for SPY Accepted-Value Retest Rent v27."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as xfeed
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
EQUS_SPY = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "EQUS.MINI"
    / "bars"
    / "spy_sh_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "spy_accepted_value_retest_rent_returns_blind_audit_v27.json"
)


def clock(index: int) -> time:
    return (
        pd.Timestamp("2000-01-01 09:30") + pd.Timedelta(minutes=index)
    ).time()


def signal(bars: pd.DataFrame) -> dict[str, Any] | None:
    opening = bars.between_time("09:30", "09:59")
    if len(opening) != 30:
        return None
    typical = (opening.high + opening.low + opening.close) / 3.0
    center = float((typical * opening.volume).sum() / opening.volume.sum())
    cash_open = float(opening.iloc[0].open)
    close = float(opening.iloc[-1].close)
    side = (
        1
        if center > cash_open and close > cash_open
        else -1
        if center < cash_open and close < cash_open
        else 0
    )
    if side == 0:
        return {"side": 0}
    rth = bars.between_time("09:30", "15:59")
    if len(rth) < 240:
        return None
    contact_index = None
    for index in range(30, 240):
        bar = rth.iloc[index]
        touched = (
            float(bar.low) <= center
            if side > 0
            else float(bar.high) >= center
        )
        if touched:
            contact_index = index
            break
    if contact_index is None or contact_index + 1 >= len(rth):
        return {"side": 0}
    contact = rth.iloc[contact_index]
    survived = (
        float(contact.close) > center and float(contact.low) > cash_open
        if side > 0
        else float(contact.close) < center and float(contact.high) < cash_open
    )
    if not survived:
        return {"side": 0}
    dead = rth.iloc[contact_index + 1]
    invalidated = (
        float(dead.low) <= cash_open
        if side > 0
        else float(dead.high) >= cash_open
    )
    if invalidated:
        return {"side": 0}
    return {
        "side": side,
        "entry_index": contact_index + 2,
        "center": center,
        "cash_open": cash_open,
    }


def main() -> None:
    spy, arca, _, arca_excluded, _ = v16.load_old()
    equs_spy = base.split_sessions(base.load_dbn(EQUS_SPY, "SPY"))
    equs_excluded = xfeed.degraded(xfeed.EQUS_CONDITIONS)
    rows: list[dict[str, Any]] = []
    for day, bars in sorted(spy.items()):
        if day in arca_excluded or not v16.START <= day <= v16.DEVELOPMENT_END:
            continue
        state = signal(bars)
        if state is None or int(state["side"]) == 0:
            continue
        side = int(state["side"])
        symbol = "UPRO" if side > 0 else "SPXU"
        quotes = arca.get(day, {}).get(symbol)
        available = False
        if quotes is not None:
            stamp = v16.stamp(
                day,
                clock(int(state["entry_index"])),
                quotes.index.tz,
            )
            available = base.quote_at(quotes, stamp, 0) is not None
        rows.append(
            {
                "date": day,
                "side": side,
                "available": available,
            }
        )
    frame = pd.DataFrame(rows)
    executable = frame[frame.available].copy()
    frequency = len(executable) / (3 * 52)
    minority = (
        min(
            int((executable.side > 0).sum()),
            int((executable.side < 0).sum()),
        )
        / max(len(executable), 1)
    )
    years = {
        str(year): int((executable.date.dt.year == year).sum())
        for year in [2021, 2022, 2023]
    }
    common = sorted(
        set(spy).intersection(equs_spy) - arca_excluded - equs_excluded
    )
    overlap = both = same = actions = 0
    for day in common:
        if not pd.Timestamp("2023-03-28") <= day <= v16.HOLDOUT_END:
            continue
        left = signal(spy[day])
        right = signal(equs_spy[day])
        la = 0 if left is None else int(left["side"])
        ra = 0 if right is None else int(right["side"])
        overlap += 1
        actions += int(la == ra)
        if la and ra:
            both += 1
            same += int(la == ra)
    direction_agreement = same / max(both, 1)
    action_agreement = actions / max(overlap, 1)
    availability = float(frame.available.mean()) if len(frame) else 0.0
    gates = {
        "at_least_two_entries_per_week": frequency >= 2.0,
        "every_year_at_least_100_entries": all(v >= 100 for v in years.values()),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "entry_quote_availability_at_least_95_percent": availability >= 0.95,
        "cross_feed_direction_agreement_at_least_90_percent": (
            direction_agreement >= 0.90
        ),
        "cross_feed_action_agreement_at_least_80_percent": (
            action_agreement >= 0.80
        ),
    }
    payload = {
        "status": "returns_blind_no_post_entry_prices_or_pnl_read",
        "candidate_entries": int(len(frame)),
        "executable_entries": int(len(executable)),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((executable.side > 0).sum()),
            "SPXU": int((executable.side < 0).sum()),
        },
        "minority_direction_fraction": minority,
        "year_counts": years,
        "entry_quote_availability": availability,
        "cross_feed": {
            "overlap_dates": overlap,
            "both_signal_dates": both,
            "same_direction_fraction": direction_agreement,
            "same_action_fraction": action_agreement,
        },
        "gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
