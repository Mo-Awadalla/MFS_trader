# ProShares +3/−1/−3 Delta-Neutral Triangle Convergence — Critique v69

## Decision before implementation

Advance to a returns-blind audit only. No post-entry price may be converted
into a return until coverage, balance, stability, independent reproduction,
and exact marketable execution all pass.

## Frozen construction

UPRO, SH, and SPXU are ProShares funds targeting +3×, −1×, and −3× the daily
S&P 500 return. Official prior NAV and continuous BBO histories exist for all
three throughout 2021–2023.

At the exact 09:32 midpoint, calculate each fund's return from its official
prior-session NAV and divide by its stated leverage:

- `x_UPRO = (UPRO / prior_NAV_UPRO - 1) / 3`;
- `x_SH = (SH / prior_NAV_SH - 1) / -1`;
- `x_SPXU = (SPXU / prior_NAV_SPXU - 1) / -3`.

This yields two overidentifying residuals:

- `positive_inverse_basis = x_UPRO - x_SH`;
- `inverse_scale_basis = x_SPXU - x_SH`.

Trade both residuals at 09:33 with $50 gross per pair:

### UPRO / SH pair

Use 25% of pair gross in UPRO and 75% in SH.

- basis positive: short both UPRO and SH;
- basis negative: buy both UPRO and SH;
- exact zero: cash.

The same-side position is intentional. Long UPRO contributes positive index
delta while long SH contributes negative delta:
`0.25 × 3 + 0.75 × -1 = 0`.

### SPXU / SH pair

Use 25% of pair gross in SPXU and 75% in SH.

- basis positive: buy SPXU and short SH;
- basis negative: short SPXU and buy SH;
- exact zero: cash.

Here opposite position sides neutralize two negative-leverage funds:
`0.25 × -3 - 0.75 × -1 = 0`.

Exit every leg at 10:30. Longs enter at ask and exit at bid. Shorts enter at
bid and cover at ask. Short proceeds are not recycled into gross exposure.
The two SH legs remain separately costed even when they could be netted; this
is conservative and avoids creating a favorable execution assumption.

## Causal mechanism

All three funds reset from official NAV and reference the same daily S&P 500
return. A common underlying move should map into their prices in the stated
leverage proportions. Different opening auctions, client orders, creations,
redemptions, and dealer inventories can temporarily dislocate one wrapper.

Authorized participants and market makers can hedge or create/redeem the
wrappers. Their arbitrage links supply the convergence mechanism. The strategy
does not predict the S&P. It takes offsetting index delta and asks whether the
same-issuer leverage triangle reconciles after the open.

## Would a high-end ETF desk take it seriously?

Yes as a structurally valid relative-value research question.

The same-side UPRO/SH position looks unusual to a directional trader but is
ordinary algebra to a derivatives or ETF desk: opposite stated leverage makes
the common index exposure cancel. A sophisticated desk would use live iNAV,
futures, swaps, complete books, creation costs, financing, dividends, stock
loan, and subsecond execution. The public implementation is a deliberately
slow and conservative proxy.

## Hard internal critique

1. Prior NAV is not live fair value.
2. The funds can use different swaps, futures, collateral, financing, and
   fee accruals.
3. A genuine discrepancy may converge before the delayed 09:33 entry.
4. SH is reused in both pairs, so errors in SH NAV or quotes can create two
   apparently independent signals. Results must be reported by pair and basis
   sign, not only pooled.
5. Separately crossing the two SH legs overstates realistic netted cost but
   protects against optimistic internal crossing.
6. Historical BBO does not establish borrow locates, rebates, or Reg SHO
   handling. No live recommendation is possible without those.
7. Arca is not the SIP NBBO. Independent EQUS feature and execution evidence
   are binding.
8. A no-threshold rule deliberately trades tiny residuals. Costs may dominate,
   and a failed result cannot be repaired by choosing a basis magnitude.
9. First-order 25/75 delta neutrality ignores beta drift and tracking error.
10. A market-neutral trade may have a good risk-adjusted return yet still fail
    the user's absolute adjusted-SPY hurdle. The hurdle remains binding.

## Relationship to consumed work

- v14 used a leverage-spectrum residual to choose one directional wrapper;
  v69 trades the replication error with its hedge.
- v48/v62 used one-legged wrapper convergence constructions.
- v68 froze the cleaner 3×/2× version but failed because SSO/SDS BBO history
  was absent. V69 is separately numbered and uses only the complete +3/−1/−3
  ProShares triangle.

## Binding falsification

Reject if:

- either pair or either basis sign is sparse;
- the 09:32 sign is unstable at 09:31 or 09:33;
- independent-feed pair actions disagree;
- any required entry/exit quote is missing;
- either pair, either basis sign, or any development year loses;
- 25/75 weights do not beat equal-dollar weights;
- divergence beats convergence;
- an extra cent per leg fill, a five-minute delay, or deleting ten best
  sessions eliminates profit;
- the five-session bootstrap lower mean is nonpositive;
- independent 2023 overlap is nonpositive;
- compounded cash does not beat adjusted SPY.

## Anti-repair rule

Do not net SH legs after seeing results, add a residual threshold, select one
pair or basis sign, change 25/75 weights, assume midpoint/passive fills, change
clocks, use a SPY bar as a substitute hedge, or open recent years after a
failed development gate.

