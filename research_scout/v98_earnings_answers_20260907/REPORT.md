# V98: management's answers after earnings calls

Status: **aborted_conditional_upper_bound_failure**. This is one new fixed hypothesis and two diagnostic controls. No validated edge or deployment decision.

Required market inputs are missing on 5 evaluation dates. Full-calendar equity is unavailable; available-case returns are not a full backtest.

Even allowing perfect, costless low-to-high trades in the best eligible stock on every unknown day, the fixed run's ending-value ceiling is **$84.93**, versus **$132.40 for SPY**. Removing costs on the known days too gives a ceiling of **$95.67**. These are bounds, not measured final returns. The comparison is conditional on the cached daily ranges covering the missing prices and leaves the fitted available-data models unchanged.

![Backtest comparison](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/missing_day_bounds.png)

## What was tested

The proposed mechanism is delayed incorporation of information in management's answers to analysts. A small text model tests whether those answers add predictive value beyond prepared remarks, the company's identity, its opening gap, and the first half-hour stock and SPY returns. It does not use a language model pretrained on later company outcomes.

The training window begins in 2018. At each month in 2021–2023, both models are refitted using only earlier completed events. Each text block uses word unigrams and bigrams, a training-only vocabulary of at most 1,500 features, minimum document frequency 5, sublinear term frequency and L2 normalization. Both models use Ridge alpha 10 with identical fixed settings. There was no parameter or threshold search.

The augmented model adds a separate management-answer block to the prepared-remarks, ticker and price features. A stock is selected only when its augmented predicted log return exceeds the 5 bps each-way cost hurdle and exceeds the baseline model's prediction. All selected stocks share the day's capital equally. The baseline control trades its own forecasts above the same hurdle; the all-event control buys every eligible call. These controls are diagnostic comparisons, not independently discovered strategies.

## Information and execution clocks

A transcript is eligible at the first full XNYS session whose opening is strictly later than the publisher's later publication/modification time plus 30 minutes. Revisions that move that eligible session are excluded because the original text was not retrieved. Early-close dates are skipped. Only management's prepared remarks and answers after an analyst question enter the model; analyst questions, operator remarks, current-price page introductions, recommendations and surrounding disclosures do not.

The price features use the 09:30–09:55 five-minute bars, which finish at 10:00. One minute of processing makes the signal available at 10:01. Entry is the 10:05 bar open, and exit is the 15:55 bar open, in New York time. These are bar-reference scenarios: a bar's first qualifying trade is not a guaranteed executable quote. Historical split adjustment cancels in the within-day ratios; it does not establish original quoted price levels. The net scenario charges 5 bps on each side, with no additional invented spread or fee; the stress doubles those bps.

## Data actually collected

The fixed universe contains 132 existing stock symbols. All 72 monthly sitemaps for 2018–2023 were retrieved. There were 3,167 candidate URLs, 3,167 saved source pages, and 1,730 admitted events across 129 companies. Headline checks remove incidental ticker-word matches from URLs. The only issuer aliases were FB to META and GOOG to GOOGL; no merger predecessors were inferred.

| Event year | Admitted events |
|---|---:|
| 2018 | 195 |
| 2019 | 258 |
| 2020 | 406 |
| 2021 | 413 |
| 2022 | 250 |
| 2023 | 208 |

The price collection covered 805 historical date batches and 4,045 requested instrument-sessions, with 318,936 raw bars before regular-session filtering. Every response page was retained and hashed; pagination and exchange-session coverage were audited. Required event features were missing for 8 events and entry/exit labels for 7 events. The initial complete training sample had 857 events; there were 871 evaluation events before trade selection.

Exclusion counts below can overlap; they are data-admission reasons, not trading losses.

| Source admission issue | Documents |
|---|---:|
| headline ticker ambiguous or unmatched | 762 |
| unresolved speaker headers | 328 |
| management attribution not explicit | 297 |
| revision changes entry session | 240 |
| analyst roles unidentified | 222 |
| qa management text below 500 words | 154 |
| qa heading not unique | 90 |
| prepared management text below 500 words | 45 |
| participants heading not unique | 39 |
| ambiguous multiple issuer session documents | 6 |
| entry outside frozen period | 1 |

## Returns and controls

Products below use known days only where gaps remain. They are not full-calendar ending equity. Trade counts exclude unknown days; missing days are never assigned zero returns.

| Portfolio | Gross product on known days | Net product on known days | Doubled-cost product | Known trade days / stock trades | Known-day net drawdown |
|---|---:|---:|---:|---:|---:|
| Answers added (available cases only) | $81.63 | $72.47 | $64.34 | 119 / 178 | -30.54% |
| Prepared + prices (available cases only) | $94.78 | $81.09 | $69.38 | 156 / 270 | -29.15% |
| All eligible calls (available cases only) | $97.54 | $73.79 | $55.82 | 279 / 861 | -34.72% |
| SPY adjusted proxy | $132.40 | — | — | Held across full calendar | -24.50% |

Idle cash earns zero. All values start from $100 and assume fractional shares without borrowing. Where data are missing, the drawdown statistic covers the known-day product only, not the actual full-calendar path. None of these daily statistics measure intraday adverse excursions. SPY includes overnight exposure and an existing adjusted-price dividend proxy. This is the user's full-calendar objective, not a claim of equal market exposure or volatility.

| Year | Answers added, net | Prepared + prices, net | All eligible calls, net | SPY |
|---|---:|---:|---:|---:|
| 2021 | incomplete | incomplete | incomplete | 28.24% |
| 2022 | incomplete | incomplete | incomplete | -18.18% |
| 2023 | -10.53% | -5.80% | -13.82% | 26.18% |

On 864 paired forward events, adding the answer text increased mean squared forecast error by **0.34%**. Baseline MSE: 0.00027960; augmented MSE: 0.00028054. The median absolute change in the predicted log return was 3.60 bps. These are descriptive tests on exposed development history, not independent confirmation.

## Missing prices and the rejection bound

Nine targeted repeats of the original five-minute requests and nine one-minute requests through the same SIP access did not recover the required prices. The primary inputs and missing decisions were preserved. The bound protocol was saved before inspecting portfolio performance.

For each unknown portfolio day, the bound gives all capital to whichever eligible stock had the largest cached daily high/low ratio. It permits buying at the low and selling at the high even if their chronological order makes that impossible, charges no costs on that day, and also permits cash. Every funded long-only basket in the frozen universe is bounded above by that factor if the daily extrema cover its fills. Multiply those factors by the known-day portfolio factors; no missing price or actual return is imputed.

The daily files were already available locally and were hashed before use. Their OHLC ordering and range consistency with observed intraday bars were checked. This is not independent certification of a second vendor. The bound holds the already-fitted available-data model and known-day trades fixed; it does not bound a different model retrained on repaired observations or a different strategy.

| Portfolio | Known-day net product | Optimistic full-calendar ceiling | Ceiling with all costs removed | Unknown dates |
|---|---:|---:|---:|---:|
| Answers added | $72.47 | $84.93 | $95.67 | 5 |
| Prepared + prices | $81.09 | $95.03 | $111.07 | 5 |
| All eligible calls | $73.79 | $86.47 | $114.30 | 5 |

Primary unknown dates: 2021-04-19, 2021-04-20, 2021-09-22, 2021-10-25, 2022-01-24.

Even perfect, costless trading within the cached daily ranges on every unknown day cannot make the fixed available-data run beat SPY.

## What this result establishes

This is a conditional historical screen. The fixed universe was chosen retrospectively from existing files, and present-day publisher metadata does not independently establish original text vintages. Excluding revised or unparseable pages is retrospective sample selection. Complete share/cash accounting for the admitted corpus does not remove those biases. A failure rejects this exact implementation on the available sample; it does not prove that every way of analyzing earnings calls lacks an edge.

The declared economic objective governs the stop. If the net portfolio fails SPY, no different vocabulary, threshold, sign, timing, leverage or rescued variant is tried. Quotes, latency replay and 2024+ candidate outcomes are not opened after a clear failure. A positive conditional bar screen would still require incremental value, original source vintages, a point-in-time universe, executable quotes and fresh confirmation.

## Verification and provenance

Eleven focused tests passed before fitting real outcomes, covering text isolation, explicit management attribution, historical fitting, held-out vocabulary/target isolation, feature completion times, missing-data handling, calendar timing and independent share/cash arithmetic. Two additional tests check that the bound covers funded stock/cash baskets and rejects invalid extrema. The 35 monthly fits record their training ranges, event identity hashes, vocabularies, IDF hashes and coefficient hashes. Known-day share purchases and sale proceeds were reconciled independently with Decimal arithmetic for gross, net and stress products; actual full-calendar equity remains unknown where inputs are missing. All 45 protected historical input hashes remained unchanged.

The initial source enumeration omitted older conference-call and truncated slugs. It was repaired to use the publisher's transcript directory before any market outcomes. A source-only attribution audit then found that the legacy pilot parser could label researchers and reporters as management when their title omitted 'analyst'. An additional explicit-management-role gate now rejects those ambiguous documents. Both the original implementation freeze and its pre-outcome repair record are retained. A scheduling helper fetched already-complete training years while later text downloaded; final price collection reused only exact matching request parameters. These changes did not alter the frozen trading or model rules.

Public method/source references: [Motley Fool transcript source](https://www.fool.com/earnings/call-transcripts/2023/07/25/microsoft-msft-q4-2023-earnings-call-transcript/), [Alpaca historical-data access and bar conventions](https://docs.alpaca.markets/us/docs/market-data-faq), [historical bars API](https://docs.alpaca.markets/us/reference/stockbars), [Ridge regression documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html). These references support the data and method, not the strategy's profitability.

Local records:

- [specification.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/specification.json)
- [implementation_freeze.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/implementation_freeze.json)
- [implementation_freeze_repair_1.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/implementation_freeze_repair_1.json)
- [implementation_notes.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/implementation_notes.json)
- [source_summary.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/source_summary.json)
- [source_audit.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/source_audit.json)
- [market_request_plan.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/market_request_plan.json)
- [market_retrieval.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/market_retrieval.json)
- [market_coverage.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/market_coverage.json)
- [panel_audit.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/panel_audit.json)
- [model_audits.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/model_audits.json)
- [forecasts.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/forecasts.json)
- [primary_evaluation.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/primary_evaluation.json)
- [baseline_evaluation.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/baseline_evaluation.json)
- [all_events_evaluation.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/all_events_evaluation.json)
- [verdict.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/verdict.json)
- [minute_gap_probe_audit.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/minute_gap_probe_audit.json)
- [missing_day_bound_protocol.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/missing_day_bound_protocol.json)
- [missing_day_bound_inputs.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/missing_day_bound_inputs.json)
- [bounded_economic_verdict.json](C:/Hazem/quant_project/untitled_project/research_scout/v98_earnings_answers_20260907/bounded_economic_verdict.json)
