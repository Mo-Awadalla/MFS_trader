"""Returns-blind audit for persistent premarket wrapper premium."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from research_scout import (
    audit_upro_spxu_cross_inverse_aggressor_relay as relay,
)
from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
ARCA_SPY = base.SPY_PATH
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
    / "upro_spxu_premarket_wrapper_premium_returns_blind_audit_v19.json"
)


def spy_sessions(path: Path) -> dict[pd.Timestamp, pd.DataFrame]:
    return base.split_sessions(base.load_dbn(path, "SPY"))


def exact_price(
    frame: pd.DataFrame,
    day: pd.Timestamp,
    clock: str,
    field: str,
) -> float | None:
    hour, minute = (int(part) for part in clock.split(":"))
    row = base.exact_row(
        frame,
        day.tz_localize(frame.index.tz)
        + pd.Timedelta(hours=hour, minutes=minute),
    )
    if row is None:
        return None
    value = float(row[field])
    return value if value > 0 else None


def midpoint_at(
    frame: pd.DataFrame,
    day: pd.Timestamp,
    clock: str,
) -> float | None:
    hour, minute = (int(part) for part in clock.split(":"))
    row = base.exact_row(
        frame,
        day.tz_localize(frame.index.tz)
        + pd.Timedelta(hours=hour, minutes=minute),
    )
    return base.midpoint(row) if base.valid_quote(row) else None


def signal_frame(
    spy: dict[pd.Timestamp, pd.DataFrame],
    pair: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> pd.DataFrame:
    days = sorted(set(spy).intersection(pair))
    rows: list[dict[str, object]] = []
    for index in range(1, len(days)):
        day = days[index]
        previous = days[index - 1]
        if day in excluded or previous in excluded or not 2021 <= day.year <= 2025:
            continue
        if not {"UPRO", "SPXU"}.issubset(pair[day]) or not {
            "UPRO",
            "SPXU",
        }.issubset(pair[previous]):
            continue
        spy_previous = exact_price(spy[previous], previous, "15:59", "close")
        upro_previous = midpoint_at(pair[previous]["UPRO"], previous, "15:59")
        spxu_previous = midpoint_at(pair[previous]["SPXU"], previous, "15:59")
        if None in {spy_previous, upro_previous, spxu_previous}:
            continue
        scores: list[float] = []
        valid = True
        for clock in ["08:30", "09:15"]:
            spy_now = exact_price(spy[day], day, clock, "close")
            upro_now = midpoint_at(pair[day]["UPRO"], day, clock)
            spxu_now = midpoint_at(pair[day]["SPXU"], day, clock)
            if None in {spy_now, upro_now, spxu_now}:
                valid = False
                break
            spy_gap = math.log(float(spy_now) / float(spy_previous))
            upro_gap = math.log(float(upro_now) / float(upro_previous))
            spxu_gap = math.log(float(spxu_now) / float(spxu_previous))
            scores.append((upro_gap - 3.0 * spy_gap) - (spxu_gap + 3.0 * spy_gap))
        if not valid:
            continue
        signs = [int(score > 0) - int(score < 0) for score in scores]
        direction = signs[0] if signs[0] == signs[1] else 0
        rows.append(
            {
                "date": day,
                "direction": direction,
                "score_0830": scores[0],
                "score_0915": scores[1],
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    arca_pair = relay.sessions(relay.ARCA_PATH)
    equs_pair = relay.sessions(relay.EQUS_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    arca = signal_frame(spy_sessions(ARCA_SPY), arca_pair, arca_excluded)
    equs = signal_frame(spy_sessions(EQUS_SPY), equs_pair, equs_excluded)
    eligible = relay.eligible_feed_sessions(arca_pair, arca_excluded)
    coverage = len(arca) / max(eligible, 1)
    nonzero = arca[arca.direction != 0]
    weeks = (
        (arca.date.max() - arca.date.min()).days / 7.0
        if len(arca) > 1
        else 0.0
    )
    frequency = len(nonzero) / weeks if weeks else 0.0
    minority = (
        float(
            min((nonzero.direction > 0).sum(), (nonzero.direction < 0).sum())
            / len(nonzero)
        )
        if len(nonzero)
        else 0.0
    )
    overlap = arca.merge(equs, on="date", suffixes=("_arca", "_equs"))
    both = overlap[
        (overlap.direction_arca != 0) & (overlap.direction_equs != 0)
    ]
    conditional = (
        float((both.direction_arca == both.direction_equs).mean())
        if len(both)
        else 0.0
    )
    action = (
        float((overlap.direction_arca == overlap.direction_equs).mean())
        if len(overlap)
        else 0.0
    )
    gates = {
        "exact_observation_coverage_at_least_80_percent": coverage >= 0.80,
        "at_least_two_signals_per_week": frequency >= 2.0,
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "conditional_cross_feed_agreement_at_least_70_percent": conditional >= 0.70,
        "all_date_action_agreement_at_least_60_percent": action >= 0.60,
    }
    payload = {
        "status": "returns_blind_no_post_open_returns_or_pnl_read",
        "arca_2021_2025": {
            "eligible_feed_sessions": eligible,
            "exact_state_sessions": len(arca),
            "coverage": coverage,
            "nonzero_signals": len(nonzero),
            "signals_per_week": frequency,
            "direction_counts": {
                "UPRO": int((nonzero.direction > 0).sum()),
                "SPXU": int((nonzero.direction < 0).sum()),
            },
            "minority_fraction": minority,
        },
        "cross_feed": {
            "overlap": len(overlap),
            "both_signal": len(both),
            "conditional_agreement": conditional,
            "all_action_agreement": action,
        },
        "predeclared_feasibility_gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
