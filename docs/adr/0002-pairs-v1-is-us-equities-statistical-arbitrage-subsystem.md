# Pairs v1 Is a US Equities Statistical Arbitrage Subsystem

Pairs v1 is frozen as a US-equities-only statistical arbitrage subsystem rather than a simple StrategyTemplate clone. The old plan allowed intra-sector equities plus crypto spot pairs, but v1 deliberately excludes crypto and does not require sector data so the first experiment can test one clear hypothesis with the same liquid US equities universe used by CSMR and Momentum.

**Consequences**

- Pair discovery, Pair Relationship lifecycle, spread diagnostics, and active pair constraints are first-class parts of the subsystem.
- Pairs v1 uses top 150 liquid US equities, Engle-Granger cointegration (`p <= 0.05`), OLS log-price hedge ratio with intercept, 252-trading-day formation, monthly refit, z-score entry at `|z| >= 2.0`, exit at `|z| <= 0.5`, stop at `|z| >= 4.0` or 60 trading days, max 20 active pairs, one active position per symbol, and equal gross budget per pair.
- Crypto pairs, mandatory sector filtering, different thresholds, different lookbacks, and alternative sizing are future Experiments or subsystems, not improvements to Pairs v1.
