# Institutional Systematic Strategy Candidates v1

## Executive conclusion

Outcome update: the cross-asset futures carry-plus-trend candidate identified here was subsequently frozen, implemented on the pinned public pysystemtrade panel, independently audited, and passed all 13 scout gates. Its next permitted step is raw-contract replication, not deployment. The point-in-time earnings-revision candidate remains blocked by data-vintage availability.

Large trading firms disclose business categories, research themes, and sometimes client-facing index rules. They generally do not publish the production signals, features, parameters, execution logic, or portfolio interactions that generate proprietary trading profits.

The most reproducible public material comes from two different groups:

1. Systematic asset managers such as AQR and Man AHL publish factor research on trend, carry, quality, value, and momentum. The research mechanism and sometimes factor data are public; the live implementation is not.
2. Dealer banks publish exact methodologies for client-facing quantitative investment strategy indices because notes and other products are linked to them. Those rules are public product specifications, not evidence that the bank's proprietary or market-making books trade the same strategy profitably.

Jane Street, Optiver, Hudson River Trading, Citadel Securities, IMC, and similar firms publicly describe quantitative market making, liquidity provision, pricing, hedging, execution, statistical modeling, and machine learning. Their actual short-horizon strategies remain proprietary and depend heavily on infrastructure, exchange access, transaction-cost advantages, inventory netting, and order-flow information. Those businesses are not realistic strategy templates for this repository.

Using the lessons from the failed reversal experiments and the repository's prior evidence, the best next candidates require new point-in-time data rather than another OHLCV window:

1. Point-in-time earnings surprise and analyst-revision continuation
2. Point-in-time profitability/quality plus medium-term momentum
3. Cross-asset futures carry plus trend
4. Announced all-cash merger arbitrage
5. Public index-reconstitution flow

There is no strong new institutional-style candidate that can be tested honestly using only the current static active-stock Alpaca panel. The best use of effort is a data-feasibility spike, not immediate strategy implementation.

## What institutions publicly disclose

### Jane Street and electronic market makers

Jane Street describes itself as a global liquidity provider and market maker using quantitative analysis, market mechanics, machine learning, and human judgment. It states that it trades continuously on more than 200 electronic exchanges and is active in ETFs, equities, bonds, and options. Its client offering emphasizes cross-asset liquidity, electronic execution, pricing, and proprietary technology.

Publicly disclosed strategy families:

- ETF and cross-asset market making
- Electronic liquidity provision
- Quantitative pricing and hedging
- Machine-learning-supported modeling
- Client execution

Not public:

- Forecast features and targets
- Fair-value models
- Inventory and hedging rules
- Venue-routing logic
- Holding periods and thresholds
- Production model parameters

Sources:

- https://www.janestreet.com/what-we-do/overview/
- https://www.janestreet.com/what-we-do/client-offering/

### Optiver, HRT, Citadel Securities, and similar firms

Optiver publicly describes model-driven price discovery, machine learning, liquidity provision, execution, and risk management across more than 100 exchanges and more than one million instruments. HRT describes itself as a multi-asset quantitative liquidity provider with advanced research, modeling, computing, and risk-management infrastructure.

These disclosures establish what the firms do at a business level. They do not provide a reproducible strategy. Their short-horizon edge is inseparable from low transaction costs, co-location and connectivity, queue position, real-time cross-venue state, order-book data, and integrated hedging.

Sources:

- https://www.optiver.com/what-we-do/
- https://www.hudsonrivertrading.com/
- https://www.citadelsecurities.com/what-we-do/

### AQR and systematic factor managers

AQR publishes substantially more useful research because many systematic asset-management returns are built from durable, diversified risk premia rather than secret microsecond signals.

Public examples include:

- Time-series momentum: an instrument's own trailing 12-month excess return positively predicts its future return across equity-index, currency, commodity, and bond futures.
- Quality Minus Junk: profitable, growing, safer, well-managed companies historically earned higher risk-adjusted returns than low-quality companies.
- Carry: expected return assuming market conditions and spot prices remain unchanged predicts returns across several asset classes.

AQR publishes papers and, for some strategies, research factor datasets. Its exact production portfolios, transaction-cost models, constraints, execution, and current signal ensemble are not public.

Sources:

- https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk
- https://www.aqr.com/Insights/Research/Journal-Article/Carry

### Man AHL

Man AHL publicly identifies itself as a systematic manager applying research and technology to hundreds of global markets. It publishes extensive trend-following research, including market selection, equity trend following, and research workflows. The strategy family is public; production rules and the complete model ensemble are not.

Source:

- https://www.man.com/ahl

### Goldman Sachs and bank QIS indices

A useful exception to strategy secrecy is the client-facing quantitative investment strategy index. The methodology must be disclosed because notes and other products are linked to the index.

A Goldman Sachs SEC filing for the Momentum Builder Multi-Asset 5S ER Index describes a rules-based index that searches combinations of 15 underlying assets over nine-, six-, and three-month return lookbacks, applies asset and asset-class constraints, limits realized volatility, and can rebalance daily into a money-market position when its volatility cap is exceeded.

This is genuinely public systematic logic. It is not proof that Goldman's proprietary desks use the same rules or that the index delivers alpha after product fees. The filing also distinguishes historical information from hypothetical backfilled index data.

Source:

- https://www.sec.gov/Archives/edgar/data/886982/000156459021045738/gs-424b3.htm

### Two Sigma, D. E. Shaw, Renaissance, and multi-strategy hedge funds

These firms publicly discuss quantitative research, machine learning, data science, systematic investment management, and sometimes broad asset classes. Exact production strategies are not public. Quarterly regulatory holdings are delayed, omit shorts and many derivatives, and do not reveal signals or execution. Job descriptions and patents reveal capabilities, not investable rules.

## What is actually public?

| Material | Public? | Reproducible? | What it proves |
| --- | --- | --- | --- |
| Market-making business description | Yes | No | The firm provides liquidity and uses quantitative technology |
| Academic/factor paper | Yes | Partly | A historical mechanism and research construction existed |
| Research factor dataset | Sometimes | Research-level | The published factor can be independently checked |
| Bank QIS index methodology | Often | Usually, with sufficient data | A client product follows disclosed rules |
| Mutual fund/ETF prospectus | Yes | Partly | Objective and broad process, not every production detail |
| 13F holdings | Yes, delayed | No | A stale subset of long US equity positions |
| Hedge-fund production alpha model | No | No | Nothing reliable can be inferred from marketing descriptions |

Public does not mean profitable. Public rules are often commoditized risk premia, portfolio products, or research examples. Institutional advantages frequently reside in data quality, portfolio interaction, financing, capacity, execution, and risk management rather than in one formula.

## Repository evidence that constrains candidate selection

The repository has already consumed several nearby hypotheses:

- ETF time-series momentum and volatility targeting passed validation, but had lower CAGR and final wealth than SPY while delivering higher Sharpe and much smaller drawdown. It is a defensive allocator, not a SPY-return challenger.
- ETF tactical momentum failed validation. Selecting a better adjacent `top_n` result after seeing the run was correctly rejected as tuning.
- Residual volatility-managed cross-sectional momentum failed decisively.
- Residual reversal and SEC-event-conditioned five-day reversal failed gross-signal tests.
- Opening-range breakout and several intraday scouts failed or are already represented by frozen experiments.

Consequences:

1. Do not test another ETF trend lookback or Goldman's three/six/nine-month variation on the same ETF sample merely because the bank rule is public.
2. Do not add another short-term reversal filter.
3. Do not prioritize generic intraday OHLCV patterns after several independent failures in that family.
4. Prefer a new economic mechanism that requires the exact point-in-time data defining the signal.

## Ranked candidate hypotheses

These are candidate research briefs, not finalized strategy specifications. Every candidate still requires a data audit and a frozen source memo before any backtest.

### 1. PointInTimeEarningsRevisionDrift-v1

Priority: highest if point-in-time consensus data can be acquired.

Institutional family: earnings momentum, analyst revisions, post-announcement drift, event-driven equity alpha.

Hypothesis:

> Stocks with genuinely positive earnings surprises and upward revisions to future consensus estimates continue to outperform stocks with negative surprises and downward revisions after the information becomes public. A sector-neutral portfolio formed only from timestamped, point-in-time surprise and revision data should earn positive one-month forward Rank IC and after-cost low-beta returns.

Why this is materially different:

- It predicts continuation after fundamental information rather than reversal of unexplained price moves.
- It uses the actual fundamental variable that the SEC filing-presence proxy failed to measure.
- Holding periods are measured in weeks rather than one or two sessions.

Required exact data:

- Point-in-time analyst consensus snapshots and revisions
- Reported EPS and the consensus that existed immediately before release
- Earnings announcement date and before-open/after-close timestamp
- Historical universe membership, delistings, and corporate actions
- Sector and size classifications available at the time

Potential frozen shape after data audit:

- Historical liquid large-cap universe
- Signal becomes tradable only after the first executable session following the release or revision timestamp
- Equal combination of standardized earnings surprise and subsequent consensus revision
- Sector-neutral top-versus-bottom quintile
- One-month holding with overlapping cohorts; no post-result holding-window search

Cheap falsification gates:

- Expected-sign one-month Rank IC is positive overall and in both chronological halves
- Gross long-short spread is positive before costs
- Results are not concentrated in the announcement session or a handful of names
- Drift-adjusted turnover and default costs leave positive alpha
- A predeclared SPY sleeve improves Sharpe without relying on market beta

Main risk: point-in-time consensus history is usually licensed and expensive. Current SEC filing metadata cannot substitute for it.

### 2. PointInTimeQualityProfitabilityMomentum-v1

Priority: highest long-only SPY-challenger candidate after acquiring historical fundamentals and membership.

Institutional family: AQR quality, profitability, medium-term momentum, systematic active equity.

Hypothesis:

> Among historical large-cap US stocks, companies with high point-in-time gross profitability and strong 12-minus-1-month price momentum outperform low-profitability, weak-momentum companies over subsequent months. A sector-aware, long-only portfolio rebalanced monthly can improve risk-adjusted returns and potentially active return versus SPY at moderate turnover.

Required exact data:

- Original filing-vintage financial statements and availability timestamps
- Gross profit, assets, profitability, leverage, and shares outstanding as known at each date
- Historical index or investable-universe membership
- Delisted companies and delisting returns
- Point-in-time sectors and corporate actions

Potential frozen shape after data audit:

- Historical Russell 1000-like universe
- Gross profitability/assets as the primary quality measure
- 12-minus-1-month momentum as the independent price measure
- Equal standardized combination, sector-relative ranks
- Long top quintile, monthly rebalance, capped stock weights
- Compare directly with same-period SPY after costs

Cheap falsification gates:

- Each component has positive expected-sign Rank IC independently
- Composite improves rather than merely hides a failed component
- Gross active return is positive in both chronological halves
- Monthly turnover is moderate and not responsible for the result
- After-cost active return and information ratio versus SPY are positive

Main risk: testing this on the current active-only stock panel would be misleading. Data acquisition is a prerequisite, not optional polish.

Sources:

- AQR Quality Minus Junk: https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk
- Novy-Marx, “The Other Side of Value,” DOI: https://doi.org/10.1016/j.jfineco.2013.01.003

### 3. CrossAssetCarryTrend-v1

Priority: high alpha-sleeve candidate if individual futures-contract data can be acquired.

Institutional family: CTA trend following, global macro, alternative risk premia.

Hypothesis:

> Across liquid equity-index, government-bond, currency, and commodity futures, a diversified portfolio that combines each market's own medium-term trend with directly measured carry earns positive after-cost returns with low long-run SPY beta. Carry and trend should diversify one another because they are distinct signals.

Why this is not another ETF momentum retest:

- The repository's validated ETF strategy already represents the public time-series-momentum family.
- The new mechanism is contract-level carry from futures curves or forwards.
- Carry cannot be recovered faithfully from back-adjusted futures prices or ETF returns alone.

Required exact data:

- Individual futures contracts, prices, expiries, multipliers, and volumes
- Frozen roll policy and transaction costs
- Currency forwards or a predeclared exclusion
- Daily collateral yield and margin treatment
- Point-in-time contract selection with no back-adjustment leakage

Potential frozen shape after data audit:

- Predeclared set of liquid markets across at least four asset classes
- Twelve-month own-return trend plus directly measured annualized roll/forward carry
- Equal signal combination, inverse-volatility risk allocation
- Daily risk update, slower buffered rebalancing, fixed portfolio volatility target

Cheap falsification gates:

- Trend and carry are independently positive before combination
- Performance is not confined to one asset class
- Contract rolls and realistic costs do not erase gross returns
- Positive after-cost alpha and improved predeclared SPY-sleeve Sharpe
- Crisis and inflation regimes are reported rather than selected

Sources:

- AQR Time Series Momentum: https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- AQR Carry: https://www.aqr.com/Insights/Research/Journal-Article/Carry
- Man AHL: https://www.man.com/ahl

### 4. AnnouncedCashMergerArbitrage-v1

Priority: medium; economically distinct and daily, but operationally demanding.

Institutional family: event-driven and risk arbitrage.

Hypothesis:

> After an all-cash acquisition is publicly announced with definitive terms, diversified long exposure to targets trading below the cash consideration earns a completion-risk premium after financing, transaction costs, failed-deal losses, and realistic completion timing.

Required exact data:

- Point-in-time deal announcements and amendments
- Cash consideration, expected close date, conditions, votes, and regulatory status
- Deal completion and termination timestamps
- Historical delisted prices and cash payments
- Financing and borrow data for any hedge

Potential frozen shape after data audit:

- All-cash US public-company deals only in v1
- Entry no earlier than the next executable session after confirmed definitive terms
- Diversified, capped risk allocation; no discretionary deal selection
- Hold until completion, termination, or a predeclared outside date
- Market-beta hedge specified before testing

Cheap falsification gates:

- Gross annualized spread exceeds financing and trading costs
- Results survive all failed deals with no retrospective exclusions
- No single deal or year dominates profit
- Tail drawdown and capital lock-up remain acceptable
- Low-beta sleeve improves SPY portfolio utility

Source basis:

- Mitchell and Pulvino, “Characteristics of Risk and Return in Risk Arbitrage,” Journal of Finance, 2001, DOI: https://doi.org/10.1111/0022-1082.00383

Main risk: apparently smooth returns conceal rare large deal breaks. This is not suitable without trustworthy deal-history data.

### 5. PublicIndexReconstitutionFlow-v1

Priority: medium-low; daily event-driven and public, but crowded.

Institutional family: index arbitrage, event trading, benchmark-flow prediction.

Hypothesis:

> Publicly announced additions and deletions to major capitalization-weighted indices create predictable benchmark-fund flows between announcement and effective dates. A market- and sector-neutral additions-versus-deletions portfolio may capture part of that temporary demand pressure after realistic announcement timing and closing-auction costs.

Required exact data:

- Original timestamped index-provider announcements
- Historical constituents and effective dates
- Corporate actions, delistings, free float, and index weights
- Closing-auction prices and realistic execution costs

Potential frozen shape after data audit:

- One index family only in v1
- Trade no earlier than the first executable period after the official announcement
- Long additions, short deletions, beta and sector neutral
- Exit at a predeclared effective-date boundary

Cheap falsification gates:

- Positive gross event-time spread in both chronological halves
- No same-announcement execution
- Closing-auction costs and borrow do not erase the edge
- Results remain positive after excluding the largest events

Main risk: index effects have evolved as arbitrage capital anticipates changes. Do not infer historical membership from current constituent lists.

### Research reserve: source-faithful intraday information diffusion

Priority: low until data and execution improve.

Large firms certainly trade cross-venue and cross-asset lead-lag relationships, but their usable horizons are often far shorter than one hour. Public academic versions include industry information diffusion, same-clock return recurrence, and overnight/intraday return decomposition.

The repository already has several failed or pending intraday OHLCV experiments. Another ETF opening-window or generic lead-lag rule should not be prioritized merely because market makers use faster relatives of the idea. A future trial would require:

- SIP-quality synchronized bars or quotes
- Open and closing auction support
- A broader source-faithful stock universe
- No same-bar fills
- Day-level concentration and turnover gates
- A mechanism materially different from already consumed hypotheses

## Strategies explicitly excluded

### Market making and ETF arbitrage

Jane Street, Optiver, Citadel Securities, HRT, IMC, and similar firms operate here, but a daily-bar backtest cannot represent:

- Bid/ask queue position
- Creation/redemption access
- Real-time basket values
- Cross-venue latency
- Inventory netting
- Exchange fee tiers and rebates
- Adverse selection

A slow “ETF arbitrage” backtest would test a different strategy while borrowing the institution's name.

### Another five-day reversal or residual mean-reversion variant

Multiple nearby hypotheses lacked gross edge or were destroyed by turnover. Do not rescue the family with a new event window, threshold, universe, or exit.

### Another ETF trend or tactical-momentum window

The repository already has a validation-passed ETF time-series-momentum allocator and a failed tactical-momentum experiment. Goldman's public multi-lookback index is useful evidence that banks package this strategy family, not permission to search adjacent windows on the same sample.

### Options volatility risk premia

Institutions use volatility carry, dispersion, and relative-value options strategies, and some Cboe index methodologies are public. They remain excluded unless options are explicitly approved and the repository gains point-in-time option surfaces, delisted contracts, realistic spreads, assignments, exercise, margin, and tail-risk simulation.

### Generic news sentiment or large-language-model headlines

Do not proceed without a point-in-time historical news archive, source timestamps, duplicate handling, a frozen model version, and untouched evaluation data. Current headlines or backfilled article databases create severe lookahead and model-drift risks.

## Recommended sequence

1. Do not implement a new candidate yet.
2. Run two bounded data-feasibility spikes:
   - Point-in-time earnings surprise/analyst-revision history with historical membership and delistings
   - Individual futures-contract and curve history for carry
3. If earnings/revision data is attainable, freeze `PointInTimeEarningsRevisionDrift-v1` first.
4. If it is not attainable but clean futures curves are, freeze `CrossAssetCarryTrend-v1` first.
5. Build `PointInTimeQualityProfitabilityMomentum-v1` only after historical membership and filing-vintage fundamentals are solved.
6. Run Rank IC, gross return, chronological halves, concentration, and turnover before any expensive validation.
7. Archive a failure immediately. Do not promote an adjacent parameter row or substitute a proxy after observing results.

## Selection principle

The relevant lesson from institutional firms is not to imitate their fastest strategy category. It is to combine a defensible mechanism with exact point-in-time data, diversified portfolio construction, rigorous execution accounting, and a clear utility objective. Where the institution's edge is latency, order flow, or proprietary data, the correct decision is exclusion rather than imitation.