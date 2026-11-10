"""Returns-blind audit for BTC spot flow baton to UPRO/SPXU v26."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
BTC_PATH = (
    ROOT
    / "data"
    / "parquet"
    / "binance_bitcoin_derivatives_public_v1"
    / "normalized"
    / "spot_klines_30m.parquet"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "btc_spot_flow_baton_returns_blind_audit_v26.json"
)


def load_btc() -> pd.DataFrame:
    frame = pd.read_parquet(BTC_PATH).copy()
    if not (frame["product"] == "spot_klines_30m").all():
        raise AssertionError("V26 may use BTC spot bars only")
    frame["open_time"] = pd.to_datetime(frame.open_time, utc=True)
    frame = frame.set_index("open_time").tz_convert("America/New_York")
    frame["day"] = frame.index.tz_localize(None).normalize()
    return frame


def cohort(
    btc: pd.DataFrame,
    day: pd.Timestamp,
    start: pd.Timestamp,
    end: pd.Timestamp,
    expected: int,
) -> dict[str, Any] | None:
    work = btc[(btc.index >= start) & (btc.index <= end)]
    if len(work) != expected or float(work.quote_volume.sum()) <= 0:
        return None
    signed = 2.0 * work.taker_buy_quote_volume - work.quote_volume
    imbalance = float(signed.sum() / work.quote_volume.sum())
    price_return = float(work.iloc[-1].close / work.iloc[0].open - 1.0)
    return {
        "day": day,
        "imbalance": imbalance,
        "price_return": price_return,
        "bars": len(work),
    }


def signal_for(btc: pd.DataFrame, day: pd.Timestamp) -> dict[str, Any] | None:
    tz = btc.index.tz
    prior = day - pd.Timedelta(days=1)
    asia_start = pd.Timestamp.combine(prior.date(), time(16, 0)).tz_localize(tz)
    asia_end = pd.Timestamp.combine(day.date(), time(0, 30)).tz_localize(tz)
    europe_start = pd.Timestamp.combine(day.date(), time(1, 0)).tz_localize(tz)
    europe_end = pd.Timestamp.combine(day.date(), time(8, 30)).tz_localize(tz)
    asia = cohort(btc, day, asia_start, asia_end, 18)
    europe = cohort(btc, day, europe_start, europe_end, 16)
    if asia is None or europe is None:
        return None
    left = float(asia["imbalance"])
    right = float(europe["imbalance"])
    direction = (
        1 if left > 0 and right > 0 else -1 if left < 0 and right < 0 else 0
    )
    return {
        "direction": direction,
        "asia": asia,
        "europe": europe,
    }


def main() -> None:
    btc = load_btc()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    eligible_dates = [
        day
        for day in sorted(spy)
        if day not in arca_excluded
        and v16.START <= day <= v16.DEVELOPMENT_END
    ]
    measurements: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    for day in eligible_dates:
        state = signal_for(btc, day)
        if state is None:
            continue
        measurements.append(
            {
                "date": day,
                "asia_imbalance": state["asia"]["imbalance"],
                "asia_return": state["asia"]["price_return"],
                "europe_imbalance": state["europe"]["imbalance"],
                "europe_return": state["europe"]["price_return"],
            }
        )
        direction = int(state["direction"])
        if direction == 0:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        quotes = arca.get(day, {}).get(symbol)
        arca_entry = False
        if quotes is not None:
            stamp = v16.stamp(day, time(9, 31), quotes.index.tz)
            arca_entry = base.quote_at(quotes, stamp, 0) is not None
        eq_quotes = (
            equs.get(day, {}).get(symbol)
            if day not in equs_excluded
            else None
        )
        equs_entry = False
        if eq_quotes is not None:
            eq_stamp = v16.stamp(day, time(9, 31), eq_quotes.index.tz)
            equs_entry = base.quote_at(eq_quotes, eq_stamp, 0) is not None
        signals.append(
            {
                "date": day,
                "direction": direction,
                "symbol": symbol,
                "arca_entry": arca_entry,
                "equs_entry": equs_entry,
            }
        )
    measured = pd.DataFrame(measurements)
    frame = pd.DataFrame(signals)
    executable = frame[frame.arca_entry].copy()
    frequency = len(executable) / (3 * 52)
    minority = (
        min(
            int((executable.direction > 0).sum()),
            int((executable.direction < 0).sum()),
        )
        / max(len(executable), 1)
    )
    year_counts = {
        str(year): int((executable.date.dt.year == year).sum())
        for year in [2021, 2022, 2023]
    }
    asia_coherence = float(
        (
            measured.asia_imbalance.mul(measured.asia_return) > 0
        ).mean()
    )
    europe_coherence = float(
        (
            measured.europe_imbalance.mul(measured.europe_return) > 0
        ).mean()
    )
    overlap = executable[executable.date >= pd.Timestamp("2023-03-28")]
    measurement_coverage = len(measured) / max(len(eligible_dates), 1)
    arca_availability = (
        float(frame.arca_entry.mean()) if len(frame) else 0.0
    )
    equs_availability = (
        float(overlap.equs_entry.mean()) if len(overlap) else 0.0
    )
    gates = {
        "btc_measurement_coverage_at_least_98_percent": (
            measurement_coverage >= 0.98
        ),
        "at_least_two_entries_per_week": frequency >= 2.0,
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "every_development_year_at_least_100_entries": all(
            value >= 100 for value in year_counts.values()
        ),
        "asia_flow_price_coherence_at_least_52_percent": asia_coherence >= 0.52,
        "europe_flow_price_coherence_at_least_52_percent": (
            europe_coherence >= 0.52
        ),
        "arca_entry_availability_at_least_95_percent": (
            arca_availability >= 0.95
        ),
        "equs_overlap_entry_availability_at_least_95_percent": (
            equs_availability >= 0.95
        ),
    }
    payload = {
        "status": "returns_blind_no_post_entry_etf_prices_or_pnl_read",
        "eligible_development_sessions": len(eligible_dates),
        "complete_btc_measurements": len(measured),
        "btc_measurement_coverage": measurement_coverage,
        "executable_entries": int(len(executable)),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((executable.direction > 0).sum()),
            "SPXU": int((executable.direction < 0).sum()),
        },
        "minority_direction_fraction": minority,
        "year_counts": year_counts,
        "own_market_flow_price_coherence": {
            "asia": asia_coherence,
            "europe": europe_coherence,
        },
        "arca_entry_availability": arca_availability,
        "equs_overlap_entry_availability": equs_availability,
        "gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
