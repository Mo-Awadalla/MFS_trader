"""Exploratory 2024-2025 check of the frozen Late Volume Clock rule."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_pair_geometry as geo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "upro_spxu_late_volume_clock_curiosity_2024_2025.json"
)
HYPOTHESIS = "late_volume_clock_compass"


def main() -> int:
    spy_sessions, feeds = base.load_inputs()
    pair_sessions = geo.load_pair_bars()
    excluded = base.degraded_dates()
    years = range(2024, 2026)
    arca = geo.run_period(
        HYPOTHESIS,
        spy_sessions,
        pair_sessions,
        feeds["arca"],
        excluded,
        years,
    )
    stress = geo.stress_table(
        HYPOTHESIS,
        arca,
        "holdout",
        spy_sessions,
        pair_sessions,
        feeds["arca"],
        excluded,
        years,
    )
    consolidated = geo.run_period(
        HYPOTHESIS,
        spy_sessions,
        pair_sessions,
        feeds["consolidated"],
        excluded,
        years,
    )
    stress["consolidated_bbo"] = geo.summary_or_empty(consolidated, "holdout")
    eligible_days = [
        day
        for day in sorted(spy_sessions)
        if day.year in years and day not in excluded
    ]
    stress["five_session_block_bootstrap"] = (
        base.moving_block_bootstrap(arca, eligible_days)
        if not arca.empty
        else {"trades": 0}
    )
    results: dict[str, Any] = {
        "status": "exploratory_curiosity_check_not_clean_validation",
        "reason": (
            "The candidate failed its frozen development frequency gate, and "
            "the user explicitly requested the otherwise locked 2024-2025 result."
        ),
        "unchanged_specification": (
            "research_scout/upro_spxu_pair_geometry_prereg_v2.json"
        ),
        "candidate": HYPOTHESIS,
        "period": "2024-01-01 through 2025-12-31",
        "results": stress,
    }
    OUTPUT.write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    observed = stress["observed_bbo"]
    compact = {
        "trades": observed.get("trades"),
        "trades_per_week": observed.get("trades_per_week"),
        "net_pnl_usd": observed.get("net_pnl_usd"),
        "profit_factor": observed.get("profit_factor"),
        "cash_account": observed.get("cash_account"),
        "year_pnl_usd": observed.get("year_pnl_usd"),
        "direction_pnl_usd": observed.get("direction_pnl_usd"),
        "one_extra_cent_each_fill": stress["one_extra_cent_each_fill"].get(
            "net_pnl_usd"
        ),
        "five_additional_minutes_delay": stress[
            "five_additional_minutes_delay"
        ].get("net_pnl_usd"),
        "consolidated_bbo": stress["consolidated_bbo"].get("net_pnl_usd"),
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
