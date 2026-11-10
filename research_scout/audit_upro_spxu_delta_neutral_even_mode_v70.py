"""Returns-blind audit of UPRO/SPXU delta-neutral even mode v70."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_proshares_leverage_triangle_convergence_v69 as v69
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay
from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "upro_spxu_delta_neutral_even_mode_returns_blind_audit_v70.json"
REPORT = ROOT / "research_scout" / "UPRO_SPXU_DELTA_NEUTRAL_EVEN_MODE_AUDIT_V70.md"
CLOCKS = ("09:31", "09:32", "09:33")
ENTRY = "09:33"
EXIT = "10:30"


def build(
    nav: dict[pd.Timestamp, dict[str, Any]],
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    clock: str,
) -> dict[pd.Timestamp, dict[str, Any]]:
    out = {}
    for day, source in sorted(nav.items()):
        if day in excluded or day not in sessions:
            continue
        returns = {}
        valid = True
        for symbol in ("UPRO", "SPXU"):
            frame = sessions[day].get(symbol)
            mid = v69.quote_midpoint(frame, day, clock) if frame is not None else None
            if mid is None:
                valid = False
                break
            value = mid / float(source["nav"][symbol]) - 1.0
            if abs(value) > 0.25:
                valid = False
                break
            returns[symbol] = value
        if not valid:
            continue
        basis = returns["UPRO"] + returns["SPXU"]
        direction = v69.sign(basis)
        out[day] = {
            "session_date": day.strftime("%Y-%m-%d"),
            "source_dates": {
                s: source["source_dates"][s].strftime("%Y-%m-%d")
                for s in ("UPRO", "SPXU")
            },
            "basis": basis,
            "basis_sign": direction,
            "action": "SHORT_BOTH" if direction > 0 else "LONG_BOTH" if direction < 0 else "CASH",
        }
    return out


def agreement(a, b):
    days = sorted(set(a).intersection(b))
    return {
        "joint": len(days),
        "identical_action": sum(a[d]["action"] == b[d]["action"] for d in days) / max(len(days), 1),
    }


def coverage(states, sessions, excluded):
    active = [d for d, r in states.items() if r["action"] != "CASH" and d not in excluded]
    valid = 0
    for day in active:
        ok = True
        for symbol in ("UPRO", "SPXU"):
            frame = sessions.get(day, {}).get(symbol)
            if frame is None:
                ok = False
                break
            entry = base.exact_row(frame, v69.clock_stamp(day, ENTRY, frame.index.tz))
            exit_row = base.exact_row(frame, v69.clock_stamp(day, EXIT, frame.index.tz))
            ok &= base.valid_quote(entry) and base.valid_quote(exit_row)
        valid += int(ok)
    return {"active": len(active), "valid": valid, "coverage": valid / max(len(active), 1)}


def render(p):
    d = p["development_2021_2023"]
    failures = [k for k, v in p["gates"].items() if not v]
    return "\n".join([
        "# UPRO/SPXU Delta-Neutral Even-Mode Audit v70", "",
        "**All returns-blind gates passed; frozen development P&L authorized.**"
        if p["gate_passed"] else "**Rejected returns-blind before P&L.**", "",
        f"- Eligible: {d['eligible_sessions']} ({d['coverage']:.3%})",
        f"- Pair trades: {d['pair_trades']} ({d['trades_per_week']:.3f}/week)",
        f"- Long both / short both: {d['long_both']} / {d['short_both']}",
        f"- 09:31 / 09:33 agreement: {p['neighbors']['09:31']['identical_action']:.3%} / {p['neighbors']['09:33']['identical_action']:.3%}",
        f"- Independent agreement: {p['independent']['identical_action']:.3%}",
        f"- Primary / independent quote coverage: {p['quotes']['primary']['coverage']:.3%} / {p['quotes']['independent']['coverage']:.3%}", "",
        "Failed gates: " + (", ".join(failures) if failures else "none"), "",
        "No post-entry return, P&L, or recent-year outcome was calculated.", ""
    ])


def main():
    expected, nav = v69.load_nav_states()
    arca = relay.sessions(relay.ARCA_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    states = {c: build(nav, arca, arca_excluded, c) for c in CLOCKS}
    primary = states["09:32"]
    equs = relay.sessions(relay.EQUS_PATH)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    independent_states = build(nav, equs, equs_excluded, "09:32")
    counts = Counter(r["action"] for r in primary.values())
    by_year = {str(y): sum(d.year == y and r["action"] != "CASH" for d, r in primary.items()) for y in (2021, 2022, 2023)}
    development = {
        "expected_sessions": len(expected),
        "eligible_sessions": len(primary),
        "coverage": len(primary) / len(expected),
        "pair_trades": counts["LONG_BOTH"] + counts["SHORT_BOTH"],
        "trades_per_week": (counts["LONG_BOTH"] + counts["SHORT_BOTH"]) / (len(expected) / 5),
        "long_both": counts["LONG_BOTH"],
        "short_both": counts["SHORT_BOTH"],
        "by_year": by_year,
    }
    neighbors = {c: agreement(primary, states[c]) for c in ("09:31", "09:33")}
    independent = agreement(primary, independent_states)
    quotes = {
        "primary": coverage(primary, arca, arca_excluded),
        "independent": coverage(independent_states, equs, equs_excluded),
    }
    causal = all(all(pd.Timestamp(x).normalize() < d for x in r["source_dates"].values()) for d, r in primary.items())
    gates = {
        "coverage_at_least_95_percent": development["coverage"] >= 0.95,
        "at_least_2_trades_per_week": development["trades_per_week"] >= 2,
        "at_least_200_each_year": min(by_year.values()) >= 200,
        "at_least_200_each_direction": min(counts["LONG_BOTH"], counts["SHORT_BOTH"]) >= 200,
        "09_31_agreement_at_least_85_percent": neighbors["09:31"]["identical_action"] >= 0.85,
        "09_33_agreement_at_least_85_percent": neighbors["09:33"]["identical_action"] >= 0.85,
        "independent_agreement_at_least_90_percent": independent["identical_action"] >= 0.90,
        "primary_quotes_at_least_95_percent": quotes["primary"]["coverage"] >= 0.95,
        "independent_quotes_at_least_90_percent": quotes["independent"]["coverage"] >= 0.90,
        "prior_nav_strictly_causal": causal,
        "no_post_entry_return_read": True,
    }
    payload = {
        "status": "returns_blind_v70_audit",
        "new_databento_calls_or_purchases": False,
        "development_2021_2023": development,
        "neighbors": neighbors,
        "independent": independent,
        "quotes": quotes,
        "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": "authorize_frozen_development_pnl_only" if all(gates.values()) else "reject_before_pnl",
        "states": [r for _, r in sorted(primary.items())],
        "independent_states_2023": [r for _, r in sorted(independent_states.items())],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k not in {"states", "independent_states_2023"}}, indent=2))


if __name__ == "__main__":
    main()
