# Treasury Settlement / ON RRP Liquidity Netting Postmortem v71

V71 is rejected returns-blind. No P&L was calculated.

The construction was dense, balanced, stable to a prior-three dealer-award
baseline, temporally causal, and fully executable on the primary feed. The
independent 2023 overlap had 98 eligible signals and 98.98% complete entry/exit
quote coverage.

The defining netting claim failed. V71's action matched RRP change alone on
347 of 383 settlement dates, or 90.60%, above the frozen 80% ceiling. The
dealer settlement term changed only 36 decisions. Thus the proposed
Treasury-settlement interaction mostly relabeled a standalone ON RRP sign.
Standalone RRP change does not identify an equity flow: the cash can move
among the Fed facility, Treasury bills, private repo, deposits, or reserves.

Do not rescale dealer awards, normalize RRP, select disagreement dates, impose
a magnitude threshold, invert the sign, or open the RRP-only P&L. The
settlement/RRP arithmetic family is consumed.
