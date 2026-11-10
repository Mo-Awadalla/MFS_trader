# Persistent Premarket Wrapper Premium — Preimplementation Critique v19

## Hypothesis

At 08:30 and 09:15 ET, calculate each leveraged ETF's log return from the
previous regular-session 15:59 observation and remove its idealized SPY beta:

- UPRO residual = UPRO gap − 3 × SPY gap
- SPXU residual = SPXU gap + 3 × SPY gap
- differential premium = UPRO residual − SPXU residual

If the differential has the same positive sign at both checkpoints, buy UPRO
after the cash open. If both are negative, buy SPXU. Otherwise hold cash.

The two-checkpoint persistence requirement distinguishes sustained premarket
wrapper demand from a single stale or noisy mark. No magnitude threshold is
allowed.

## Why a serious ETF desk might care

Leveraged wrappers can receive asymmetric premarket client demand even after
the common underlying move is removed. Market makers can hedge that demand in
SPY or futures while carrying wrapper inventory into the opening auction.
Persistent relative richness across two checkpoints is therefore a plausible
shadow of inventory that the opening cash session must distribute.

## Hard critique

1. SPY is a hedge proxy, not the funds' exact swap/futures basket or NAV.
2. Premarket ARCA trades can be stale; exact checkpoint requirements are
   mandatory and may destroy frequency.
3. A premium normally invites convergence. Continuation is justified only by
   persistence across two checkpoints, and that sign is frozen before outcomes.
4. Corporate actions and distributions can contaminate overnight gaps.
5. The theoretical coefficient need not be exactly three outside the cash
   session.
6. ARCA and EQUS.MINI may observe different last trades and BBOs. Weak
   cross-feed direction agreement rejects the idea before P&L.
7. This is related to, but not the same as, the failed v14 cash-session
   leverage-spectrum residual. V19 measures persistent overnight/premarket
   wrapper demand across two checkpoints and does not use SH or cash-session
   residual blocks. If the data cannot distinguish that state cleanly, it must
   not be implemented.
8. SPXU execution cost, year stability, winner concentration, and passive-SPY
   outperformance remain binding.

## Returns-blind admission gates

- exact observations on at least 80% of feed session dates;
- at least two persistent nonzero signals per week;
- minority direction at least 20%;
- conditional ARCA/EQUS.MINI direction agreement at least 70%;
- identical all-date actions at least 60%.

## Decision

Advance only to the returns-blind audit. No post-open price may be read unless
all measurement gates pass.

