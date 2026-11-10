"""Returns-blind feasibility audit for listing-venue participation tilt."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_expanding_analog_memory as analog

ROOT = Path(__file__).resolve().parents[1]
EQUS_PAIR_BARS = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "EQUS.MINI"
    / "bars"
    / "upro_spxu_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst"
)
EQUS_CONDITIONS = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "EQUS.MINI"
    / "dataset_condition_2023_2025.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "upro_spxu_listing_venue_returns_blind_audit_v15.json"
)
START = pd.Timestamp("2023-03-28")
END = pd.Timestamp("2025-12-31")


def degraded(path: Path) -> set[pd.Timestamp]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        pd.Timestamp(row["date"])
        for row in payload["conditions"]
        if row["condition"] == "degraded"
    }


def sessions(path: Path) -> dict[pd.Timestamp, dict[str, pd.DataFrame]]:
    frame = base.load_dbn(path)
    output: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol in ["UPRO", "SPXU"]:
        for day, bars in base.split_sessions(frame[frame.symbol == symbol]).items():
            output.setdefault(day, {})[symbol] = bars
    return output


def totals(frame: pd.DataFrame) -> tuple[float, float]:
    window = base.between(frame, "09:30", "10:29")
    volume = window.volume.astype(float)
    typical = (
        window.open.astype(float)
        + window.high.astype(float)
        + window.low.astype(float)
        + window.close.astype(float)
    ) / 4.0
    return float(volume.sum()), float((volume * typical).sum())


def main() -> None:
    arca = sessions(analog.OLD_PAIR_BARS)
    consolidated = sessions(EQUS_PAIR_BARS)
    excluded = degraded(analog.OLD_CONDITIONS) | degraded(EQUS_CONDITIONS)
    rows: list[dict[str, object]] = []
    for day in sorted(set(arca).intersection(consolidated)):
        if day in excluded or not START <= day <= END:
            continue
        if not {"UPRO", "SPXU"}.issubset(arca[day]):
            continue
        if not {"UPRO", "SPXU"}.issubset(consolidated[day]):
            continue
        shares: dict[str, float] = {}
        dollar_shares: dict[str, float] = {}
        contained = True
        valid = True
        for symbol in ["UPRO", "SPXU"]:
            arca_volume, arca_dollars = totals(arca[day][symbol])
            all_volume, all_dollars = totals(consolidated[day][symbol])
            if min(arca_volume, arca_dollars, all_volume, all_dollars) <= 0:
                valid = False
                break
            shares[symbol] = arca_volume / all_volume
            dollar_shares[symbol] = arca_dollars / all_dollars
            contained = contained and arca_volume <= all_volume
        if not valid:
            continue
        score = shares["UPRO"] - shares["SPXU"]
        dollar_score = dollar_shares["UPRO"] - dollar_shares["SPXU"]
        rows.append(
            {
                "date": day,
                "score": score,
                "dollar_score": dollar_score,
                "direction": int(score > 0) - int(score < 0),
                "dollar_direction": (
                    int(dollar_score > 0) - int(dollar_score < 0)
                ),
                "volume_contained": contained,
                "upro_share": shares["UPRO"],
                "spxu_share": shares["SPXU"],
            }
        )
    frame = pd.DataFrame(rows)
    nonzero = frame[frame.direction != 0].copy()
    span_weeks = (
        (nonzero.date.max() - nonzero.date.min()).days / 7.0
        if len(nonzero) > 1
        else 0.0
    )
    same_direction = nonzero.direction == nonzero.dollar_direction
    payload = {
        "status": "returns_blind_no_afternoon_prices_or_pnl_read",
        "period": f"{START.date()} through {END.date()}",
        "eligible_sessions": len(frame),
        "nonzero_signal_sessions": len(nonzero),
        "signals_per_calendar_week": (
            len(nonzero) / span_weeks if span_weeks > 0 else 0.0
        ),
        "volume_containment_fraction": float(frame.volume_contained.mean()),
        "raw_vs_dollar_share_direction_agreement": float(
            same_direction.mean()
        ),
        "direction_counts": {
            "UPRO": int((nonzero.direction > 0).sum()),
            "SPXU": int((nonzero.direction < 0).sum()),
        },
        "year_counts": {
            str(year): int((nonzero.date.dt.year == year).sum())
            for year in sorted(nonzero.date.dt.year.unique())
        },
        "median_arca_volume_share": {
            "UPRO": float(frame.upro_share.median()),
            "SPXU": float(frame.spxu_share.median()),
        },
        "predeclared_feasibility_gates": {
            "at_least_two_signals_per_week": (
                len(nonzero) / span_weeks >= 2.0 if span_weeks > 0 else False
            ),
            "arca_volume_contained_at_least_99_percent": (
                float(frame.volume_contained.mean()) >= 0.99
            ),
            "raw_and_dollar_share_direction_agree_at_least_90_percent": (
                float(same_direction.mean()) >= 0.9
            ),
            "both_directions_at_least_100_sessions": (
                int((nonzero.direction > 0).sum()) >= 100
                and int((nonzero.direction < 0).sum()) >= 100
            ),
        },
    }
    payload["feasibility_passed"] = all(
        payload["predeclared_feasibility_gates"].values()
    )
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
