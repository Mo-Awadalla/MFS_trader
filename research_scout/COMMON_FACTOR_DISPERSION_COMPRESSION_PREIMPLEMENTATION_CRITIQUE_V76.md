# Common-Factor Dispersion Compression: Preimplementation Critique v76

## Hypothesis

An unfinished basket/program order should make the common index factor more
important relative to idiosyncratic stock news.  For the frozen large-cap
universe, compare the cross-sectional median absolute deviation of nonoverlapping
first- and second-half-hour returns.  If dispersion strictly falls while both
SPY half-hours have the same nonzero sign, trade that sign from 10:31 to 15:55.

This is not V75 breadth acceleration: it uses compression of cross-sectional
return dispersion and a two-half SPY path, not counts of positive/negative
names.

A desk could take the common-factor interpretation seriously, but prices still
do not identify the initiator, static membership is biased, and IEX is
venue-local.  Reject before P&L unless signals exceed 2/week and 100/year,
directions are balanced, odd/even half-universe actions agree at least 70%, the
rule selects 20–80% of sessions, overlap with V75 signal dates is at most 80%,
and quote/source gates pass.

No dispersion threshold, volatility scaling, universe deletion, sign inversion,
UPRO-only sleeve, alternate clock, or regime filter is allowed.
