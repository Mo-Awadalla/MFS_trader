# V49 full-quote signal audit — September 7, 2026 UTC

**Decision: V49 fails its original signal-only admission gates. No P&L backtest was run.**

The newer data repairs the earlier measurement shortage. This replay evaluates whether the resulting signal satisfies the original rules before looking at strategy profitability. A failed signal gate is not proof of negative returns; it means the candidate does not qualify for the next stage under its registered protocol.

## Evidence

Decoded 806 local MBP-1 files containing 223,597,341 source records; retained 29,016 targeted quote states. Observed files by year: {'2023': 192, '2024': 252, '2025': 250, '2026': 112}. No market-data download or account operation was needed.

The primary rule produces 461 signals from 758 synchronized sessions after warm-up. Development has 84 signals, side counts {'B': 39, 'A': 45} (B = UPRO, A = SPXU), and 84 with complete execution quotes. The 2026 observed extension has 69 signals.

| Original requirement | Observed | Threshold | Result |
|---|---:|---|---|
| Development signals | 84 | >=80 | PASS |
| Development signals/week | 2.108 | >=2 | PASS |
| 2026 observed signals | 69 | >=20 | PASS |
| Development minority ETF share | 46.43% | >=20%, both ETFs | PASS |
| All-delay entry/exit quote coverage | 100.00% | >=90% | PASS |
| Executable development signals/week | 2.108 | >=2 | PASS |
| Executable minority ETF share | 46.43% | >=20%, both ETFs | PASS |
| 09:30:01 vs 09:30:05 action agreement | 49.17% | >=60% | **FAIL** |
| 10 vs 20-session action agreement | 75.88% | >=70% | PASS |
| 40 vs 20-session action agreement | 79.45% | >=70% | PASS |
| Signal selection share | 60.82% | 20–80% | PASS |
| Entries after 09:31 boundary | True | True | PASS |
| Official statistics unique/positive | True | True | PASS |

## Stability interpretation

Action agreement uses the original denominator: days on which either compared rule trades. A trade-versus-cash disagreement counts as a mismatch; days on which both are cash are excluded. This prevents many inactive days from inflating agreement.

In the separate 2023-only diagnostic, adjacent-clock agreement is 48.25%; rolling-10 and rolling-40 agreement are 78.95% and 75.56%. This diagnostic does not replace the original full-period gate.

Across the full observed sample, the two clocks agree on ETF direction on 88.06% of days when both trade. That is distinct from deciding reliably whether to trade at all. Both metrics are retained rather than substituting the more favorable one.

## Scope and safeguards

- Original signal generation, residual formula, 10/20/40-session baselines, timing boundaries, degraded-day exclusions and all 13 gates ran from the original module without edits. Its SHA-256 is unchanged.
- The explicitly registered measurement amendment replaces trade-triggered TBBO with full MBP-1 updates. The first valid event at or after each target is selected, with the original 60-second search bound. This is a replay with a changed data source, not an exact replication of the old trade-event signal.
- 28 requested dates through the original July 24, 2026 boundary are absent locally. Missing sessions are not known cash decisions. Gates involving the full period apply to observed data; missing-session results are unknown. The observed sample is sufficient to report its measured failure or pass, not full-calendar completion.
- 0 retained quote states have a nonpositive displayed size. These are counted as a separate quality diagnostic because the original signal filter uses prices. Complete quote evidence alone is not an assurance of fills, capacity, or fractional-share execution.
- Historical periods have already been exposed in this research program. Neither 2024–2025 nor 2026 is represented as new prospective validation.
- No thresholds, observation times, or selection conditions were repaired after seeing this result. No post-entry P&L, benchmark, return optimization or order was calculated or submitted.

## Verification and current position

An independent reconstruction from saved quote states reproduced all 461 primary actions and all three action-agreement statistics. Quote time bounds and positive non-crossed prices were checked; no verification errors were found.

V49 moves from data-blocked to rejected under its original signal-stability requirements on the available full-quote sample. Better quotes did not establish a stable trade decision. There is still no validated SPY-beating intraday strategy; further V49 tuning would constitute a new, exposed hypothesis.

## Reproduce

From the repository root, run `.venv/Scripts/python.exe -X utf8 -m research_scout.replay_v49_mbp_20260907`, then modules `research_scout.verify_v49_mbp_replay_20260907` and `research_scout.report_v49_mbp_replay_20260907`. The replay reuses the saved extraction cache. Original historical artifacts are not overwritten.

Evidence: `specification.json`, `original_gate_result.json`, `development_stability_diagnostic.json`, `extraction_summary.json`, `quote_cache/`, and `verification.json`.
