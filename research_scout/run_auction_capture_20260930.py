"""Freeze and run a corrected capture-order execution proxy for the same signals."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime

import databento as db
import numpy as np
import pandas as pd

from research.auction_capture_proxy import SCENARIOS, extract_envelopes, replay_day
from research.auction_hft_event import RULES
from research.crypto_symbol_cache import digest
from research.precise_ledger import ledger_frame
from research_scout.run_auction_hft_20260930 import MANIFEST, ROOT
from research_scout.run_auction_hft_20260930 import OUT as PREVIOUS

OUT = ROOT / "research_scout/auction_capture_20260930"


def process_day(source):
    path = ROOT / source["path"]
    assert digest(path) == source["sha256"]
    raw = db.DBNStore.from_file(str(path)).to_df().reset_index()
    envelopes, audit = extract_envelopes(raw, source["date"])
    cache = OUT / "envelopes" / f"{source['date']}.parquet"
    envelopes.to_parquet(cache, index=False)
    return {"date": source["date"], "source_path": source["path"], "source_sha256": source["sha256"],
            "cache_sha256": digest(cache), "raw_rows": len(raw), "envelope_rows": len(envelopes), "symbols": audit}


def summarize(frame):
    complete = bool(frame.complete.all())
    lower = frame.pnl_lower.fillna(0).to_numpy(float)
    upper = frame.pnl_upper.fillna(0).to_numpy(float)
    return {"complete_under_model": complete, "net_lower": float(lower.sum()) if complete else None,
            "net_upper": float(upper.sum()) if complete else None,
            "resolved_subtotal_lower": float(lower.sum()), "resolved_subtotal_upper": float(upper.sum()),
            "known_fill_dates": int(frame.status.eq("bounded_fill").sum()),
            "fill_or_reject_dates": int(frame.status.eq("bounded_fill_or_reject").sum()),
            "without_best_five_lower": float(lower.sum() - np.sort(lower)[-5:].sum()) if complete else None,
            "dates": len(frame), "outcomes": frame.status.value_counts().to_dict(),
            "unresolved_dates": frame.loc[~frame.complete, "date"].tolist()}


def main():
    (OUT / "envelopes").mkdir(parents=True, exist_ok=True)
    spec_path = OUT / "specification.json"
    if spec_path.exists():
        raise FileExistsError("Capture-order revision already frozen")
    previous = json.loads((PREVIOUS / "specification.json").read_text())
    days = previous["dates"]
    manifest = json.loads(MANIFEST.read_text())
    sources = [s for s in manifest["results"] if s["date"] in set(days)]
    code = ["research/auction_capture_proxy.py", "research/auction_hft_event.py", "research/precise_ledger.py",
            "research_scout/run_auction_capture_20260930.py"]
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(), "configurations": 8, "new_hypotheses": 0,
        "dates": days, "rules": RULES, "holds_seconds": [15, 30], "scenarios": SCENARIOS,
        "previous_spec_sha256": digest(PREVIOUS / "specification.json"),
        "auction_inputs_sha256": digest(PREVIOUS / "auction_inputs.parquet"),
        "source_manifest_sha256": digest(MANIFEST),
        "unchanged": "All signals, decision times, signal freshness, causal cost gate, selected dates, fixed intended sizing, FOK collars, fees and ACK-based holding periods remain identical to the original 8 configurations. All source periods historically exposed. No 2026 quote outcomes.",
        "correction": "Preserve aggregate BBO receive order. Do not sort aggregate snapshots by component exchange timestamp or quarantine ordinary component clock reversals. An unchanged valid standing quote does not expire solely because no update occurred; last bad/missing/crossed state remains unusable.",
        "model": "At each nominal arrival collect the standing capture-ordered state before t-epsilon and every update through t+epsilon; epsilon=1ms baseline, 100ms stress. This is quote-clock alignment uncertainty, not a change to the nominal order/ACK schedule. A complete data-file boundary and valid states throughout are required. The extrema are bounds only within this observed-state proxy, not guaranteed physical venue execution bounds.",
        "execution_branches": "Every observed entry state above the causal FOK collar permits rejection; states at/below it with sufficient L1 size permit a full fill. Keep BOTH branches, including zero when possible, even if it makes the P&L interval worse. Insufficient L1 size at/below the collar is unresolved, since deeper within-limit liquidity is unknown. Exit requires adequate displayed bid size and valid state throughout its envelope; otherwise retain possible inventory. No outcome-based dropping or future resizing.",
        "cash": "Lower bound uses maximum admissible entry ask and minimum exit bid; upper bound uses their opposites; all fees/adverse allowances charged. Include rejection zero if possible. Daily independent $10000 capital reset means intervals can be added across dates without a capital/path interaction.",
        "limitations": "Anonymized EQUS.MINI BBO lacks routing identities and a complete physical matching-engine view. These are conditional discovery scenarios, not actual fills. Passing still requires venue-resolved or forward executable evidence. A chosen timing envelope is not a guaranteed bound on data/execution latency.",
        "progression": "All 2025 scenarios complete under the model with positive LOWER net; base >=50 mandatory fills and positive lower after best five dates removed; 2023-24 base complete with positive lower. Only then inspect later outcomes. No candidate implies no automatic follow-up tuning of its threshold or horizon.",
        "multiplicity": "108 configurations / 148 implementation versions, including this 8-rule correction. Stress scenarios and corrected replays are dependent, not independent confirmations. Repository-wide historical selection is additional.",
        "primary_documentation": ["https://databento.com/docs/standards-and-conventions/common-fields-enums-types",
                                  "https://databento.com/docs/schemas-and-data-formats/mbp-1",
                                  "https://databento.com/docs/venues-and-datasets/equs-mini"],
        "code_sha256": {name: digest(ROOT / name) for name in code},
    }
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Frozen capture-order proxy: {len(days)} sessions, unchanged 8 signals, 5 execution stresses", flush=True)
    audits = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(process_day, s) for s in sources]):
            audits.append(job.result())
            if len(audits) % 50 == 0 or len(audits) == len(sources):
                print(f"Envelope extraction {len(audits)}/{len(sources)}", flush=True)
    auction = pd.read_parquet(PREVIOUS / "auction_inputs.parquet")
    state = {(r["date"], r["label"]): r for r in auction.to_dict("records")}
    records = {f"{rule}_{hold}s": {name: [] for name in SCENARIOS} for rule in RULES for hold in (15, 30)}
    for number, day in enumerate(days, 1):
        signals = pd.read_parquet(PREVIOUS / "panels" / f"{day}.parquet")
        envelopes = pd.read_parquet(OUT / "envelopes" / f"{day}.parquet")
        for rule in RULES:
            for hold in (15, 30):
                for name, scenario in SCENARIOS.items():
                    records[f"{rule}_{hold}s"][name].append(replay_day(day, signals, envelopes,
                        state[day, "early"], state[day, "late"], rule, hold, scenario))
        if number % 100 == 0:
            print(f"Replayed {number}/{len(days)} dates", flush=True)
    results, advance = {}, []
    decision_keys = ["date", "symbol", "underlying_prediction", "projected_return", "quantity", "signal_ask", "signal_ask_qty", "expected_net"]
    for name, scenarios in records.items():
        summaries = {}
        old = pd.read_parquet(PREVIOUS / "precise_ledgers" / f"{name}_base_attempts.parquet")
        for scenario, rows in scenarios.items():
            frame = ledger_frame(rows)
            pd.testing.assert_frame_equal(frame[decision_keys], old[decision_keys])
            frame.to_parquet(OUT / f"{name}_{scenario}_attempts.parquet", index=False)
            summaries[scenario] = {"all": summarize(frame),
                "development_2023_2024": summarize(frame.loc[frame.date.lt("2025-01-01")]),
                "selection_2025": summarize(frame.loc[frame.date.ge("2025-01-01")])}
        base, development = summaries["base"]["selection_2025"], summaries["base"]["development_2023_2024"]
        passed = (all(s["selection_2025"]["complete_under_model"] and s["selection_2025"]["net_lower"] > 0 for s in summaries.values())
                  and development["complete_under_model"] and development["net_lower"] > 0
                  and base["known_fill_dates"] >= 50 and base["without_best_five_lower"] > 0)
        results[name] = {"scenarios": summaries, "needs_additional_evidence": passed}
        if passed:
            advance.append(name)
        print(f"{name}: 2025 lower={base['net_lower']}, upper={base['net_upper']}, "
              f"resolved subtotal=[{base['resolved_subtotal_lower']:.2f},{base['resolved_subtotal_upper']:.2f}], advance={passed}", flush=True)
    assert all(digest(ROOT / name) == sha for name, sha in spec["code_sha256"].items())
    (OUT / "results.json").write_text(json.dumps({"results": results, "source_audits": audits,
        "decisions_identical_to_original": True, "candidates_for_additional_evidence": advance,
        "reliable_edge_established": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
