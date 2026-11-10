"""Build a reviewable report from the completed audit, without changing the model."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def run():
    if (HERE/'REPORT.md').exists():
        raise FileExistsError('Preserve completed audit report; use a new version for changes')
    r=json.loads((HERE/'results.json').read_text())
    d=json.loads((HERE/'coverage_details.json').read_text())
    s=json.loads((HERE/'source_missingness.json').read_text())
    for name,h in r['source_sha256_before'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h
    for x in r['refit_diagnostics']:
        assert x['training_last']<x['calibration_first']<=x['calibration_last']<x['evaluation_first']
    assert r['reproduction']['probability_max_absolute_error']<1e-10
    assert r['architecture']['scaler_training_mean_max_difference']==0
    assert r['code_robustness']['tie_filter_future_dependency']=='CONFIRMED'
    assert r['data_quality']['inconsistent_ohlc_rows']==0
    checks=dict(status='PASS audit evidence reconciled',checks=[
        'Original predictions reproduced to less than 1e-10 maximum absolute error',
        'All original causal feature values reproduced to 1e-12',
        'Scaler mean exactly equals the training-only mean',
        'Price and metric future perturbation checks passed',
        'Future-dependent tie eligibility reproduced',
        'Long-window gap and invalid-bar validator weaknesses reproduced',
        'Three missing-metric raw source archives verified against official SHA256',
        'Both diagnostic refits have strictly ordered train/calibration/evaluation dates',
        'Original model unit test passed: 1 test; cache-write warning did not affect assertion execution',
        'All original model and previous exchange experiment source hashes remain unchanged'])
    (HERE/'verification.json').write_text(json.dumps(checks,indent=2)+'\n')
    lines=['# Bitcoin five-minute model audit', '', 'Date: September 30, 2026.', '',
        '**Verdict: a reasonable simple probability baseline, but an inadequate trading model with material data and evaluation defects.** The model has a small directional signal; the audit does not support describing it as random or completely broken. Its return objective, missing-data policy, model freshness, and decision eligibility need correction before another profitability claim.', '',
        'This audit inspected the original source, rebuilt all causal features, reproduced saved predictions, ran failure-case checks, traced source missingness, assessed calibration and feature sensitivity, and ran two fixed diagnostic refits. No original code, model, panel, or prior experiment result was modified. No accounts, orders, paid data, or new downloads were used.', '',
        '## Findings in priority order', '',
        '### 1. The target answers direction, not expected trading profit — high impact design mismatch', '',
        'The label is whether a five-minute candle closes above its open. Logistic classification penalizes a wrong 0.001% move the same way as a wrong 1% move; it does not estimate win/loss size, executable spread, fee, or expected monetary return. The original trading threshold simply uses p(up) >= 0.55 or <= 0.45. That can be useful for a binary-event probability, but it is insufficient for an exchange payoff.', '',
        'On Jan–Aug 2026 all-decision execution references, the original confident rule wins 54.13% of price-return trades, with mean win 13.27bps and mean loss 14.32bps. Using that observed payoff distribution, approximately 66.4% wins would be required to cover 4bps round-trip friction. This is a diagnostic calculation conditional on unchanged payoff sizes, not a universal required accuracy. Source: research/bitcoin_5m_probability_model.py:216 and :258; previous exchange all_decisions_diagnostic.json.', '',
        '### 2. Mandatory, mostly unavailable ratio fields remove most of 2022 — high impact data-design defect', '',
        'There are 105,120 five-minute price bars in 2022, but only 13,372 causally eligible decisions (12.72%) and 13,298 rows in the original non-tie training panel (12.65%). February, March, April, July, August, October, and November have zero training-panel rows. The required count_toptrader_long_short_ratio field is missing in 91,733 metric records that year. All-missing-row exclusion is causal, but the resulting training sample omits most of an important market year.', '',
        'Checksum-verified raw archives for February 1, July 1, and November 15, 2022 have the blank ratio in all 288 rows on each day. This establishes source missingness in those samples rather than a parser-created number. The preexisting integrity report already recorded these null fields; the model report did not surface their severe year-by-year coverage effect.', '',
        f"A coverage-only diagnostic removing optional trader-ratio requirements retains {s['coverage_only_ratio_feature_removal']['potential_causal_rows_without_ratio_feature_requirements']:,} of 105,120 2022 bars (99.83%). That is potential sample coverage, not a profitable replacement model. Missing ratios must not be backfilled from future values or invented. Source: research/bitcoin_5m_probability_model.py:193–212; coverage_details.json and source_missingness.json.", '',
        '### 3. Dataset eligibility depends on the eventual outcome — high impact validity defect, small measured economic effect', '',
        'build_dataset excludes a row if that same candle eventually closes exactly at its open. A deployment process cannot know this at the decision time. A synthetic check changes only the current eventual close to make a tie: current causal features remain identical but the original row disappears. Label filtering for binary research must be separated from decision eligibility and trade accounting.', '',
        'The audit predicts all causally eligible bars for economics, retaining zero-return ties. Jan–Aug 2026 includes 202 tied bars and 2,614 original confident trades versus 2,602 in the original non-tie-only evaluation. Correcting the exclusion does not rescue profitability. Source: research/bitcoin_5m_probability_model.py:209–212; previous all_decisions_diagnostic.py; audit.py robustness checks.', '',
        '### 4. The frozen model is stale, and its useful confidence has weakened — medium/high impact model-maintenance issue', '',
        'Base training ends June 2023 and calibration ends December 2023. The original model applies those same weights and scaler through August 2026. There is no rolling retraining, conditional recalibration, or drift-triggered update in this experiment. That is valid for a frozen test, but inadequate as the whole maintenance policy for a deployed trading system.', '',
        'The original standardized classifier converged in 18 iterations. Its Platt calibrator shrinks the raw logit by a slope of 0.573. Removing calibration worsens Brier loss beyond the 50/50 baseline in every evaluated year: calibration is helping, not causing the failure. On 2026 confident non-tie predictions, the average claimed correctness is about 56.00%, versus observed 54.38%. The seven-day-block interval for that confidence gap includes zero, so overconfidence in the selected tail is suggestive rather than conclusively measured. The evaluation-fitted reliability slope is approximately 0.70; it is diagnostic only and was not deployed.', '',
        'The original report uses 10-percentage-point calibration buckets. Almost all probabilities lie between 40% and 60%, so those broad buckets obscure behavior around the 45%/55% trade thresholds. This audit exports finer fixed buckets, sample sizes, monthly stability, and block uncertainty.', '',
        '### 5. Several features add little and some are nearly redundant — medium impact modeling limitation', '',
        'The model is an additive linear logistic classifier over 15 standardized inputs. That is a defensible baseline; simplicity itself is not evidence of a poor model. It cannot express conditional volatility/flow interactions without engineered features. One-bar close return and candle body correlate at 0.99993, volume and trade-count z-scores at 0.97423, and global/top-trader ratios at 0.97511 in training. Coefficient magnitudes among correlated inputs are not reliable causal importance measures.', '',
        'The strongest fitted coefficients and group sensitivity point mainly to price reversal and taker flow. Open-interest inputs have very small fitted contributions. Replacing the positioning-ratio group with its training means slightly improves Brier in 2024, 2025, and 2026. This is a fixed-model sensitivity diagnostic, not retrained ablation, an importance significance test, or permission to select features using the test outcomes. It nevertheless makes discarding most of 2022 to require those fields especially questionable.', '',
        '### 6. Data guards and test coverage are incomplete — medium impact engineering issues', '',
        'The continuity guard checks only 12 previous transitions, while other features require 48 or 288 observations. A synthetic gap outside the 12-bar guard but inside the longer windows changes features without excluding the row. No actual price-grid gaps occur in these 631,008 loaded bars, so this is a reproducible robustness defect rather than demonstrated historical price-gap contamination.', '',
        '_validate_bars accepts a high below low, NaN/infinite prices, and taker-buy volume exceeding total volume. The actual loaded prices have no nonfinite values, inconsistent OHLC rows, or invalid taker-volume rows. Downstream filtering can discard some malformed data, but it cannot replace explicit ingestion validation. The existing model test contains one broad smoke test; it passes, but does not exercise these failure cases. Source: research/bitcoin_5m_probability_model.py:50–85 and :207–208; tests/unit/test_bitcoin_5m_probability_model.py.', '',
        '## What the model gets right', '',
        '- Price features use prior completed candles, and observed derivatives metrics are at least five minutes old. Future price/metric perturbations leave current features unchanged.',
        '- Scaling is fitted on training data only, and calibration uses a separate later partition. The chronological splits are appropriate for the original one-bar target; an arbitrary long embargo would not by itself fix the model.',
        '- Feature reconstruction matches every original panel row within 1e-12; the frozen model reproduces every saved probability exactly.',
        '- Calibrated probability loss and directional accuracy improve slightly over simple priors across 2024, 2025, and 2026. Within the fixed-model daily-block diagnostic, that small predictive advantage is measurable. It is much weaker in economic return terms.', '',
        '## Frozen-model probability quality', '',
        'Direction statistics exclude ties explicitly; economics includes them. Brier skill is fractional loss reduction relative to the constant training-rate prior. A skill of 0.08% is a very small improvement.', '',
        '| Period | Direction accuracy | Brier | Brier skill | Confident accuracy |',
        '| --- | ---: | ---: | ---: | ---: |']
    for year,v in r['periods'].items():
        a=v['calibrated']
        lines.append(f"| {year} | {a['accuracy']:.2%} | {a['brier']:.6f} | {a['brier_skill_vs_training_prior']:.3%} | {a['confident_accuracy']:.2%} |")
    lines+=['', 'For example, the 2025 Brier improvement over the training prior is 0.000196, with a circular seven-calendar-day bootstrap 95% interval approximately [0.000049, 0.000342]. These conditional diagnostics are not corrected for the repository’s full research search history. Positive probability skill does not establish positive tradable returns.', '',
        '## Does refreshing the same model help?', '',
        'Two expanding-window diagnostic refits were declared in spec.json before running them. They keep the same 15 features, logistic C=0.1, separate Platt calibration, fixed 55% decision threshold, and five-minute holding rule. The 2025 refit trains through June 2024 and calibrates on July–December 2024; the 2026 refit trains through June 2025 and calibrates on July–December 2025. No threshold or hyperparameter search was performed. They retain the existing complete-case ratio policy, so they do not repair the 2022 exclusion.', '',
        '| Evaluation | Version | Trades | Gross bps/trade | Net at 4bps | Gross + funding 95% interval |',
        '| --- | --- | ---: | ---: | ---: | --- |']
    for x in r['refit_diagnostics']:
        year=str(x['year'])
        for label,e in [('Original frozen',r['periods'][year]['economics_all_causal_decisions']),('Refreshed diagnostic',x['economics'])]:
            ci=e['gross_plus_funding_ci95_bps']
            lines.append(f"| {year} | {label} | {e['trades']:,} | {e['gross_bps']:.3f} | {e['net_bps']['4']:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] |")
    lines+=['', 'Refreshing improves gross expectancy in these diagnostics, but it selects far fewer confident trades. The 2025 refreshed version has only 227 trades and its gross interval includes losses; the nearly break-even 4bps point estimate is not evidence of reliable profit. The 2026 refreshed version has 566 trades, earns 1.826bps gross, and loses 2.172bps per trade at 4bps friction. Its gross interval also includes losses. Thus staleness matters, but neither refit demonstrates that freshness alone is sufficient.', '',
        'The 4bps assumption is the same deliberately favorable fee-only scenario used in the prior exchange study; it is not an account-specific verified fee. Spread and slippage could make results worse. A basis point is 0.01%. Results use Binance open-to-next-open references, not executable Coinbase fills. Funding is the previously documented Binance timestamp/approximate-mark calculation. These historical diagnostics do not validate venue transfer, latency, maker queue behavior, or live performance.', '',
        '## Repair priorities', '',
        '1. Separate causal feature generation/eligibility from realized labels. Decide and document tie treatment for binary scoring while retaining all decision-time eligible bars for trading.',
        '2. Rebuild feature/data eligibility so optional sparse ratios cannot remove most of an entire year. Use a smaller complete feature set or an explicit causal missing-data design, verify source coverage by month, and preserve the old experiment rather than rewriting its history.',
        '3. Evaluate fixed rolling or expanding retraining/calibration schedules chronologically, with labels available before each fit. Do not optimize update schedules on already viewed 2025–2026 outcomes.',
        '4. For exchange trading, model return size or the return distribution as well as direction. Admission and position decisions must compare expected monetary payoff with realistic total execution cost.',
        '5. Add full lookback/gap checks, finite/OHLC/flow validation, finer reliability reporting, and the reproduced edge-case tests.',
        '6. Freeze the repaired design and evaluate subsequent data with observed executable quotes and latency before claiming profit. The current audit does not authorize or justify live trading.', '',
        '## Interpretation and reproducibility', '',
        'This audit diagnoses an existing model; all historical outcomes used here are already exposed. The two refits are explicitly new audit diagnostics, not independent confirmation or promoted candidates. Fixed-group mean replacement preserves the frozen model and tests sensitivity; it must not be interpreted as retrained feature removal. The apparent gross gain from updating is sample-dependent and does not establish its causal contribution relative to every alternative.', '',
        'Feature causality checks verify timestamp construction, not actual exchange publication latency. Price features from the immediately preceding bar are available only after that bar closes, so execution at the exact next bar open remains optimistic. Data source differences from Polymarket and Coinbase remain unresolved. No fee-adjusted trading profit is claimed.', '',
        'To reproduce in a new versioned output directory: run audit.py, details.py, coverage_recovery.py, then write_report.py. audit.py and the report writer refuse to overwrite completed primary audit evidence. Dependencies and public source files are those already present in this workspace. The existing test command is .venv/Scripts/python.exe -m pytest tests/unit/test_bitcoin_5m_probability_model.py -q. It passed with a nonfatal pytest cache-write warning.', '',
        'Machine evidence: spec.json, results.json, coverage_details.json, source_missingness.json, verification.json. All original and previous exchange-study hashes were rechecked after the audit and matched.', '',
        'Methodology references: [scikit-learn probability calibration](https://scikit-learn.org/stable/modules/calibration.html) describes independent calibration data, reliability curves, and why Brier loss mixes calibration and discrimination; [logistic regression documentation](https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression) describes the model family. The numerical findings above come from local source and archived data, not those documentation pages.', '']
    (HERE/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(status='REPORT SAVED',verification=checks['status'],path=str(HERE/'REPORT.md'))))


if __name__=='__main__':
    run()
