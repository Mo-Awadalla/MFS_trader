"""Returns-blind audit for the UPRO/SPXU liquidity thermostat."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research_scout import (
    audit_upro_spxu_cross_inverse_aggressor_relay as relay,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "upro_spxu_liquidity_thermostat_returns_blind_audit_v17.json"
)


def exact_window(
    frame: pd.DataFrame,
    day: pd.Timestamp,
    start: str,
    periods: int,
) -> pd.DataFrame | None:
    hour, minute = (int(part) for part in start.split(":"))
    first = day.tz_localize(frame.index.tz) + pd.Timedelta(
        hours=hour,
        minutes=minute,
    )
    wanted = pd.date_range(first, periods=periods, freq="min")
    window = frame.reindex(wanted)
    if len(window) != periods or window.isna().all(axis=1).any():
        return None
    bid = window.bid_px_00.astype(float)
    ask = window.ask_px_00.astype(float)
    if (bid <= 0).any() or (ask < bid).any():
        return None
    return window


def median_spread(frame: pd.DataFrame) -> float:
    bid = frame.bid_px_00.astype(float)
    ask = frame.ask_px_00.astype(float)
    return float(((ask - bid) / ((ask + bid) / 2.0)).median())


def session_signal(pair: dict[str, pd.DataFrame]) -> dict[str, object] | None:
    if not {"UPRO", "SPXU"}.issubset(pair):
        return None
    changes: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        early = exact_window(pair[symbol], pair[symbol].index[0].normalize().tz_localize(None), "09:45", 15)
        late = exact_window(pair[symbol], pair[symbol].index[0].normalize().tz_localize(None), "10:00", 15)
        if early is None or late is None:
            return None
        early_spread = median_spread(early)
        late_spread = median_spread(late)
        if early_spread <= 0 or late_spread <= 0:
            return None
        changes[symbol] = late_spread / early_spread - 1.0
    signs = {
        symbol: int(value > 0) - int(value < 0)
        for symbol, value in changes.items()
    }
    direction = signs["UPRO"] if signs["UPRO"] == signs["SPXU"] else 0
    return {
        "direction": direction,
        "upro_change": changes["UPRO"],
        "spxu_change": changes["SPXU"],
    }


def signal_frame(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for day in sorted(sessions):
        if day in excluded or not 2021 <= day.year <= 2025:
            continue
        signal = session_signal(sessions[day])
        if signal is not None:
            rows.append({"date": day, **signal})
    return pd.DataFrame(rows)


def counts(frame: pd.DataFrame) -> dict[str, int]:
    return {
        "UPRO": int((frame.direction > 0).sum()),
        "SPXU": int((frame.direction < 0).sum()),
        "NO_TRADE": int((frame.direction == 0).sum()),
    }


def main() -> None:
    arca_sessions = relay.sessions(relay.ARCA_PATH)
    equs_sessions = relay.sessions(relay.EQUS_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    arca = signal_frame(arca_sessions, arca_excluded)
    equs = signal_frame(equs_sessions, equs_excluded)
    eligible = relay.eligible_feed_sessions(arca_sessions, arca_excluded)
    coverage = len(arca) / max(eligible, 1)
    nonzero = arca[arca.direction != 0]
    weeks = (
        (arca.date.max() - arca.date.min()).days / 7.0
        if len(arca) > 1
        else 0.0
    )
    signals_per_week = len(nonzero) / weeks if weeks > 0 else 0.0
    minority_fraction = (
        min(
            int((nonzero.direction > 0).sum()),
            int((nonzero.direction < 0).sum()),
        )
        / len(nonzero)
        if not nonzero.empty
        else 0.0
    )
    overlap = arca.merge(equs, on="date", suffixes=("_arca", "_equs"))
    both = overlap[
        (overlap.direction_arca != 0) & (overlap.direction_equs != 0)
    ]
    conditional_agreement = (
        float((both.direction_arca == both.direction_equs).mean())
        if not both.empty
        else 0.0
    )
    action_agreement = (
        float((overlap.direction_arca == overlap.direction_equs).mean())
        if not overlap.empty
        else 0.0
    )
    gates = {
        "valid_window_coverage_at_least_95_percent": coverage >= 0.95,
        "at_least_two_nonzero_signals_per_week": signals_per_week >= 2.0,
        "minority_direction_at_least_20_percent": minority_fraction >= 0.20,
        "conditional_cross_feed_direction_agreement_at_least_65_percent": (
            conditional_agreement >= 0.65
        ),
        "all_date_cross_feed_action_agreement_at_least_55_percent": (
            action_agreement >= 0.55
        ),
    }
    payload = {
        "status": "returns_blind_no_post_signal_prices_or_pnl_read",
        "definition": {
            "early_window": "09:45-09:59 ET",
            "late_window": "10:00-10:14 ET",
            "per_wrapper_change": (
                "late median proportional spread divided by early median "
                "proportional spread minus one"
            ),
            "action": (
                "UPRO if both changes are negative; SPXU if both are positive; "
                "otherwise no trade"
            ),
        },
        "arca_2021_2025": {
            "eligible_feed_session_dates": eligible,
            "valid_window_sessions": int(len(arca)),
            "coverage_fraction": coverage,
            "nonzero_signal_sessions": int(len(nonzero)),
            "signals_per_calendar_week": signals_per_week,
            "direction_counts": counts(arca),
            "minority_direction_fraction": minority_fraction,
            "year_signal_counts": {
                str(year): int(
                    ((arca.date.dt.year == year) & (arca.direction != 0)).sum()
                )
                for year in sorted(arca.date.dt.year.unique())
            },
        },
        "cross_feed_overlap_2023_2025": {
            "overlap_sessions": int(len(overlap)),
            "both_signal_sessions": int(len(both)),
            "conditional_direction_agreement": conditional_agreement,
            "all_date_action_agreement": action_agreement,
            "arca_direction_counts": {
                "UPRO": int((overlap.direction_arca > 0).sum()),
                "SPXU": int((overlap.direction_arca < 0).sum()),
                "NO_TRADE": int((overlap.direction_arca == 0).sum()),
            },
            "equs_direction_counts": {
                "UPRO": int((overlap.direction_equs > 0).sum()),
                "SPXU": int((overlap.direction_equs < 0).sum()),
                "NO_TRADE": int((overlap.direction_equs == 0).sum()),
            },
        },
        "predeclared_feasibility_gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
