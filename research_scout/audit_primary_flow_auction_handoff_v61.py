"""Returns-blind audit of a primary-market-to-opening-auction handoff state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FLOW_AUDIT = (
    ROOT / "research_scout" / "proshares_primary_market_flow_audit_v60.json"
)
AUCTION_STATES = ROOT / "research_scout" / "spy_auction_imbalance_states_v34.json"
AUCTION_VALIDATION = (
    ROOT
    / "external_artifacts"
    / "databento_cash_etf_budget_v1"
    / "validation_report.json"
)
OUTPUT = ROOT / "research_scout" / "primary_flow_auction_handoff_audit_v61.json"
REPORT = (
    ROOT / "research_scout" / "PRIMARY_FLOW_AUCTION_HANDOFF_AUDIT_V61.md"
)
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")


def count_by_year(frame: pd.DataFrame) -> dict[str, int]:
    return {
        str(year): int((frame["session_date"].dt.year == year).sum())
        for year in (2021, 2022, 2023)
    }


def render(payload: dict[str, Any]) -> str:
    item = payload["development_2021_2023"]
    failures = [
        name for name, passed in payload["gates"].items() if not passed
    ]
    lines = [
        "# Primary-Flow / Opening-Auction Handoff Audit v61",
        "",
        "## Verdict",
        "",
        (
            "**Returns-blind construction gates passed. A formal critique and "
            "preregistration may be written; P&L remains unopened.**"
            if payload["gate_passed"]
            else "**Rejected returns-blind before P&L.**"
        ),
        "",
        "## Frozen construction",
        "",
        "- State 1: prior-session split-adjusted UPRO minus SPXU creation flow.",
        "- State 2: latest eligible SPY Arca opening-auction message strictly "
        "before 09:29 ET.",
        "- Candidate: act only when the two directions agree; use no magnitude "
        "threshold.",
        "",
        "## Development reachability",
        "",
        f"- Joint eligible sessions: {item['joint_eligible_sessions']}",
        (
            f"- Aligned candidate sessions: {item['aligned_sessions']} "
            f"({item['signals_per_week']:.3f}/week)"
        ),
        (
            f"- UPRO / SPXU actions: {item['upro_actions']} / "
            f"{item['spxu_actions']}"
        ),
        (
            "- Signals by year: "
            + ", ".join(
                f"{year}={count}" for year, count in item["signals_by_year"].items()
            )
        ),
        "",
        "## Distinctness",
        "",
        (
            "- Exact-action agreement including cash with flow-only: "
            f"{payload['distinctness']['flow_only_action_agreement']:.3%}"
        ),
        (
            "- Exact-action agreement including cash with auction-only: "
            f"{payload['distinctness']['auction_only_action_agreement']:.3%}"
        ),
        (
            "- Exact-action agreement including cash with failed v34 buy-only: "
            f"{payload['distinctness']['v34_buy_only_action_agreement']:.3%}"
        ),
        "",
        "## Gates",
        "",
    ]
    for name, passed in payload["gates"].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    lines.extend(
        [
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            "No target return, strategy P&L, or 2024-2025 outcome was read.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    flow_payload = json.loads(FLOW_AUDIT.read_text(encoding="utf-8"))
    auction_payload = json.loads(AUCTION_STATES.read_text(encoding="utf-8"))
    validation = json.loads(AUCTION_VALIDATION.read_text(encoding="utf-8"))

    flow = pd.DataFrame(flow_payload["paired_directional_flow"]["states"])
    flow["session_date"] = pd.to_datetime(flow["available_session"]).dt.normalize()
    flow = flow[flow["session_date"].between(START, END)].copy()
    flow["flow_action"] = flow["direction"].map({"B": "UPRO", "A": "SPXU"})

    auction = pd.DataFrame(auction_payload["states"])
    auction["session_date"] = pd.to_datetime(auction["session_date"]).dt.normalize()
    auction = auction[auction["session_date"].between(START, END)].copy()
    auction["auction_action"] = auction["side"].map({"B": "UPRO", "A": "SPXU"})

    joint = flow.merge(
        auction[
            [
                "session_date",
                "ts_event",
                "side",
                "ref_price",
                "ind_match_price",
                "paired_qty",
                "total_imbalance_qty",
                "auction_action",
            ]
        ],
        on="session_date",
        how="inner",
        validate="one_to_one",
    )
    joint["aligned"] = joint["flow_action"] == joint["auction_action"]
    joint["candidate_action"] = joint["flow_action"].where(joint["aligned"], "CASH")
    joint["v34_buy_only_action"] = joint["auction_action"].where(
        joint["auction_action"] == "UPRO", "CASH"
    )
    aligned = joint[joint["aligned"]].copy()

    expected_sessions = int(flow_payload["expected_sessions"])
    development = {
        "joint_eligible_sessions": len(joint),
        "joint_coverage": len(joint) / expected_sessions,
        "aligned_sessions": len(aligned),
        "signals_per_week": len(aligned) / (expected_sessions / 5.0),
        "upro_actions": int((aligned["candidate_action"] == "UPRO").sum()),
        "spxu_actions": int((aligned["candidate_action"] == "SPXU").sum()),
        "signals_by_year": count_by_year(aligned),
        "joint_sessions_by_year": count_by_year(joint),
        "selection_share": len(aligned) / len(joint),
    }
    distinctness = {
        "flow_only_action_agreement": float(
            (joint["candidate_action"] == joint["flow_action"]).mean()
        ),
        "auction_only_action_agreement": float(
            (joint["candidate_action"] == joint["auction_action"]).mean()
        ),
        "v34_buy_only_action_agreement": float(
            (joint["candidate_action"] == joint["v34_buy_only_action"]).mean()
        ),
    }
    auction_source = next(
        item
        for item in validation["files"]
        if item.get("schema") == "imbalance"
    )
    gates = {
        "underlying_flow_audit_passed": bool(flow_payload["admission_passed"]),
        "auction_source_has_clean_eof_and_hash": bool(
            auction_source["clean_eof"] and auction_source["sha256"]
        ),
        "joint_coverage_at_least_95_percent": bool(
            development["joint_coverage"] >= 0.95
        ),
        "candidate_frequency_at_least_2_per_week": bool(
            development["signals_per_week"] >= 2.0
        ),
        "at_least_90_signals_each_year": bool(
            min(development["signals_by_year"].values()) >= 90
        ),
        "both_sleeves_and_minority_at_least_25_percent": bool(
            min(development["upro_actions"], development["spxu_actions"])
            / development["aligned_sessions"]
            >= 0.25
        ),
        "selection_share_between_35_and_65_percent": bool(
            0.35 <= development["selection_share"] <= 0.65
        ),
        "distinct_from_flow_only_below_80_percent_action_agreement": bool(
            distinctness["flow_only_action_agreement"] < 0.80
        ),
        "distinct_from_auction_only_below_80_percent_action_agreement": bool(
            distinctness["auction_only_action_agreement"] < 0.80
        ),
        "distinct_from_failed_v34_below_80_percent_action_agreement": bool(
            distinctness["v34_buy_only_action_agreement"] < 0.80
        ),
        "flow_delayed_and_auction_timestamp_strictly_before_09_29": bool(
            pd.to_datetime(joint["source_date"]).lt(joint["session_date"]).all()
            and pd.to_datetime(joint["ts_event"], utc=True).dt.tz_convert(
                "America/New_York"
            ).dt.time.lt(pd.Timestamp("09:29:00").time()).all()
        ),
        "no_returns_pnl_or_recent_year_outcomes_read": True,
    }
    payload = {
        "status": "returns_blind_cross_data_construction_audit",
        "sources": {
            "proshares_flow_audit": str(FLOW_AUDIT.relative_to(ROOT)),
            "spy_auction_states": str(AUCTION_STATES.relative_to(ROOT)),
            "auction_source": auction_source["path"],
            "auction_source_sha256": auction_source["sha256"],
            "new_databento_calls_or_purchases": False,
        },
        "rule": {
            "flow": "prior-session UPRO creation dollars minus SPXU creation dollars",
            "flow_delay": "one US trading session",
            "auction": auction_payload["decision_cutoff"],
            "candidate": "act in the common direction only; disagreement is cash",
            "magnitude_threshold": None,
        },
        "development_2021_2023": development,
        "distinctness": distinctness,
        "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": (
            "allow_formal_critique_and_preregistration_only"
            if all(gates.values())
            else "reject_before_pnl"
        ),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
