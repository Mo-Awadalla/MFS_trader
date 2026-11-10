# Trading-edge discovery — September 7, 2026

**The strongest new lead in this bounded review is slow incorporation of information in earnings-call answers. We have established partial access to the required public text, but have not established a predictive signal, profitable strategy, or SPY-beating portfolio. No new backtest was run.**

The research objective remains fully funded day trading, flat by the close, beating SPY total return after costs over the entire comparison calendar. The work used existing files and public websites, with no paid data, model API calls, orders, or subscription changes. It did not reopen earlier failed strategies or add another numbered hypothesis to the ledger.

## Why this lead merits investigation

An earnings release supplies headline numbers. Management's subsequent answers can add information about demand, margins, customer behavior, financing and uncertainty. The proposed mechanism is that interpreting those answers takes time, leaving some information unpriced when a later trade can actually enter. This is a hypothesis about information processing; we have not observed the counterparties, their inventories, or their reasons for trading.

There is supporting research, with material limits:

- Price, Doran, Peterson and Bliss report that conference-call tone, including Q&A, predicts subsequent abnormal returns. Their principal drift evidence extends over 60 trading days; it does not demonstrate our same-day objective. [Original 2012 study](https://www.sciencedirect.com/science/article/pii/S0378426611002901).
- Druz, Wagner and Zeckhauser examine managerial tone conditional on economic performance and speaker effects. That supports testing information beyond a firm's identity or reported numbers, rather than treating all optimistic language as a buy signal. [Authors' 2015 working-paper description](https://www.hks.harvard.edu/centers/mrcbg/publications/fwp/2015-05).
- A June 2026 preprint reports next-session intraday predictability from transcript sentiment. Its long/short construction, light cost sensitivity and model-training overlap require scrutiny before comparison with our funded long-only mandate. Its public repository currently contains a README saying code and data are coming soon, so independent reproduction is unavailable there. We did not adopt its reported returns as evidence of our performance. [Paper](https://arxiv.org/html/2606.29734v1), [repository](https://github.com/piqueyd/Fast-Numbers-Slow-Language).
- Evidence is not uniform. A 2024 study finds no measurable post-call drift in its group without environmental/social incidents, while finding conditional effects in another group. This argues against assuming a universal language premium. [Original study](https://www.sciencedirect.com/science/article/pii/S0929119924000476).

The eventual trading instruments would be **the individual stocks whose calls supply the information**. SPY remains the benchmark. This lead requires no automatic mapping of a company's disclosure to UPRO or SPXU.

The scoped archive search found no prior management-answer language test. Earlier SEC-CONT, V73, V85, V96 and V97 concerned filing events, breadth/peers, reporting schedules or numeric guidance. This is distinct from those measurements, but shares the broader earnings-information research exposure. No claim of originality in the academic literature is made. [Novelty search](C:/Hazem/quant_project/untitled_project/research_scout/edge_discovery_20260907/novelty_scan.json).

## What the free-data pilot established

Before retrieving the pilot text or calculating any sentiment score, a protocol fixed twelve companies and selected each company's earliest transcript URL in January–March 2021. The initial two Microsoft pages from 2023 were format-discovery examples and are kept separate. [Protocol](C:/Hazem/quant_project/untitled_project/research_scout/edge_discovery_20260907/discovery_protocol.json), [selection manifest](C:/Hazem/quant_project/untitled_project/research_scout/edge_discovery_20260907/pilot_manifest.json).

The twelve requested companies span nine sector categories. **Eleven pilot transcripts were retrieved. Ten passed the parser's structural checks. Nine both passed those checks and had no publication-versus-modification difference that changed the next eligible entry session.** Those nine are AAPL, CVX, JNJ, JPM, LIN, MSFT, NEE, PG and XOM. These are source-format observations, not nine successful trades or a representative coverage estimate.

The parser retains management remarks, analyst questions, management answers and their speaker associations separately. It rejects unidentified speakers, ignores ordinary speech dashes as speaker boundaries, and excludes the page introduction and surrounding material. The introduction contains a changing stock-price percentage: feeding the whole webpage into a model would risk contaminating historical features with later information.

Specific findings:

- **WMT:** the page was published February 19, 2021 at 01:30 Eastern and modified February 22 at 21:48:07. With an illustrative 30-minute buffer followed by the next full-session open, the current version belongs to February 23, not February 19. The current page cannot establish what the earlier version said. Its URL also says Q4 2020 while the headline says Q4 2021; URL slugs alone cannot identify fiscal periods. [Publisher page](https://www.fool.com/earnings/call-transcripts/2021/02/19/wal-mart-stores-inc-wmt-q4-2020-earnings-call-tran/).
- **AMT:** the original text has an unidentified speaker, so the parser flags attribution as incomplete. AMT also has no daily SIP file in the pilot's selected local directory. Neither problem is treated as a neutral signal. [Publisher page](https://www.fool.com/earnings/call-transcripts/2021/02/25/american-tower-amt-q4-2020-earnings-call-transcrip/).
- **CAT:** no matching transcript appeared in the three monthly publisher sitemaps. Targeted public search did not resolve that pilot entry. This is a gap in this source/sample, not proof that no transcript exists elsewhere.
- **Publication delay:** across the eleven retrieved pilot pages, publication was approximately 5–17.5 hours after the stated call start. These are not measured lags after call completion. A call-start timestamp cannot authorize using the complete transcript.

The dates above are publisher metadata observed today. They are useful for an explicitly labelled historical screen, but are not independently archived proof of each original version or its first availability. Broad universe coverage and historical version fidelity remain unresolved. [Parser audit](C:/Hazem/quant_project/untitled_project/research_scout/edge_discovery_20260907/pilot_audit.json), [timing audit](C:/Hazem/quant_project/untitled_project/research_scout/edge_discovery_20260907/publication_timing_audit.json).

A separate public Hugging Face corpus advertises roughly 33,000 transcripts and structured speakers. Its documented date field is the call date, and its schema does not provide original transcript-publication or revision timestamps. It can help discover text, but does not by itself solve execution timing. Only its metadata/card were retrieved; the bulk corpus was not downloaded. [Dataset card](https://huggingface.co/datasets/kurry/sp500_earnings_transcripts).

## Economics before another backtest

The known 2021–2023 comparator is $100 → $132.3969. For a fully invested portfolio on each selected day and zero idle-cash interest, the following geometric averages would merely equal that comparator:

| Invested days during those three years | Required net gain per invested day | Required gross gain with 5 bps cost each way |
|---|---:|---:|
| 100 | 28.10 bps | 38.14 bps |
| 250 | 11.23 bps | 21.25 bps |
| 500 | 5.61 bps | 15.62 bps |

One basis point is 0.01%. These are arithmetic hurdles, not measured returns or forecasts. Cash days remain in the comparison. Actual volatility, concentration, incomplete investment and execution costs matter; positive average event returns alone would not establish a successful portfolio. The pilot is too small and selected for source diversity to estimate strategy frequency. [Calculation and assumptions](C:/Hazem/quant_project/untitled_project/research_scout/edge_discovery_20260907/opportunity_hurdles.json).

## Concrete research decision

Advance **one information hypothesis** to measurement design: can the content of management's answers predict additional same-day stock returns beyond prepared remarks and information already reflected in price?

Before a new trading test, the necessary work is a dated event panel with coverage failures retained, a fixed and independently checked way to extract the information, and a frozen entry/exit and selection rule. Historical scoring must avoid a model that can simply recall later company outcomes. A simple frozen text model or a model trained only on earlier samples is a valid candidate method; neither has yet been selected or trained here. Ticker/management identity, prepared remarks, and pre-entry price response belong in the controls. Predicting volatility alone does not satisfy the objective.

The first economic screen would use long stock baskets and same-day exits under the existing accounting contract. A surviving result would still require quote evidence, capital and capacity checks, selection-bias treatment, and fresh confirmation. If the verified result clearly fails the SPY objective, abort it without timing searches or sign reversals. We should not infer that missing original text is harmless, or that this small pilot warrants a large model or data purchase.

Generic leveraged-fund rebalancing was not advanced: it overlaps existing tests, and V63 already demonstrated that its chosen flow construction mostly duplicated momentum. The literature also gives reasons capital flows can offset predicted rebalancing demand. [Repository evidence](C:/Hazem/quant_project/untitled_project/research_scout/postmortem_20260907/hypothesis_ledger.json), [Federal Reserve research description](https://www.federalreserve.gov/econres/feds/2014.htm).

## Verification and retained artifacts

The task retained thirteen transcript pages in total: eleven fixed pilot pages and two earlier Microsoft format probes. Three monthly sitemap files and three research/dataset metadata files were also cached. Raw inputs have retrieval logs and hashes; parsed text is separate. No credentials or account configuration were read or changed.

Four focused tests passed: exclusion of later page material and analyst text; rejection of unknown speaker attribution; handling of revised/naive timestamps; and explicit analyst-role recognition when names differ from the participant list. Targeted lint passed. The eleven existing local price-file hashes remained unchanged. The final [discovery verdict](C:/Hazem/quant_project/untitled_project/research_scout/edge_discovery_20260907/discovery_verdict.json) distinguishes partial source readiness from signal quality, economics and validation.
