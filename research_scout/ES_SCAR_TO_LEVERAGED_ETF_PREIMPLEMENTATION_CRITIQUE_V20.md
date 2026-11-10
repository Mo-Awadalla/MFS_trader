# ES Prior-Scar Signal to UPRO/SPXU — Preimplementation Critique v20

The ES prior-close volume-scar rule is the strongest independently developed
signal in the repository: positive in all five years and both directions, with
positive development and secondary holdout under substantial cost stress.

V20 changes no signal component. It transports the frozen ES state into the
$100 fractional UPRO/SPXU account:

- prior ES 15:00–15:29 volume scar;
- current ES 09:30–09:59 center and terminal-price confirmation;
- UPRO for long and SPXU for short;
- causal 10:01 ETF ask after the completed signal;
- structural ES invalidation one tick beyond the opening center;
- ETF bid in the minute after invalidation, otherwise 15:30.

## Why a high-end ETF desk would listen

ES is the primary price-discovery and hedging venue for S&P risk; leveraged ETFs
are actuators rather than sensors. Separating signal formation from ETF
execution avoids asking sparse leveraged-ETF trades to discover direction.

## Why it may still fail

- The ES rule's known holdout is tail-dependent.
- Its expectancy decays rapidly with entry delay; 10:01 is deliberately causal
  and may be too late.
- Mapping an ES stop into a next-minute ETF liquidation introduces basis and
  timing risk.
- SPXU spreads can erase short-side expectancy.
- The historical ES holdout is already known; an ETF survivor is not pristine
  evidence and still requires forward observation.

## Decision

Implement exactly this transport. Reject unless it clears frequency, every
year, both actuators, BBO cost and delay, winner removal, passive SPY, untouched
ETF-execution holdout, and EQUS.MINI execution-rebuild gates. No scar, clock,
stop, side, or exit modification is permitted.

