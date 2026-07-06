# SPYOpeningHourCorrelation-v1

Date predeclared: 2026-06-29

## Purpose

Scout whether SPY's first regular-session hour contains directional information about the next trading hour or the final trading hour. This is a descriptive hypothesis scout, not a trading authorization.

## Instrument

`SPY` only.

## Data

- Use public Yahoo Chart API intraday bars: `range=730d`, `interval=60m`, `includePrePost=false`.
- Keep regular-session bars only.
- Treat Yahoo 60-minute timestamps as bar start times in New York time.
- Require at least these bars for a session:
  - 09:30 bar: opening hour, approximately 09:30-10:30.
  - 10:30 bar: next hour, approximately 10:30-11:30.
  - 15:30 bar: final half-hour/hour proxy ending at/near close.

## Primary hypothesis

SPY first-hour return is positively correlated with same-day final-hour return.

Mechanism: broad-market intraday momentum and institutional execution can cause early market direction to persist into the close.

## Secondary hypothesis

SPY first-hour return is positively correlated with the immediately following hour return.

Mechanism: early-session price discovery may continue into the next hour, but the effect may be weaker because late-day institutional/closing flows are absent.

## Frozen measurements

For each valid session:

- `first_hour_return = close(09:30 bar) / open(09:30 bar) - 1`
- `next_hour_return = close(10:30 bar) / open(10:30 bar) - 1`
- `last_hour_return = close(15:30 bar) / open(15:30 bar) - 1`

Report:

1. Pearson and Spearman correlation between first-hour and next-hour returns.
2. Pearson and Spearman correlation between first-hour and last-hour returns.
3. Conditional mean/median/win-rate of next-hour and last-hour returns when first-hour return is positive versus negative.
4. Quintile table by first-hour return, measuring next-hour and last-hour average returns.
5. First-half versus second-half chronological stability for the two Pearson correlations.

## Scout pass criteria

This scout is not allowed to create a promoted Experiment. It only passes as an interesting lead if all are true:

- At least 400 valid sessions.
- Primary Pearson correlation between first-hour and last-hour returns is > 0.05.
- Primary Spearman correlation between first-hour and last-hour returns is > 0.05.
- The first-hour positive bucket has a higher average last-hour return than the first-hour negative bucket.
- The positive-vs-negative last-hour average spread is positive in both chronological halves.

The secondary next-hour relationship is reported but does not determine pass/fail.

## Failure interpretation

If the primary criteria fail, do not rescue this hypothesis by changing bar windows, adding thresholds, using a different ETF, or switching to strategy returns. Any such change is a new hypothesis.
