# Alpaca IEX Order-Flow Predictiveness v1

Status: **FROZEN falsification scout**. This is not a Strategy, Experiment, paper-trading authorization, or claim about consolidated US order flow.

Machine-readable specification: `research_scout/alpaca_iex_orderflow_v1.json`.

## Question

During 09:35-10:30 ET, do five-minute IEX signed-trade imbalance and terminal quote-size imbalance contain stable, economically meaningful information about the next five-minute midpoint return in SPY, QQQ, and IWM?

The mechanism is short-horizon price impact and liquidity-provider inventory adjustment. Cont, Kukanov, and Stoikov (2014, DOI `10.1093/jjfinec/nbt003`) and Hasbrouck (1991, DOI `10.1111/j.1540-6261.1991.tb03749.x`) motivate the information-content question. They do not validate this venue-local implementation or imply that its effect survives execution.

## Frozen information and timing

- Feed: Alpaca Basic IEX historical trades and top-of-book quotes only.
- Symbols: SPY, QQQ, IWM. No substitutions after results are observed.
- Raw event window: 09:30:00-10:30:05 America/New_York; the final five seconds exist only to obtain the frozen one-second-delayed exit for the 10:25 signal.
- Signal timestamps: 09:35:00 through 10:25:00 at five-minute spacing.
- Target: next contiguous five-minute terminal-midpoint return.
- Trade classification: trade price versus the latest eligible normal quote strictly before the trade; equal-timestamp ordering is excluded.
- Quote classification older than two seconds is excluded from signed flow.
- Composite score: `0.5 * signed_trade_imbalance + 0.5 * terminal_quote_size_imbalance`.
- Selected observation: `abs(composite_score) >= 0.20`.
- Direction: sign of the composite score.
- No alternative frequency, holding period, score weighting, threshold, symbol, or session window is permitted after data are consumed.

## Frozen condition-code policy

Condition definitions were retrieved on 2026-07-10 from Alpaca's authenticated metadata endpoints:

- `GET https://data.alpaca.markets/v2/stocks/meta/conditions/trade?tape={A|B|C}`
- `GET https://data.alpaca.markets/v2/stocks/meta/conditions/quote?tape={A|B|C}`

Eligible trades must carry the tape-specific regular-sale marker and may carry only the following additional conditions:

- Tapes A/B: regular sale `" "` required; `E` automatic execution, `F` intermarket sweep, and `I` odd lot are allowed.
- Tape C: regular sale `@` required; `F` intermarket sweep and `I` odd lot are allowed.

Odd lots remain eligible because they are genuine observed IEX trades and may represent a material part of venue-local retail-sized flow. Opening/closing prints, late or out-of-sequence reports, crosses, average/derivatively priced trades, contingent trades, and other non-regular conditions are excluded.

Eligible quotes must be a normal, positive, uncrossed two-sided quote with condition set exactly `{R}` (regular open/two-sided open). Locked, crossed, one-sided, invalid, non-firm, manual/slow, opening, closing, and imbalance quotes are counted but excluded from feature state.

## Frozen sample and chronology

Each partition uses the second and last actual Wednesday trading session of each month according to Alpaca's calendar endpoint, giving 24 sessions per year. Exact dates are immutable in the JSON specification.

- Development: 2023.
- Internal validation: 2024.
- Final untouched holdout: 2025.

Only development may be consumed initially. Internal validation may be downloaded only if development clears every progression gate. The final holdout may be downloaded only if both earlier partitions pass without changing this specification.

This sampled design is an economical falsification scout, not a full population estimate. Passing it justifies a larger unchanged-specification study; failure terminates this branch.

## Frozen execution diagnostic

Midpoint return is the primary information-content target, not executable P&L. A separate venue-local diagnostic applies:

- signal known at interval boundary;
- entry at the first eligible IEX quote at or after boundary plus one second;
- exit at the first eligible IEX quote at or after five-minute target boundary plus one second;
- long enters at ask and exits at bid;
- short enters at bid and exits at ask;
- subtract an additional fixed two basis points per round trip after crossing the displayed IEX spread.

This remains an IEX-only proxy. It cannot establish normal Alpaca routing or NBBO execution quality.

## Frozen diagnostics

Report without variant search:

1. Spearman information coefficient for trade imbalance, quote imbalance, and the composite.
2. Selected-observation mean direction-signed midpoint return in basis points.
3. Directional accuracy.
4. Results by symbol and month.
5. Session-block bootstrap 95% confidence interval with 2,000 resamples and seed 42.
6. Result after removing the top 5% of sessions ranked by maximum absolute target return.
7. One-second-latency IEX crossing return and the same return after the additional two-basis-point friction.
8. Counts excluded by condition policy, quote state, staleness, and missing future execution quotes.

## Progression gates

A partition passes only if all are true:

- at least 100 selected observations;
- mean selected direction-signed midpoint return is at least 2.0 basis points;
- session-block-bootstrap lower 95% bound is above zero;
- mean selected direction-signed midpoint return is positive for each of SPY, QQQ, and IWM;
- mean remains positive after removing the top 5% of sessions;
- mean one-second-latency IEX crossing return remains positive after an additional two-basis-point round-trip friction.

No pooled t-statistic can override a failed economic or consistency gate.

## Terminal stopping rules

Stop this branch and do not open the next partition if any gate fails. Do not respond by testing nearby intervals, thresholds, score weights, individual stocks, technical filters, or machine-learning models. A failure means this frozen free-IEX implementation lacks enough robust evidence to justify further development.

A pass does not authorize a strategy. It permits only the next chronological partition with unchanged code and specification. Even a final holdout pass would require unchanged-feature replication on consolidated SIP/NBBO data before strategy construction or execution claims.
