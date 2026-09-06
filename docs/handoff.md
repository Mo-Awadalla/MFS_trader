# Handoff: ETF SIP paper-evidence campaign

Updated: 2026-09-05

## Current release status

The release baseline is Python 3.12 and preserves the historical Yahoo ETF
Experiment as authoritative evidence. Its UUID is
`119131fa-0f67-48d7-ab87-f20d81c70c1f`, its hash is
`8e584c2eb4ba20a90b0af3d62a8f28c1d753a83a3e57ca79deafb869af23270e`, and
its current metadata status is `paper_ops`. It is historical evidence and is
not a SIP successor.

The new SIP campaign stopped at the input-integrity gate. No successor UUID or
hash, frozen Experiment, validation result, paper-evidence packet, broker
session, order, launchd job, or promotion exists. Remaining stage-2 paper
identity/CLI normalization and stages 3–5 are deferred.

## Retained SIP input evidence

The canonical attempted snapshot is
`sip-etf-daily-20260905t214300z`. Its label is an identifier; the authoritative
acquisition time is `2026-09-05T21:28:08.316145+00:00`. The immutable manifest
and portable input bundle are at:

- `docs/reports/etf_campaign_inputs/sip-etf-daily-20260905t214300z/manifest.json`
- `docs/reports/etf_campaign_inputs/sip-etf-daily-20260905t214300z/input-bundle.tar.gz`

It contains raw and `adjustment=all` SIP daily panels for DBC, GLD, IEF, IWM,
QQQ, SHY, and SPY. All 14 symbol/adjustment indexes contain 2,684 common
sessions from `2016-01-04` through `2026-09-04`. The bundle retains 19
manifest-listed inputs; their hashes match. The bundle SHA-256 is
`22dac4692868e21abd455b70f8133183b9364d5d3378e797b22d4c464c9af5fd`.

The original manifest remains failed because 140 of 388 returned cash-dividend
records lack `payable_date`; the same 140 also lack `record_date`. Missing
payable dates are the ledger blocker. The returned endpoint payload does not
prove that every corporate action was returned or that raw/adjusted price
factors reconcile, so filling those 140 fields alone would not authorize a
successor.

The complete successor snapshot is
`sip-etf-daily-20260905t214300z-corporate-actions-complete`. It reuses the
identical acquired bars, calendar, and assets payloads; only
`http/corporate_actions.json` gains the 140 `record_date`/`payable_date`
pairs (plus per-record `date_source`), matched from issuer-published
distribution histories (iShares for IEF/SHY/IWM, Invesco for QQQ/DBC, SSGA
for SPY) on ticker, ex-date, and event type; no dates were inferred. Its
bundle SHA-256 is
`9cf77ccdd38e636f76d07ab3c93f7b1e051da956532026729c42bad50de7235e`. The
retained-bundle verifier passed
(`docs/reports/etf_campaign_inputs/sip-etf-daily-20260905t214300z-corporate-actions-complete-calendar-integrity-verification.json`),
and the full-history reconciliation found no missing dividends, no missing
splits, and no unexplained raw/adjusted price-factor differences. Per-record
provenance and issuer-source hashes:
`docs/reports/etf_campaign_inputs/sip-etf-daily-20260905t214300z-corporate-actions-complete/backfill_provenance.json`.
Caveats kept for review: 94 records (IEF/SHY pre-2020) have issuer-displayed
amounts that differ from the Alpaca rate (dates are authoritative issuer
declarations; the Alpaca rate remains the amount of record), and DBC paid
twice in the week of 2018-12-24 (two price-panel adjustment steps; Invesco
lists one row; the 12-26 record is RESOLVED_WITH_NOTE).

The append-only corrected calendar verification is
`docs/reports/etf_campaign_inputs/sip-etf-daily-20260905t214300z-calendar-integrity-verification-v2.json`.
It verifies the retained panel using date plus `America/New_York` close time,
then UTC: 2,663 regular closes, 21 early closes, 902 EST closes, 1,782 EDT
closes, no duplicate dates, and no close after acquisition. It reports
`verification_status: passed`, while the source manifest remains failed and
the input gate remains blocked. The earlier verification report is retained
and referenced by the v2 report; do not overwrite either report or the
snapshot manifest.

Earlier attempted acquisition manifests (`212500z`, `213100z`, and `213400z`)
are retained as failed historical attempts and are not gate evidence.

The recorded latest-SPY SIP request returned HTTP 403 for recent data. A
bounded completed-session historical SIP request for all seven ETFs returned
HTTP 200. The 403 is advisory about latest access and is not the historical
input blocker. Do not substitute IEX for SIP.

## Historical replay diagnostic

The old Yahoo runtime replay is operational evidence only. Research ended at
`$50,944.37` and the runtime replay at `$27,759.42`, a `$23,184.95` gap. The
recorded mechanisms include fixed sizing equity, thresholded position deltas,
risk reductions, and distinct simulated/research cost treatment. No
counterfactual attribution was run, so this is not an economic-parity claim.

## Required recovery sequence

1. Preserve the failed snapshot and append a corporate-action completeness and
   raw/adjusted factor-reconciliation result; do not infer missing payable
   dates.
2. Implement the execution, identity/policy/CLI, and independent
   research/runtime-ledger work; verify deterministic synthetic parity tests
   only, then commit the implementation without candidate-performance claims.
3. Freeze a complete input manifest, predeclared execution/validation
   protocol, and new Experiment UUID/hash.
4. Prove session-level economic parity against that frozen identity, then run
   the unchanged validation gauntlet. Archive a failure without tuning.
5. Only a successor passing both parity and validation may enter the separate
   paper smoke, qualification, and operator-review gates.

The approved future paper defaults remain `$1,000` allocated capital, `$500`
maximum per order, `$1,000` gross exposure, `$100,000` cumulative turnover,
and a `$1` minimum adjustment or broker higher minimum without a percentage
filter. Existing percentage risk limits, validation thresholds, and tiny smoke
caps remain unchanged.

## Verification baseline

Before SIP integration, the isolated baseline commit
`ff87b10091b84cbd55fcc55491800830a22f92ed` passed the prescribed Python 3.12
checks in a fresh checkout: Ruff passed; pytest reported 586 passed and one
expected startup-reconciliation skip. The final integrated commit requires a
new fresh-checkout run of the same command.
