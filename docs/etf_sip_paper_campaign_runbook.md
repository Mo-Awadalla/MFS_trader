# ETF SIP paper-evidence campaign runbook

Status on 2026-09-05: no SIP successor has been frozen. The read-only
latest-SPY entitlement check returned HTTP 403 at
`2026-09-05T21:12:16.148693+00:00`, but a separate historical SIP probe for
all seven ETFs succeeded at `2026-09-05T21:18:56.184538+00:00` for
`2026-09-03T00:00:00Z` through `2026-09-04T00:00:00Z` with `feed=sip` and
`adjustment=all`. The limited historical probe is not a frozen data manifest
or full panel-completeness result. Do not replace SIP with IEX. No SIP input
manifest, frozen Experiment, validation report, broker session, order, or
launchd job exists.

The existing Yahoo Experiment `119131fa-0f67-48d7-ab87-f20d81c70c1f` remains
historical evidence in `paper_ops`. Its identity and evidence must not be
altered or reused for SIP inputs.

When entitlement has been provisioned, execute these gates in order:

1. Run the full read-only historical seven-symbol panel check and retain its
   feed, as-of time, requested history, universe, and completeness result.
2. Freeze a new immutable SIP data manifest, checksums, execution policy, and
   Experiment UUID/hash. The selection remains monthly using completed-session
   information; daily target maintenance may execute only in the next regular
   session's first five minutes.
3. Reconcile research and deterministic runtime ledgers session by session,
   including quantities, costs, risk reductions, corporate actions, cash, and
   equity. The historical replay is operational evidence only: it ended at
   `$27,759.42` versus `$50,944.37` in research, so it is not economic-parity
   evidence.
4. Run the unchanged validation gauntlet. Archive any failure without tuning
   or automatic replacement.
5. If validation passes, run fresh simulation drills, the tiny Alpaca
   submit/cancel smoke, then the formal paper-evidence window. Keep the
   Experiment in `paper_ops` pending independent operator confirmation.

Approved future campaign defaults, to freeze before validation:

- `$1,000` allocated paper capital; `$500` maximum per order; `$1,000`
  maximum gross exposure; `$100,000` cumulative campaign turnover.
- A `$1` minimum adjustment, or the broker's higher minimum, with no
  percentage-change filter.
- Existing percentage risk limits, validation thresholds, and tiny smoke caps
  remain unchanged.
- Qualification requires at least 30 calendar days, 20 market sessions, 100
  unique reconciled filled orders, 99.5% cycle completion, acceptable
  slippage, no unexplained missed cycles, no unresolved reconciliation, and
  recorded kill-switch drills. These are observed records, never targets that
  can be manufactured.

Install the separate engine and watchdog launchd jobs only after executable
parity and validation pass. The jobs need process locking, logs, local
notifications, sleep prevention while active, and heartbeats between sessions.
