# Release-reconciliation disposition

## Base and authority

The candidate branch is `codex/release-reconciliation`, isolated from the user's original checkout. Its base is sanitized `origin/main` `7c32d0b1c1730f317d008e67b2b754c05d4da213`. Remote inspection/fetch and local commits are permitted; publishing, remote merging, history rewriting, broker access, and real Experiment changes are not.

Ref inspection on 2026-09-28 found PR #3 open at `b2526f6df5ef08a66dd1f3b880d02cab74ae0f23`, numerical work at `9b1c10c9c6bd6e45f1c9002839a057e76a0778a2`, and diverged ETF-paper work at `22595d1e5018a8211f13e991f7b0c3762156f5ec`. Historical successful CI runs on main/PR #3 are not verification of this candidate.

The original checkout had 708 modified/untracked status paths and local main `df29331`, on pre-rewrite history. It remains outside the integration worktree. Local release-correctness and ETF-paper branches also descend from old history; none is merged wholesale. Original checkout status and tracked-diff fingerprint are retained externally for preservation checks.

## Change disposition

| Source / concern | Disposition | Reason |
| --- | --- | --- |
| Sanitized main `7c32d0b` | Adopted as base | Preserves cleanup ancestry and existing lint repairs |
| Numerical commit `9b1c10c` | Adopted as `7cb4dd8`, then corrected/extended in `bcbf2a6` | Initial-equity peak, adverse signed percentile, bootstrap endpoint, referenced DSR; complete caller migration and invalid-data handling were still required |
| PR #3 CCXT guard `cdfec10` | Adopted as `aec29be` | Absent sandbox URL must not call unsupported sandbox configuration; data downloader remains read-only, not trading authority |
| PR #3 data catalog `928a722` | Adopted as `83ea04b` | Central local-bar reads and explicit aligned-panel preparation; no downloader or strategy change |
| PR #3 offline wheel smoke `b2526f6` | Adopted as `103db33`, verification superseded by `8eea866` | Original wheel environment installed development requirements and could conceal runtime dependency omissions |
| Isolated packaging `37b8994` | Adopted as `8eea866` | Runtime-only verifier, package assets, optional-import boundaries, offline guard, interpreter matrix, scoped constraints |
| Isolated parity `a6121c0` | Adopted as `2525c4f` | Additive ledger observations and declared execution differences; structural PASS is not financial equality |
| Corrected-evaluation work `7d5875f` / `6a3dbf3` | Adopted, admission integrated in `2aad4f5` | Separate immutable computation/provenance and recovery dispositions; historical PASS alone cannot grant current paper readiness |
| Offline paper evidence/recovery `a41e069` | Adopted | Calendar-derived cycles, scoped observed fills, durable attempt/checkpoint recovery, mandatory startup reconciliation; no real broker campaign |
| Paper integration `757c15b` | Adopted | Synthetic fixtures compute current numerical evidence; paper-run uses the shared pre-subcommand config option |
| Diverged ETF-paper branch wholesale | Deliberately excluded | Contains unrelated strategy families, restricted input bundles, lifecycle transitions, and live-session development |
| Live-session authority facades and new strategy/event-MC policy abstractions | Deliberately excluded | Not required for the research/simulation release; no second authority or trial-count method introduced |
| Intraday annualization idea from diverged work | Adopted narrowly | MC callers record 252 × bars/session rather than silently treating each intraday bar as a day |
| Old local branches and user modifications | Preserved, not imported | Old ancestry and unrelated work cannot be reconciled by overwriting the user's checkout |
| Real frozen snapshots, original reports, and lifecycle statuses | Intentionally unchanged | Numerical correction is not retroactive evidence or promotion authority |
| Historical full-window ETF financial-gap attribution | Blocked by evidence | Retained cache has 1,260 union bars, not the original 5,405; distinct-window attribution cannot replace original input identity |
| Broker-paper qualification | Not established | No broker campaign, elapsed qualifying window, attributable broker fills, or operator sign-off was manufactured |
| Remote publication | Pending owner action | No push, merge, remote tag, package publish, or deployment is authorized by reconciliation |

## Audit/current-state discrepancies

- The numerical branch was not based on latest sanitized main; cherry-picking its correction avoids losing intervening cleanup/lint work.
- Corrected MC/DSR code alone did not migrate every caller. No-tuning callers now explicitly lack sufficient selection evidence instead of retaining historical success or silently switching trial-count methods.
- The historical handoff's implementation claims and earlier test counts are not current verification. Its missing offline startup-failure regression must be executable in release checks; real broker tests remain disabled.
- Stored metadata, not a diverged branch's narrative, controls historical identity. The featured Yahoo Experiment remains historically `validation_passed`, not newly authorized `paper_ops`.
- A simulated drill PASS is not the required 30-calendar-day, 20-market-session, 100-trade paper window.
- Python metadata retained 3.11 support while the old NumPy development pin required 3.12. Separate compatible locks and runtime-only installation checks preserve both intended versions.
- Structural ETF replay completed, but research/runtime timing, capital basis, thresholds, cost accounting, and risk exposure differ. Those differences are declared and attributed, not hidden behind a shared PASS.
- A HARD kill switch also suspends the Experiment. Paper startup checks that switch before the generic lifecycle rejection so the original operator halt reason is retained.

## Verification authority

The final external release packet—not this disposition table—must identify the exact clean source commit/tree, wheel checksum, interpreter/dependency environments, command logs and exit codes, individual skips, independent review findings, and remaining blockers. Any later source change invalidates affected verification. A local green run does not establish remote CI, distribution rights, strategy profitability, financial parity, or broker qualification.
