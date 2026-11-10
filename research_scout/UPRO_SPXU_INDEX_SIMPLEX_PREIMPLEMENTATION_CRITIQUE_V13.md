# UPRO/SPXU Index-Simplex v13: Preimplementation Critique

Saved before any v13 outcome was calculated.

## Research constraint

The prior Breadth Consensus result permits one lesson only: agreement between
independent equity segments may identify a broad information shock. It does not
permit deleting bearish trades, choosing a favorable clock, adding a fitted
return threshold, or combining the signal with another historically profitable
rule.

## Ideas rejected before implementation

### Breadth-consensus lifecycle

Treat agreement as a state with a birth and death, entering at agreement and
exiting at disagreement.

Rejected because it repackages the already failed Consensus Formation Event at
different intraday checkpoints. Moving the same transition around the clock is
not a new mechanism.

### QQQ-SPY-IWM triangle circulation

Use the signed area traced by relative returns to infer whether information
rotated from growth to small caps or in the reverse order.

Rejected because the sign-to-trade mapping is ambiguous. The same circulation
can describe either diffusion or exhaustion; choosing between them would require
looking at returns.

### Estimated leveraged-fund closing demand

Infer closing rebalance pressure from UPRO and SPXU dollar volume.

Rejected because volume is not fund AUM, shares outstanding, or creation-unit
flow. The available data cannot identify the mechanical quantity required by
the theory, and Closing Rebalance Torque already failed.

### Recursive strategy selector

Trade Breadth Consensus only while its trailing realized P&L is positive.

Rejected because it uses noisy strategy outcomes rather than a market
mechanism. It would be an adaptive post-hoc switch and would likely chase
regimes after they changed.

### Leveraged-pair tracking convergence

Trade temporary UPRO/SPXU deviations from their theoretical SPY exposure.

Rejected because any genuine price discrepancy should be arbitraged on a much
shorter horizon than one-minute BBO snapshots can execute or validate.

## Hypothesis that passes the smell test

### Index-Simplex Coherence

At the end of the first hour:

1. QQQ and IWM must have the same nonzero open-to-10:29 return sign.
2. SPY's corresponding return must lie inside the closed interval spanned by
   the QQQ and IWM returns.
3. Buy UPRO for positive agreement or SPXU for negative agreement at the
   observed 10:31 ask.
4. Exit at the observed 15:55 bid.

The interval test has no fitted coefficient, percentile, volatility adjustment,
or magnitude cutoff.

## Why it might work

QQQ and IWM are economically different equity segments. When they move in the
same direction and SPY lies between them, the three returns admit a simple
one-dimensional ordering consistent with a shared market shock. Neither segment
nor SPY is the outlier. If information reaches the segments at different rates,
this coherent cross-section may continue propagating through the S&P complex
after 10:30.

This is not a claim that SPY is literally a portfolio of QQQ and IWM. The
convex-hull relation is used only as a parameter-free coherence test.

## Why it might fail

- QQQ, SPY, and IWM share market beta, so containment may be common but
  informationally empty.
- SPY is not a fixed convex combination of QQQ and IWM; different sector
  exposures and betas can violate the geometry without implying disorder.
- The filter may merely reduce the trade count while retaining the original
  candidate's winner concentration.
- The original edge was too thin to dominate SPY reliably. A geometric subset
  must improve per-trade economics materially, not just produce a positive
  backtest.
- IEX 30-minute signal bars and ARCA execution quotes come from different
  market views. The consolidated-BBO audit must agree with the ARCA result.

## Decision before implementation

Implement exactly one candidate. It passes because its direction is determined
before outcomes, its geometry is parameter-free, its horizon is slow enough for
the available data, and it adds no transactions. Reject it unless it clears the
same frequency, cost, delay, concentration, year, direction, holdout, and SPY
hurdles as prior candidates.

