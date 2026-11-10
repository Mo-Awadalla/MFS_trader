# Final Cash-ETF Data Blocker Audit v33

## Final determination

No strategy in the available non-futures data qualifies as desk-grade under
the frozen requirements. The result is not “day trading cannot work” and not
“leveraged ETFs never contain opportunity.” The proven boundary is:

> With the current minute bars, sampled BBOs, sparse event panels, and daily
> cross-asset files, every frequent and feed-stable causal quantity tested
> either lacked predictive expectancy, failed later years, failed marketable
> execution, depended on a few winners, or could not beat passive SPY.

The current history is now too researched to justify further transformations
of the same observables. A new result obtained by changing signs, clocks,
thresholds, sides, controls, or execution assumptions after these outcomes
would be a selection artifact. Meaningful progress requires a new causal field
or genuinely new forward data.

Futures-derived signals are excluded from this conclusion and from the final
search passes because the user specified a cash account without futures
margin.

## Requirement-by-requirement completion audit

### Explain the hypothesis before implementation

Satisfied as a research-process requirement. Every late-stage candidate was
written and criticized before outcomes:

- v31: ordered ownership traversal between prior closing and current opening
  accepted-value anchors;
- v32: BTC spot flow coherence as a state sensor, with the SPY cash gap as the
  asset-specific direction;
- v33: same-issuer SH/SPXU proportional-spread curvature as the incremental
  price of leveraged downside liquidity.

Each critique explicitly recorded why the idea might work, why it might fail,
the “elite desk” test, frozen clocks/signs, and prohibited repairs.

### At least two trades per week

This was not the general blocker:

- v29: 4.73/week;
- v32: 2.73/week;
- v33: 4.48/week;
- multiple earlier activity, flow, variance, and cross-market rules also
  exceeded 2/week.

Rare structural objects failed honestly before P&L:

- v23: about 0.10/week;
- v31: 0.67/week despite 100% cross-feed direction agreement.

No sparse candidate was widened after its cadence was known.

### Cash-only $100 UPRO/SPXU implementation

Satisfied in every executable test:

- long fractional UPRO or SPXU only;
- at most $100 deployed;
- no account leverage, short sale, futures, or overnight ETF holding;
- observed ask entry and observed bid exit;
- invalid or missing quotes canceled rather than forward-filled.

### Observed execution and stress

The v30 signal-free actuator diagnostic established the hurdle over 2021–2025:

| Sleeve, 10:31–15:30 daily | Fixed-$100 P&L | Compounded ending cash | Midpoint ending cash | Mean spread drag |
|---|---:|---:|---:|---:|
| UPRO | +$65.20 | $146.13 | $201.03 | 2.58 bps |
| SPXU | −$177.93 | $12.68 | $28.67 | 6.61 bps |
| Passive SPY | — | $181.68 | — | price-only hurdle |

This proves:

- gross UPRO opportunity exists;
- repeated executable crossings erase enough of it to trail SPY;
- SPXU combines materially higher spread drag with inverse-fund decay;
- a symmetric classifier needs exceptional downside timing, not modest
  directional accuracy.

Every admitted strategy was also subjected to an extra cent at both fills and
a multi-minute delayed entry. Candidates that were profitable only at
midpoints were rejected.

### Positive every development year and on both sleeves

No late-stage frequent candidate passed.

The final independent challenges were unambiguous:

| Candidate | Fixed P&L | 2021 | 2022 | 2023 | UPRO | SPXU |
|---|---:|---:|---:|---:|---:|---:|
| v29 SPY value/price phase lag | −$48.03 | +$1.35 | +$0.29 | −$49.67 | +$22.81 | −$70.84 |
| v32 BTC attention × SPY gap | −$30.58 | +$40.84 | −$12.56 | −$58.85 | +$18.24 | −$48.82 |
| v33 inverse leverage-liquidity curve | −$59.08 | −$40.82 | −$11.52 | −$6.74 | +$17.69 | −$76.78 |

Deleting SPXU now would select a known favorable sleeve. It is not a new
long-only hypothesis.

### Cross-feed identification

Measurement noise was separated from economic failure:

- v31: 100% direction agreement, 96.4% identical actions, but only 0.67/week;
- v32: 99.5% direction agreement, 99.7% identical actions, then −$38.89 on
  the independent development overlap;
- v33: 96.4% direction agreement, 95.8% identical actions, then −$27.69 on
  the independent development overlap.

Thus the final failures cannot be dismissed as ARCA-only signal instability.
Earlier candidates such as v25 and v28 were rejected before P&L precisely
because their actions were not feed-stable.

### Winner concentration

This remained binding even for unconditional UPRO:

- always-UPRO 2021–2025 fixed P&L: +$65.20;
- after deleting its ten best sessions: −$28.81.

Examples among candidate strategies:

- v16: +$60.32 became −$5.69 without ten winners;
- v20: +$48.02 became −$2.14 without ten winners;
- v29: −$48.03 became −$118.89;
- v32: −$30.58 became −$85.62;
- v33: −$59.08 became −$128.11.

No tail-dependent candidate was called robust.

### Outperform passive SPY

The price-only hurdle was:

- $100 → $126.66 in 2021–2023;
- $100 → $181.68 in 2021–2025.

This understates the real hurdle because dividends were not reinvested.
Positive fixed-notional P&L alone was never treated as success.

No candidate surviving the other gates also beat SPY in development and
untouched later years.

### Holdout integrity

Later years were opened only after all frozen development gates passed.
Examples of honest failures:

- v5 Silence Entropy passed development and failed 2024–2025;
- v10 flow geometry was strong in development and failed holdout;
- v11 Breadth Consensus looked strong in development and failed the SPY
  holdout hurdle;
- the opening-center benchmark passed development and lost in both 2024 and
  2025.

V26, v29, v32, and v33 failed development, so their holdouts remain sealed.
No failed development rule was repaired with later-year feedback.

## Final independent challenge: v33

V33 was selected because it was the last observable not reducible to a prior
test:

- SH and SPXU share issuer and downside factor;
- their −1×/−3× proportional-spread ratio forms an internal leverage curve;
- the time change in that curve was hypothesized to price convex downside risk
  capacity.

The measurement was unusually strong:

- 738/738 valid development measurements;
- 699 returns-blind executable signals;
- 4.48 entries/week;
- 339 UPRO and 360 SPXU;
- 96.4% cross-feed direction agreement;
- 95.8% identical actions.

The economics were decisively wrong:

- observed-BBO fixed P&L: −$59.08;
- compounded cash: $46.24;
- profit factor: 0.902;
- every development year negative;
- extra-cent stress: −$120.73;
- five-minute delay: −$67.01;
- without ten best trades: −$128.11;
- independent-feed overlap: −$27.69.

The exact sign flip also lost $7.42, failed 2022 and 2023, trailed SPY, and
became −$76.55 without ten winners. Therefore the result does not hide an
invertible anomaly.

## Why the remaining apparent ideas are not valid experiments

### Invert or keep only UPRO from a failed rule

This uses observed outcomes to choose sign or sleeve. V32 and v33 both showed
the recurring UPRO-positive/SPXU-negative pattern already quantified by v30.
Selecting it now is actuator drift, not evidence that the signal predicts.

### Fit a spread, volume, distance, or event threshold

The cutoff would be chosen from already observed winners and losers. The
available history has supported dozens of related transformations; another
threshold has an uncontrolled false-discovery rate.

### Replace marketable fills with midpoint or limits

One-minute BBO does not observe queue position, passive fill probability, or
counterfactual execution. This would manufacture an edge by assumption.

### Test wrapper convergence at one-minute resolution

Liquid SPY/leveraged-ETF discrepancies are event-time and queue-time objects.
Minute snapshots cannot establish that a stale quote remained executable after
the signal was known.

### Infer fund hedging from ETF price or unsigned volume

Without AUM, shares outstanding, creations/redemptions, basket files, iNAV, or
derivative hedge flow, the primary-market imbalance is unidentified.

### Mine static daily constituents or cross-asset gaps

The stock collection lacks point-in-time S&P membership, creating survivorship
bias. Daily ETF open/close gaps also contain distribution and asynchronous
opening-print effects without a corporate-action feed. A high-end desk would
not accept those as clean intraday macro shocks.

### Combine failed candidates

Choosing a portfolio or voting rule after seeing component P&L compounds
selection bias. No orthogonal untouched holdout remains to validate the
combination.

## Exact data additions that would reopen research

At least one of these is required for a genuinely new causal experiment:

1. historical intraday iNAV/NAV, AUM, shares outstanding, and
   creation/redemption basket files for UPRO/SPXU;
2. synchronized consolidated event-level trades and quotes for SPY, UPRO,
   SPXU, and SH with exchange identifiers and quote conditions;
3. official opening/closing auction imbalance messages and auction prints;
4. point-in-time S&P 500 membership with timestamped constituent trades and
   quotes;
5. options surface, option flow, and greeks data to identify dealer gamma
   without requiring the account to trade options;
6. order-book/message data sufficient for queue-aware passive execution;
7. genuinely new forward sessions reserved before any further rule design.

## Conclusion

The current blocker is genuine and data-imposed:

- ex-post opportunity is abundant;
- frequent signals are easy to construct;
- measurement-stable signals are possible;
- but the fields that would identify institutional inventory, primary-market
  pressure, dealer gamma, auction imbalance, or executable event-time
  convergence are absent.

Further backtests on the same minute bars would increase creativity of the
representation without increasing information. The scientifically correct
next step is new causal data or a preregistered forward sample—not another
historical transformation.
