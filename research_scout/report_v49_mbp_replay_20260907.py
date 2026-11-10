"""Render the V49 gate evidence without promoting a failed candidate to P&L."""
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research_scout/v49_mbp_replay_20260907'

def main():
    r=json.loads((OUT/'original_gate_result.json').read_text())
    x=json.loads((OUT/'extraction_summary.json').read_text())
    v=json.loads((OUT/'verification.json').read_text())
    d=json.loads((OUT/'development_stability_diagnostic.json').read_text())
    old=json.loads((ROOT/'external_artifacts/databento_cash_etf_mbp1_open_v55/validation_report.json').read_text())
    missing=[day for day in old['missing_dates'] if day<='2026-07-24']
    a=r['all_periods'];dev=r['development_2023_overlap'];ex=r['executable_development_2023_overlap'];s=r['stability']
    failed=[g for g,p in r['gates'].items() if not p]
    rows=[
      ('Development signals',str(dev['signals']),'>=80','at_least_80_development_feature_signals'),
      ('Development signals/week',f"{dev['signals_per_declared_week']:.3f}",'>=2','development_feature_frequency_at_least_two_per_week'),
      ('2026 observed signals',str(a['extension_2026_signals']),'>=20','at_least_20_signals_in_2026'),
      ('Development minority ETF share',f"{100*dev['minority_share']:.2f}%",'>=20%, both ETFs','both_actuators_and_minority_at_least_20pct'),
      ('All-delay entry/exit quote coverage',f"{100*a['execution_coverage']:.2f}%",'>=90%','execution_coverage_at_least_90pct'),
      ('Executable development signals/week',f"{ex['signals_per_declared_week']:.3f}",'>=2','executable_development_frequency_at_least_two_per_week'),
      ('Executable minority ETF share',f"{100*ex['minority_share']:.2f}%",'>=20%, both ETFs','executable_both_actuators_and_minority_at_least_20pct'),
      ('09:30:01 vs 09:30:05 action agreement',f"{s['adjacent_09_30_01']['identical_action_including_cash_pct']:.2f}%",'>=60%','adjacent_clock_identical_action_including_cash_at_least_60pct'),
      ('10 vs 20-session action agreement',f"{s['rolling_windows']['10']['identical_action_including_cash_pct']:.2f}%",'>=70%','rolling_10_identical_action_including_cash_at_least_70pct'),
      ('40 vs 20-session action agreement',f"{s['rolling_windows']['40']['identical_action_including_cash_pct']:.2f}%",'>=70%','rolling_40_identical_action_including_cash_at_least_70pct'),
      ('Signal selection share',f"{100*a['selection_share']:.2f}%",'20–80%','selection_share_between_20_and_80pct'),
      ('Entries after 09:31 boundary',str(r['timestamp_observability']['all_entries_after_09_31_signal_boundary']),'True','all_entries_after_signal_boundary'),
      ('Official statistics unique/positive',str(r['gates']['statistics_unique_and_positive']),'True','statistics_unique_and_positive')]
    lines=['# V49 full-quote signal audit — September 7, 2026 UTC','',
      '**Decision: '+('All original gates pass; costed testing is the next required stage.' if r['gate_passed'] else 'V49 fails its original signal-only admission gates. No P&L backtest was run.')+'**','',
      'The newer data repairs the earlier measurement shortage. This replay evaluates whether the resulting signal satisfies the original rules before looking at strategy profitability. A failed signal gate is not proof of negative returns; it means the candidate does not qualify for the next stage under its registered protocol.','',
      '## Evidence','',
      f"Decoded {x['files']:,} local MBP-1 files containing {x['source_rows']:,} source records; retained {x['quote_states']:,} targeted quote states. Observed files by year: {dict(Counter(row['date'][:4] for row in x['sessions']))}. No market-data download or account operation was needed.",'',
      f"The primary rule produces {a['signals']} signals from {a['synchronized_warm_sessions']} synchronized sessions after warm-up. Development has {dev['signals']} signals, side counts {dev['side_counts']} (B = UPRO, A = SPXU), and {ex['signals']} with complete execution quotes. The 2026 observed extension has {a['extension_2026_signals']} signals.",'',
      '| Original requirement | Observed | Threshold | Result |','|---|---:|---|---|']
    lines += [f"| {name} | {value} | {threshold} | {'PASS' if r['gates'][key] else '**FAIL**'} |" for name,value,threshold,key in rows]
    lines += ['', '## Stability interpretation','',
      'Action agreement uses the original denominator: days on which either compared rule trades. A trade-versus-cash disagreement counts as a mismatch; days on which both are cash are excluded. This prevents many inactive days from inflating agreement.','',
      f"In the separate 2023-only diagnostic, adjacent-clock agreement is {d['adjacent_clock']['identical_action_including_cash_pct']:.2f}%; rolling-10 and rolling-40 agreement are {d['rolling_10']['identical_action_including_cash_pct']:.2f}% and {d['rolling_40']['identical_action_including_cash_pct']:.2f}%. This diagnostic does not replace the original full-period gate.",'',
      f"Across the full observed sample, the two clocks agree on ETF direction on {s['adjacent_09_30_01']['direction_agreement_on_joint_pct']:.2f}% of days when both trade. That is distinct from deciding reliably whether to trade at all. Both metrics are retained rather than substituting the more favorable one.",'',
      '## Scope and safeguards','',
      '- Original signal generation, residual formula, 10/20/40-session baselines, timing boundaries, degraded-day exclusions and all 13 gates ran from the original module without edits. Its SHA-256 is unchanged.',
      '- The explicitly registered measurement amendment replaces trade-triggered TBBO with full MBP-1 updates. The first valid event at or after each target is selected, with the original 60-second search bound. This is a replay with a changed data source, not an exact replication of the old trade-event signal.',
      f"- {missing.__len__()} requested dates through the original July 24, 2026 boundary are absent locally. Missing sessions are not known cash decisions. Gates involving the full period apply to observed data; missing-session results are unknown. The observed sample is sufficient to report its measured failure or pass, not full-calendar completion.",
      f"- {x['nonpositive_size_states']} retained quote states have a nonpositive displayed size. These are counted as a separate quality diagnostic because the original signal filter uses prices. Complete quote evidence alone is not an assurance of fills, capacity, or fractional-share execution.",
      '- Historical periods have already been exposed in this research program. Neither 2024–2025 nor 2026 is represented as new prospective validation.',
      '- No thresholds, observation times, or selection conditions were repaired after seeing this result. No post-entry P&L, benchmark, return optimization or order was calculated or submitted.','',
      '## Verification and current position','',
      f"An independent reconstruction from saved quote states reproduced all {v['independently_reconstructed_signals']} primary actions and all three action-agreement statistics. Quote time bounds and positive non-crossed prices were checked; no verification errors were found.",'',
      ('The candidate now qualifies for a separately frozen economic evaluation, not deployment.' if r['gate_passed'] else 'V49 moves from data-blocked to rejected under its original signal-stability requirements on the available full-quote sample. Better quotes did not establish a stable trade decision. There is still no validated SPY-beating intraday strategy; further V49 tuning would constitute a new, exposed hypothesis.'),'',
      '## Reproduce','',
      'From the repository root, run `.venv/Scripts/python.exe -X utf8 -m research_scout.replay_v49_mbp_20260907`, then modules `research_scout.verify_v49_mbp_replay_20260907` and `research_scout.report_v49_mbp_replay_20260907`. The replay reuses the saved extraction cache. Original historical artifacts are not overwritten.','',
      'Evidence: `specification.json`, `original_gate_result.json`, `development_stability_diagnostic.json`, `extraction_summary.json`, `quote_cache/`, and `verification.json`.','']
    (OUT/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'gate_passed':r['gate_passed'],'failed_gates':failed,'report':str(OUT/'REPORT.md')},indent=2))

if __name__=='__main__':main()
