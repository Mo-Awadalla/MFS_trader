"""Maintain the resumable research checkpoint without changing frozen evidence."""

import json
from datetime import UTC, datetime

from research_scout.prepare_bybit_funding_20261002 import OUT, ROOT


def main():
    path = ROOT/"research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    value = json.loads(path.read_text())
    manifest = json.loads((OUT/"all_states_manifest.json").read_text())
    value.update(status="active", reliable_edge_found=False, paused_at_user_request=False,
                 updated_at_utc=datetime.now(UTC).isoformat(), focused_tests_total=221,
                 bybit_funding_report=str(OUT/"REPORT.txt"),
                 bybit_funding_native_messages=1432850, bybit_funding_original_observations=8857,
                 bybit_funding_partial_rate_candidates=60,
                 bybit_funding_partial_pairs_above_fee_hurdle=2,
                 bybit_funding_partial_pairs_above_spread_and_size_hurdle=0,
                 bybit_funding_full_source_recovery_complete=manifest["complete"],
                 bybit_funding_source_files_recovered=len(manifest["files"]),
                 bybit_funding_rows_inspected=manifest["rows_inspected"],
                 bybit_funding_economic_implementations=0,
                 bybit_funding_selection_2025_opened=False,
                 bybit_funding_actual_execution_verified=False,
                 wide_tick_replay_engine_validation="19 focused execution tests and Ruff passed; independent raw-source queue, signal, clock, cash and aggregate audit passed.")
    if "pause_reason" in value:
        value["previous_pause_reason"] = value.pop("pause_reason")
    result_path = OUT/"all_states_screen_results.json"
    if result_path.exists():
        result = json.loads(result_path.read_text())
        value.update(bybit_funding_full_screen=result,
                     remaining_evidence_work="Full Bybit funding source recovery and same-rule screen complete. Inspect candidate lifecycle, native field provenance and spreads; independently audit the expanded screen before any edge claim. This remains source screening, not an economic replay.")
    else:
        value["remaining_evidence_work"] = "Finish full Bybit funding source recovery for the original 8,857 symbol/windows, then apply the already frozen all-state screen. Both provisional rate-gap candidates fail the spread budget. Unknown rates have not been treated as zero. Research resumed on explicit user request."
    if manifest["complete"]:
        value["active_research_jobs"] = []
        value["last_research_process"] = {"session_id": 43372, "source_manifest_complete": True}
    else:
        value["active_research_jobs"] = [{"session_id": 43372, "task": "Bounded full Bybit funding state recovery", "last_observed": "running"}]
    path.write_text(json.dumps(value, indent=2)+"\n")
    report = (
        "BYBIT-FIRST FUNDING HFT RESEARCH — IN PROGRESS\n\n"
        "No reliable edge established. Research only; no strategy P&L or actual fills have been established.\n"
        "Scope: stocks/ETFs/crypto remain authorized; this branch investigates crypto perpetual funding within a maximum 30-second inventory horizon. Conservative costs remain unchanged.\n\n"
        "The original Binance-first funding screen omitted Bybit-only extreme rates. This dependent extension freezes 24 first-of-month 2024 windows, at 08:00 and 16:00 UTC. Signals use captures strictly before settlement minus 10.25 seconds. The absolute Bybit funding-rate hurdle is 14bp; equal-unit paired payments must exceed 28bp before spreads.\n\n"
        "Native source: 24 complete windows, 1,432,850 native messages, 8,857 symbol/windows and 481 symbols. The short delta windows omitted 5,519 funding rates and all complete funding-time states. These missing fields are unknown, not zero.\n\n"
        "Partial recovery: 60 known large-rate observations from 52 complete symbol/date files. Sixteen usable pairs; AXLUSDT (2024-03-01 16:00 UTC) and STEEMUSDT (2024-05-01 08:00 UTC) exceed the fee-only hurdle. Both fail the full displayed-spread budget: -3.01865bp and -4.82767bp respectively, before settlement repricing. Both also fail the frozen displayed-size gate. These are hypothetical payment budgets, not P&L.\n\n"
        f"Full source recovery: {len(manifest['files'])}/12 files processed; {manifest['rows_inspected']:,} rows inspected; complete={manifest['complete']}. Full recovery retains every original symbol/window, verifies native/normalized field agreement and uses the unchanged thresholds.\n\n"
        "Validation: six native-field tests, three aggregate as-of tests and seven pairing/gating tests passed; Ruff passed. The independent audit of this funding extension is not complete. 2025 validation remains unopened.\n\n"
        "Artifacts: specification.json; source_manifest.json; native_states.parquet; pair_screen_results.json; quote_gate_results.json; all_states_recovery_plan.json; all_states_manifest.json; all_states_screen_implementation.json. Original partial results remain intact.\n"
    )
    if result_path.exists():
        report += "\nFULL-STATE SCREEN RESULTS\n"+json.dumps(result, indent=2)+"\n"
    (OUT/"REPORT.txt").write_text(report, encoding="utf-8")
    print(json.dumps({"updated": str(path), "source_complete": manifest["complete"]}), flush=True)


if __name__ == "__main__":
    main()
