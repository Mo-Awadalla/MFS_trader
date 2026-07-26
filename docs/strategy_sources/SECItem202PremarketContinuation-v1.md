# SEC Item 2.02 Premarket Continuation v1

Status: frozen bounded falsification scout. It is not a registered Strategy, an
Experiment, or authorization for paper/live trading.

Machine-readable specification:
`research_scout/sec_item_202_premarket_continuation_v1.json`.

## Hypothesis

When a liquid U.S. company has an SEC Item 2.02 disclosure accepted before
09:25 ET, a positive stock-minus-SPY return during the first 30 regular-session
minutes may reflect firm-specific information that is still being incorporated.
A deliberately delayed long entry at 10:05 ET may therefore earn a positive
stock and residual return through a 15:55 ET exit after conservative retail
costs.

This differs from the repository's failed fundamental-event reversal scout.
The filing supplies the event, while the observed first-30-minute relative move
supplies direction. The rule tests continuation, not reversal and not a generic
filing veto.

## Frozen rule

- Eligible forms: `8-K` and `8-K/A`.
- Required item token: `2.02`.
- SEC acceptance: 00:00:00 through 09:25:00 America/New_York on the session.
- Universe: the existing static 133-stock liquid universe.
- Bars: adjusted Alpaca IEX five-minute regular-session bars plus SPY.
- Observed feed boundary: 2020-07-28. A pre-return data audit found that
  the configured Alpaca IEX account returned no bars before this date, so the
  development partition begins here rather than silently counting empty windows.
- Signal: stock 09:30-open-to-09:55-close return minus the identical SPY return.
- Trigger: residual signal strictly greater than zero.
- Entry: 10:05 bar open.
- Exit: 15:55 bar open.
- Portfolio: equal weight across selected stocks, long-only, gross exposure at
  most 1.0.
- Costs: 10 bps fixed round trip; 20 bps stress round trip.
- No threshold, short side, volume/news/sentiment/regime filter, stop, target,
  or re-entry.

The implementation retains incomplete event rows and reports their missing
inputs. It must not silently discard difficult sessions.

The observed IEX start-date correction was made before a return panel or report
was constructed. It changes data feasibility, not the signal, clocks, costs, or
progression gates.

## Evidence boundaries

The static current-active universe carries survivorship and historical-identifier
bias. IEX is venue-local rather than SIP/NBBO. SEC acceptance is an auditable
availability timestamp but can follow an issuer press release, so it is not
necessarily the first public timestamp.

Consequently, a pass permits only a new point-in-time-universe and SIP-quality
replication. It does not permit paper operation. A failure terminates this exact
branch without nearby thresholds, clocks, filters, or an inverted short rule.

## Reproduction

Run a data-only eligibility audit:

```bash
python scripts/run_sec_item_202_premarket_continuation_scout.py \
  --partition development \
  --audit-only
```

Download event-session bars and evaluate the unlocked partition:

```bash
python scripts/run_sec_item_202_premarket_continuation_scout.py \
  --partition development
```

Alpaca downloads require `ALPACA_API_KEY` and `ALPACA_API_SECRET`. Later
partitions remain locked until the preceding report passes.
