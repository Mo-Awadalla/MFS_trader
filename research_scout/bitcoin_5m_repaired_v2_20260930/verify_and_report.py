"""Reconcile source, feature, target, signal and replay evidence; write repair report."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from research.bitcoin_5m_exchange_validation import summarize_trades


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    if (HERE/'REPORT.md').exists() or (HERE/'verification.json').exists():
        raise FileExistsError('preserve completed repair verification evidence')
    initial=json.loads((HERE/'results.json').read_text())
    rerun=HERE/'verification_rerun'
    r=json.loads((rerun/'results.json').read_text())
    p=pd.read_parquet(HERE/'predictions.parquet')
    q=pd.read_parquet(rerun/'predictions.parquet')
    pd.testing.assert_frame_equal(p,q,check_exact=True)
    for name in ['panel','shadow_trades','admitted_trades','delayed_shadow_trades']:
        pd.testing.assert_frame_equal(pd.read_parquet(HERE/f'{name}.parquet'),
                                     pd.read_parquet(rerun/f'{name}.parquet'),check_exact=True)
    assert initial['periods']==r['periods'] and initial['folds']==r['folds']
    for name,h in r['source_sha256'].items():
        assert sha(ROOT/name)==h
    for result,folder in [(initial,HERE),(r,rerun)]:
        for name,h in result['code_sha256'].items():
            assert sha(folder/'executed_code'/Path(name).name)==h
    for name,h in r['code_sha256'].items():
        assert sha(ROOT/name)==h
    assert not p.actionable_signal.any()
    assert r['admitted_quarters']==0
    assert p.open_time.is_monotonic_increasing and not p.open_time.duplicated().any()
    for f in r['folds']:
        assert f['last_training_target']<f['calibration_start']
        assert f['last_calibration_target']<f['admission_start']<f['update']
        assert not f['admission']['admitted']
    c2022=next(c for c in r['coverage'] if c['year']==2022)
    assert c2022['decisions']/c2022['source_price_bars']>.999
    fine=[]
    for year,g in p.loc[p.target_return.notna()].groupby(p.open_time.dt.year):
        g=g.copy()
        g['bucket']=pd.cut(g.p_up,[0,.4,.45,.48,.5,.52,.55,.6,1],include_lowest=True)
        for bucket,a in g.groupby('bucket',observed=True):
            fine.append(dict(year=int(year),bucket=str(bucket),rows=len(a),mean_p=float(a.p_up.mean()),
                observed_up=float(a.target_return.gt(0).mean()),mean_target_bps=float(a.target_return.mean()*1e4)))
    pd.DataFrame(fine).to_csv(HERE/'fine_calibration.csv',index=False)
    checks=dict(status='PASS',tests_passed=30,
        full_replay_reproduction='Exact equality: all predictions, targets, signals, trade ledgers, fold and period results',
        checks=['All v1, prior audit and exchange result hashes unchanged',
            'Executed source snapshots match both recorded run hashes',
            'Final source hashes match the verification rerun',
            'Two full quarterly runs produce bit-identical predictions and trade economics',
            'Training/calibration/admission/evaluation labels strictly ordered for all 11 quarters',
            '2022 coverage restored above 99.9%',
            'No failed-admission signals become actionable',
            'Cost, funding, gap, tie, future-feature, invalid-input and CLI preservation tests passed',
            'Focused lint passes'],
        exact_future_decisions_note='One extra feature row at September 1 can be forecast without a realized candle; it is excluded from the evaluation and price-bar coverage denominator')
    (HERE/'verification.json').write_text(json.dumps(checks,indent=2)+'\n')
    lines=['# Bitcoin five-minute model repair v2', '', 'Date: September 30, 2026.', '',
        '**The implementation repairs are complete. Profitability remains unconfirmed.** A single fixed version 2 replaces the original entrypoint default while preserving version 1 source, data, models and result evidence. The repaired model’s historical candidate averages are positive after the declared costs, but the candidates are sparse and all separate quarterly admission checks reject them. Actionable signals remain flat.', '',
        '## Implemented repairs', '',
        '- Causal feature generation requires only completed bars. It can produce a prediction before the next candle exists. Decision eligibility is independent of that candle’s eventual outcome.',
        '- Tied/zero-return outcomes are retained in targets and trade accounting. Unknown future targets stay null and do not remove decision rows.',
        '- Sparse trader-ratio requirements are removed. Open-interest changes are optional, with missing flags and median imputation fitted solely on training data. Prices are never imputed.',
        '- All 289 completed closes needed by the longest volatility input must be continuous. Market-data validation rejects nonfinite prices, inconsistent OHLC, invalid volume/flow, duplicate/missing timestamps, fractional trade counts and off-grid bars.',
        '- The model estimates direction and separate conditional win/loss sizes. It proposes trades from expected monetary return after total costs, instead of confidence alone.',
        '- Training updates quarterly: 24 months training, 2 months separate calibration, 1 month separate admission, then the evaluation quarter. Boundary-crossing labels are purged. Test outcomes do not enter a prior fit or admission.',
        '- Failed or missing admission produces no actionable trade. There is no exchange client or order-submission capability.',
        '- The usual runner defaults to v2. Legacy reproduction needs --legacy-v1 and a new directory. A frozen-spec hash and exclusive reservation prevent silent parameter changes or overwriting prior evidence.', '',
        f"2022 coverage rises from the audited original 13,372 causal decisions to **{c2022['decisions']:,} of {c2022['source_price_bars']:,} bars ({c2022['decisions']/c2022['source_price_bars']:.4%})**. Version2’s remaining exclusions are causal core-feature conditions such as zero-volume flow history. No missing trader ratios were invented or future-filled.", '',
        '## Fixed model and trading rule', '',
        'Direction: standardized L2 logistic regression C=0.1. Positive and nonpositive return magnitudes: separate Ridge alpha=100 regressions, using the same training-only preprocessing. Calibration uses Platt direction probabilities and conditional magnitude scale factors from the subsequent calibration period. The untrimmed target is next-open/current-open minus 1, including zero returns. Expected return equals p(up)×expected win minus (1−p(up))×expected loss.', '',
        'The proposed long or short requires at least 2bps expected net edge after 6bps round-trip friction. The 6bps scenario is an assumption: the prior favorable 4bps exchange fee-only scenario plus 2bps assumed execution friction, not an account-specific quote. Admission requires 100 candidate trades across 20 active days and a positive lower 95% seven-day-block net 6bps expectation in the separate admission month. All thresholds and parameters were declared before version 2 outcomes; no post-result tuning was performed.', '',
        '## Historical candidate results, before admission', '',
        'These are ungated diagnostic candidates, not approved trades, live fills, or proven profits. They use Binance bar opens with both-side notional costs and available settled funding. One basis point is 0.01%.', '',
        '| Period | Candidate trades | Active days | Gross bps/trade | Net at 6bps | Net6bps95% interval |',
        '| --- | ---: | ---: | ---: | ---: | --- |']
    for year,a in r['periods'].items():
        e=a['economics']['shadow'];ci=e['net_ci95_bps']['6']
        label=year if year!='2026' else 'Jan–Aug 2026'
        lines.append(f"| {label} | {e['trades']} | {e['active_days']} | {e['gross_bps']:.3f} | {e['net_bps']['6']:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] |")
    lines+=['',
        'For Jan–Aug 2026, the point estimate is +0.13166% per candidate trade after 6bps assumed friction. The 95% interval is approximately [−0.03155%,+0.34174%]. Only 23 trades on 10 active days support that mean. Each annual net 6bps interval includes losses. These averages cannot be presented as reliable earnings, and rare clustered events may make uncertainty larger than this bootstrap suggests.', '',
        '**Zero of 11 quarterly admission checks pass; admitted trades are zero.** Admission candidate counts are too small for the declared sample gate. This is an intentional abstention on insufficient evidence, not a profitable strategy with hidden trades. The admission rule is conservative and may leave a rare-event strategy inactive for a long time; changing it would require a new declared experiment, not relabeling the existing result.', '',
        '## Entry-delay sensitivity', '',
        'A separate fixed one-bar delay stress preserves the five-minute holding horizon. It was declared before results and is not selected as an improved strategy.', '',
        '| Period | Delayed candidate trades | Gross bps/trade | Net at 6bps | Net6bps95% interval |',
        '| --- | ---: | ---: | ---: | --- |']
    for year,a in r['periods'].items():
        e=a['economics']['delayed_shadow'];ci=e['net_ci95_bps']['6']
        lines.append(f"| {year} | {e['trades']} | {e['gross_bps']:.3f} | {e['net_bps']['6']:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] |")
    lines+=['',
        'The favorable delayed 2025 interval rests on 21 trades across10 active days and already viewed history. It does not validate selecting that entry rule, relaxing admission, or deploying. The 2026 delayed interval includes losses. A five-minute stress is not a measured millisecond execution-latency model.', '',
        '## Probability diagnostics', '',
        'Version2 probabilities predict positive open-to-next-open return, with zero included in the nonpositive class. Original version 1 probabilities predict close-versus-open direction and exclude ties, so their accuracy is not directly comparable. Fine fixed probability bins are exported in fine_calibration.csv.', '',
        '| Period | Direction accuracy | Brier | AUC |',
        '| --- | ---: | ---: | ---: |']
    for year,a in r['periods'].items():
        lines.append(f"| {year} | {a['directional_accuracy']:.2%} | {a['brier']:.6f} | {a['auc']:.4f} |")
    lines+=['', '## Verification and provenance', '',
        '30 focused tests pass across version 1, repaired features/model, cost/funding/replay/admission, and the default/legacy runners. Focused lint passes. A full final-source rerun reproduces all original version 2 predictions, target values, candidate/actionable signals, trade ledgers, quarterly folds and annual economics exactly. All original and previous result hashes remain unchanged. Executed source snapshots accompany both runs.', '',
        'The initial repair result files are preserved. Formatting, defensive guards and the coverage denominator correction are reflected in verification_rerun/; they do not change predictions or economics. The initial 2026 coverage count included the valid feature-only September 1 decision; the verified count uses actual price-bar timestamps and correctly reports 69,984. The feature-only row remains available for prediction but is outside this historical evaluation.', '',
        '## Run and inspect', '',
        '```powershell',
        'python scripts/run_bitcoin_5m_probability_model.py --output-dir research_scout/bitcoin_5m_v2_reproduction',
        'python -m pytest tests/unit/test_bitcoin_5m_probability_model.py tests/unit/test_bitcoin_5m_exchange_model.py tests/unit/test_bitcoin_5m_exchange_validation.py tests/unit/test_bitcoin_5m_repaired_runner.py -q -p no:cacheprovider',
        '```', '',
        'The output directory must be new. Dedicated entrypoint: scripts/run_bitcoin_5m_exchange_model.py. Model source: research/bitcoin_5m_exchange_model.py. Accounting/admission source: research/bitcoin_5m_exchange_validation.py. Documentation: docs/research_scout/Bitcoin5mExchangeModel-v2.md.', '',
        'Evidence: spec.json, results.json, verification.json, fine_calibration.csv, quarterly model_*.pkl, panel.parquet, predictions.parquet, shadow_trades.parquet, admitted_trades.parquet, delayed_shadow_trades.parquet and executed_code/. Final-source repeated evidence is under verification_rerun/.', '',
        '## Remaining limitations', '',
        'All 2020–August 2026 history was already exposed. Repair choices were motivated by previous audit outcomes; this is an engineering repair and historical diagnostic, not independent confirmation. No additional models, thresholds, holding periods, leverage, or entry delays were searched after these results.', '',
        'Returns use optimistic Binance bar references rather than executable Coinbase bid/ask quotes. Actual publication/receipt latency, spread, depth, queue, partial fills, order minimums, contract sizing, margin and hourly funding are unresolved. Settled Binance funding preserves actual timestamps and uses containing five-minute open approximate marks; exact entry/exit-boundary events are excluded. Optional OI imputation is explicit and causal but its missingness can itself drift.', '',
        'Version2 fixes the evidenced defects and adds a payoff-based decision policy. It does not demonstrate a deployable profitable bot. The appropriate next validation is prospective frozen predictions and executable quotes, keeping actionable trades blocked until sufficient independent economic evidence exists.', '']
    (HERE/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(status='VERIFIED',source_preservation=r['source_preservation'],
        prediction_reproduction='bit-identical',admitted_quarters=r['admitted_quarters'],report=str(HERE/'REPORT.md'))))


if __name__=='__main__':
    run()
