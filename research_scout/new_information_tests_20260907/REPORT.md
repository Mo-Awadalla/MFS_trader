# New filing-information tests — September 7, 2026

**Current position: no new strategy qualifies. V96 failed the development economics; V97 stopped at data feasibility before a return was calculated. V97's profitability remains unknown.**

These are two new information hypotheses. No earlier strategy was reopened. The rules and original input hashes are preserved in [specification.json](C:/Hazem/quant_project/untitled_project/research_scout/new_information_tests_20260907/specification.json). The authorized inputs were existing files plus free public data; no new data purchase or trading order was made.

| Hypothesis | What it would trade | Result | Disposition |
|---|---|---|---|
| V96: unexpectedly early periodic reporting | Equal-weight stocks whose original 10-Q or 10-K arrives at least five calendar days earlier than their own comparable prior-year reporting schedule | $100 → **$101.79 net**, versus **$132.40 SPY**; 97 filing signals over 83 trading days | Abort: development economic failure |
| V97: upward annual adjusted-EPS guidance revision | Equal-weight ABBV, AMGN, CVS, LLY and UNH when management raises the midpoint of a comparable same-year forecast | Ten pilot releases read successfully; the intervening forecast history could not be certified | Abort: data feasibility; **no backtest return** |

## V96: completed and independently checked

The development interval is January 4, 2021 through December 29, 2023: 753 exchange sessions, including 670 cash days. The stock universe consists of 132 existing SEC/daily-price symbols, with GOOG removed to avoid duplicating Alphabet. Selection uses filing timing and fiscal report dates; it has no price-pattern filter.

Each current filing is matched to the same form with a fiscal report date 350–380 days earlier, known before current acceptance. The match closest to 365 days is used, with a deterministic accession tie-breaker. Duplicate original filings for the same issuer/form/report date and unusable reporting lags are excluded. Amendments do not qualify.

The signal becomes available at SEC acceptance plus a 30-minute processing buffer. Entry is at the first full NYSE session open strictly after that time; exit is at the same session's 16:00 New York close. Early-close sessions are excluded prospectively. The portfolio is fully funded, uses fractional shares and equal weights within each day's basket, and holds cash outside those positions. SEC acceptance is a conservative information-availability bound; it is not assumed to be the first public earnings announcement.

| Development result | Ending value from $100 | Total return |
|---|---:|---:|
| Stock strategy, frictionless daily-bar reference | $110.60 | +10.60% |
| Stock strategy, 5 basis points adverse cost on each side | $101.79 | +1.79% |
| SPY adjusted-price total-return proxy, full calendar | $132.40 | +32.40% |

All 97 selected event legs had valid daily prices. The strategy's net maximum daily drawdown was 20.02%. Even the frictionless reference trailed SPY by 21.80 percentage points, so this is a clear failure for the stated objective. The rule did not generate enough same-day gains. Signal frequency is reported here as a result, not used as an additional pass/fail threshold.

The independent audit checked all 1,570 comparable filing records against raw SEC fields, validated the selected flags and first eligible session, and rebuilt the 97 legs using separate Decimal share/cash accounting. Its ending values differed from the evaluator by less than $0.000000000002. Original source hashes remained unchanged. See [independent_verification.json](C:/Hazem/quant_project/untitled_project/research_scout/new_information_tests_20260907/independent_verification.json), [V96_verdict.json](C:/Hazem/quant_project/untitled_project/research_scout/new_information_tests_20260907/V96_verdict.json) and [V96_evaluation.json](C:/Hazem/quant_project/untitled_project/research_scout/new_information_tests_20260907/V96_evaluation.json).

The evaluation's routine cost-stress and paired-bootstrap fields are retained in the JSON. Following the economic failure, no control portfolio, later-period evaluation or rescue variant was run.

Limitations: the stock universe is a static survivor sample, daily open/close prices are execution references rather than observed executable quotes, and the cached Yahoo adjusted-price benchmark is labelled a legacy total-return proxy. The development history has been exposed in prior research and is not fresh confirmation data. These limitations prevent a deployment claim; the frictionless shortfall already justifies stopping this candidate.

## V97: data feasibility failed before economics

The frozen hypothesis requires the **most recent previously public** annual adjusted-EPS range for the same issuer, fiscal year, currency, units and accounting basis. Initial forecasts, one-sided ranges, withdrawals and incomparable definitions do not qualify. The intended entry, exit, capital and cost assumptions match V96.

All ten predeclared pilot documents—the earliest two 2021 Item 2.02 releases per issuer—were retrieved and their annual EPS ranges checked. The original CVS pilot PDF's guidance page was also rendered and visually inspected. [V97_pilot_extraction.json](C:/Hazem/quant_project/untitled_project/research_scout/new_information_tests_20260907/V97_pilot_extraction.json) retains the numeric facts, source hashes and matched filing acceptance times. Those extracted facts are not a certified trade list.

The wider history check exposed two problems:

1. **Intervening disclosure gaps.** Across the cached expanded scope of 236 Form 8-K records, 127 Item 2.02/7.01 primary documents were requested through the public web tool; 75 returned content and 52 did not. Several of those 52 are covered by issuer releases or separately indexed exhibits, so they must not be counted as 52 missing guidance events. However, specific intervening disclosures remain unresolved. One is UNH's March 8, 2021 disclosure, between its two pilot reports; others include CVS's June 9 and September 13, 2022 disclosures. Their contents cannot be assumed to leave guidance unchanged. The exact URLs and retrieval status are in [V97_coverage_audit.json](C:/Hazem/quant_project/untitled_project/research_scout/new_information_tests_20260907/V97_coverage_audit.json).
2. **Quarterly tables alone can misstate the information change.** Lilly's November 2, 2021 release estimated an additional approximately $0.25 of 2021 EPS from a government purchase. Its December 15 comparison table still printed the older quarterly range as the prior forecast. Treating that table as an unbroken public history could misclassify the subsequent update. See the [November announcement](https://investor.lilly.com/news-releases/news-release-details/lilly-supply-614000-additional-doses-bamlanivimab-and-etesevimab) and [December guidance release](https://investor.lilly.com/news-releases/news-release-details/lilly-highlights-innovation-based-growth-strategy-and-pipeline). Changes to non-GAAP accounting definitions were also found, including Amgen's treatment of development expenses and CVS's treatment of realized capital gains/losses. These require explicit comparability checks, as illustrated in [Amgen's 2022 release](https://www.amgen.com/newsroom/press-releases/2022/11/amgen-reports-third-quarter-2022-financial-results) and [CVS's 2023 release](https://investors.cvshealth.com/news/news-details/2023/CVS-HEALTH-REPORTS-FIRST-QUARTER-RESULTS-COMPLETES-ACQUISITIONS-OF-SIGNIFY-HEALTH-AND-OAK-STREET-HEALTH/default.aspx).

The retrieval effort covered issuer HTML/PDF archives, indexed SEC primary and exhibit pages, targeted searches, and two complete-submission alternatives. A direct transparent SEC HTTP request returned 403; it was not retried with a disguised identity. The existing environment has no configured identified SEC contact user-agent. These are current retrieval limitations, not a claim that the documents do not exist or require a paid subscription.

Under the frozen feasibility stop, V97 is closed for this batch without calculating P&L or treating missing information as a no-signal day. Redefining the rule as a comparison with the previous quarterly table would change the hypothesis. See [V97_verdict.json](C:/Hazem/quant_project/untitled_project/research_scout/new_information_tests_20260907/V97_verdict.json).

## Assets retained and checks

The task added **69 public issuer documents: 66 HTML releases and three PDFs**, with extracted text, publication labels, URLs and hashes. Separately preserved web responses contain filing, exhibit and source-discovery evidence. [public_document_inventory.json](C:/Hazem/quant_project/untitled_project/research_scout/new_information_tests_20260907/public_document_inventory.json) indexes the local corpus. It is useful new research material, but it is not yet a complete point-in-time guidance-event feed.

Two focused tests cover the processing buffer/early-close calendar and prior-year matching/ambiguous filing exclusions. Independent source and accounting verification passed. Targeted lint checks passed. Pytest reported one cache-directory permission warning; both tests passed. No 2024+ strategy returns were read for these candidates, and neither candidate advanced to trading or promotion.

The scripts and evidence are reproducible within the existing environment. Use `python -m research_scout.verify_new_information_20260907` to audit the closed V96 artifacts; `python -m research_scout.finalize_information_data_20260907` audits the public-source inventory and records the V97 data stop without reading price data. The development backtest script is retained for provenance; it should not be reopened as another candidate.
