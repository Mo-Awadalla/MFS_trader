# ETF SIP paper-evidence campaign runbook

## Status: input-integrity gate passed; paper identity/CLI remains unimplemented

No SIP successor is frozen. The canonical attempted snapshot is
`sip-etf-daily-20260905t214300z`; its authoritative `acquired_at` is
`2026-09-05T21:28:08.316145+00:00`, not the arbitrary identifier timestamp.
Its immutable manifest is failed and its bundle is retained unchanged as
evidence at:

- `docs/reports/etf_campaign_inputs/sip-etf-daily-20260905t214300z/manifest.json`
- `docs/reports/etf_campaign_inputs/sip-etf-daily-20260905t214300z/input-bundle.tar.gz`

The bundle has 19 manifest-listed files, all hash-verified, covering DBC, GLD,
IEF, IWM, QQQ, SHY, and SPY. Raw and adjusted panels each have 2,684 common
completed sessions from `2016-01-04` through `2026-09-04`.

The failure is deliberate and remains blocking: 140 of 388 returned
cash-dividend records lack `payable_date`. Those same 140 lack `record_date`;
missing record date is recorded diagnostically, while missing payable date is
the ledger gate. By symbol the missing-payable counts are DBC 3, IEF 47, IWM
13, QQQ 16, SHY 47, SPY 14, and GLD 0. The report does not prove endpoint-wide
corporate-action completeness, absence of splits, or raw/adjusted price-factor
reconciliation. Do not infer dates or claim that adding the 140 values alone
unblocks the campaign.

Recovery step 1 is now done. The complete successor snapshot
`sip-etf-daily-20260905t214300z-corporate-actions-complete` fills the 140
missing `record_date`/`payable_date` pairs from issuer-published distribution
histories (iShares for IEF/SHY/IWM, Invesco for QQQ/DBC, SSGA for SPY),
matched on ticker, ex-date, and event type; no dates were inferred. Per-record
provenance, issuer source files, and their SHA-256 hashes are retained in
`docs/reports/etf_campaign_inputs/sip-etf-daily-20260905t214300z-corporate-actions-complete/backfill_provenance.json`. The retained-bundle verifier passed on the complete snapshot
(`...-corporate-actions-complete-calendar-integrity-verification.json`), and a
full-history reconciliation found no missing dividends, no missing splits, and
no unexplained raw/adjusted price-factor differences. Known caveat retained
for review: for 94 records (IEF/SHY pre-2020) the issuer-page displayed amount
differs from the Alpaca rate; dates are authoritative issuer declarations while
the Alpaca rate remains the amount of record because it is consistent with the
price panel. DBC paid twice in the week of 2018-12-24 (two distinct price-panel
adjustment steps); Invesco lists one row and the 12-26 record is marked
RESOLVED_WITH_NOTE.

The retained calendar initially had time-only closes. The append-only v2
verification corrects their interpretation as session-date plus
`America/New_York` time, then UTC:

`docs/reports/etf_campaign_inputs/sip-etf-daily-20260905t214300z-calendar-integrity-verification-v2.json`

It verifies 6,709 retained calendar records, 2,684 completed panel sessions,
2,663 regular 16:00 closes, 21 13:00 early closes, 902 EST closes, 1,782 EDT
closes, zero duplicate dates, zero closes after acquisition, and exact index
alignment across 14 panels. Its calendar verification passed; its source
manifest status remains failed, its input gate is blocked, and it does not
authorize campaign progression. The prior verification report and all four
failed acquisition-attempt manifests are retained without overwrite.

A latest-SPY SIP request received HTTP 403 for recent data. A bounded
historical seven-ETF SIP query returned HTTP 200 with `feed=sip` and
`adjustment=all`; historical access is therefore not blocked by the latest
403. Do not substitute IEX.

The historical Yahoo Experiment
`119131fa-0f67-48d7-ab87-f20d81c70c1f` remains in `paper_ops` as historical
evidence. It must not be reused for SIP provenance.

## Read-only evidence commands

Run these from a fresh checkout with Python 3.12. The environment file is read
only into process memory. Each evidence output and snapshot identifier must be
new because the writers reject overwrite.

```bash
python scripts/preflight_alpaca_sip_entitlement.py \
  --config config/etf_tsm_sip_campaign_preflight.toml \
  --env-file .env --feed sip \
  --output docs/reports/etf_campaign_preflight/<new-preflight>.json

python scripts/acquire_etf_tsm_sip_inputs.py --acquire \
  --env-file .env --snapshot-id <new-unique-snapshot-id>

python scripts/verify_etf_tsm_sip_snapshot.py \
  --bundle docs/reports/etf_campaign_inputs/<snapshot>/input-bundle.tar.gz \
  --manifest docs/reports/etf_campaign_inputs/<snapshot>/manifest.json \
  --report docs/reports/etf_campaign_inputs/<snapshot>-calendar-integrity-verification.json
```

The verifier extracts the portable bundle to a temporary matching
`data/parquet/...` layout before checking all manifest hashes and both strict
panels; it does not need a pre-existing local data cache. The acquisition
script's cutoff is fixed in its reviewed source and must be deliberately
updated and re-reviewed before a later campaign snapshot.

## Deferred work

No successor UUID/hash, validation report, paper evidence packet, broker
session, order, kill-switch drill, launchd job, or live promotion exists.
Remaining paper identity/CLI normalization is unimplemented. Economic-parity
work, qualification, and all paper-operation stages are deferred by the failed
input gate.

The historical runtime replay is not economic-parity evidence: its ending
`$27,759.42` differs from research ending `$50,944.37` by `$23,184.95`. Timing,
fixed sizing, holdings drift, risk reductions, and different cost treatment
are recorded possible mechanisms, without a counterfactual attribution.

## Recovery sequence

1. DONE 2026-09-06: corporate-action completeness appended (backfilled from
   issuer-published histories) and raw/adjusted price-factor jumps reconciled;
   the failed snapshot is preserved unchanged. See
   `sip-etf-daily-20260905t214300z-corporate-actions-complete/`.
2. Implement paper identity/policy/CLI handling and independent ledgers;
   verify deterministic synthetic parity tests and commit the implementation
   without candidate-performance claims.
3. Only after complete inputs and committed implementation exist, freeze a new
   data manifest, predeclared execution/validation protocol, and Experiment
   UUID/hash.
4. Prove candidate session parity tied to that frozen identity, then run the
   unchanged validation gauntlet and archive any failed successor.
5. A successor passing both parity and validation may then run the paper smoke
   and qualification campaign before independent operator review.

## Frozen future defaults

When the gate is eventually passed, freeze these defaults before validation:

- `$1,000` allocated paper capital; `$500` maximum per order; `$1,000`
  maximum gross exposure; `$100,000` cumulative campaign turnover.
- A `$1` minimum adjustment, or the broker's higher minimum, with no
  percentage-change filter.
- Existing percentage risk limits, validation thresholds, and tiny smoke caps.
- Monthly selection from completed-session information with daily target
  maintenance only in the next regular session's first five minutes.
- Qualification measured from persistent evidence: at least 30 calendar days,
  20 market sessions, 100 unique reconciled filled orders, 99.5% cycle
  completion, acceptable slippage, no unexplained missed cycles, no unresolved
  reconciliation, and recorded kill-switch drills.

Install separate engine and watchdog launchd jobs only after executable parity
and validation pass. Use process locking, logs, local notifications, sleep
prevention while active, and heartbeats between sessions.
