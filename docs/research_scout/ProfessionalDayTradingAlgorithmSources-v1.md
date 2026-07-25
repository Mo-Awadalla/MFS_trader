# ProfessionalDayTradingAlgorithmSources-v1

Status: research memo; no strategy is approved or implemented from this document.

## Executive conclusion

Professional day-trading algorithms are usually not found as ready-made rules in books or public strategy lists. They are developed inside a research and execution stack:

1. A mechanism is identified from market structure, information arrival, risk transfer, or behavioral evidence.
2. The mechanism is measured with broad point-in-time data, often including trades, quotes, order-book events, fundamentals, event timestamps, or proprietary flow.
3. Researchers estimate the signal jointly with transaction costs, liquidity, market impact, financing, and portfolio interactions.
4. Traders and engineers turn the signal into pricing, order placement, hedging, inventory, risk, and reconciliation systems.
5. Many small signals are diversified across instruments, markets, and time horizons.

The critical gap in this repository is therefore not a missing opening-range formula. It is the lack of a professional-grade information and execution layer for intraday research. The repository has strong research discipline and a useful backtesting/risk framework, but its day-trading experiments mostly operate on small ETF panels and bar-based OHLCV. That is materially narrower than the data and business model used by professional intraday firms.

The honest implication is not that we should copy HFT. The fastest professional strategies depend on microsecond latency, queue position, co-location, exchange connectivity, and order-flow advantages that are outside the stated objective. The implication is that a non-HFT day-trading program needs a different professional-grade information source: synchronized trade/quote data, order-flow aggregates, timestamped events, or a broader cross-asset information-diffusion panel.

## 1. “Professional day trader” describes several different businesses

### A. Electronic market makers and prop trading firms

Examples include Jane Street, Optiver, Citadel Securities, Hudson River Trading, IMC, and similar firms.

Their public descriptions emphasize:

- liquidity provision;
- quantitative pricing;
- market making;
- hedging;
- inventory management;
- execution and venue selection;
- machine learning and statistical modeling;
- in-house trading and risk systems.

They are often flat or close to flat in directional risk over short intervals, but that does not mean they use a simple flat-by-close directional strategy. Their P&L can come from earning spreads, managing inventory, pricing derivatives/ETFs, cross-venue relationships, and hedging efficiently.

Jane Street’s official overview states that it is a global liquidity provider and trading firm using quantitative analysis and market mechanics. It says it trades on more than 200 electronic exchanges, analyzes large datasets, uses machine learning, and builds models, strategies, and systems in-house. It also says a single trade is the product of trading, research, technology, and risk systems working together.

Source:

- https://www.janestreet.com/what-we-do/overview/

This is not a reproducible signal disclosure. It is evidence that the production algorithm is a stack rather than one public pattern.

### B. Medium-frequency systematic managers

Examples include AQR, Man AHL, and systematic teams inside multi-strategy hedge funds.

These firms may trade daily, weekly, or monthly rather than at HFT speeds. Their public research often covers:

- time-series momentum;
- cross-sectional momentum;
- value;
- quality/profitability;
- carry;
- trend following;
- volatility and risk premia;
- event-driven or fundamental continuation.

They generally do not publish the exact live signal ensemble, current parameters, execution schedule, cost model, portfolio constraints, or risk overlay.

Man AHL’s official page describes a team of researchers, developers, and traders applying scientific research and technology to diverse data and hundreds of global markets.

Source:

- https://www.man.com/ahl

AQR’s public research pages provide an important example of what can be reproduced: a paper mechanism and, in some cases, original paper data. They do not disclose the current production portfolio or implementation.

Sources:

- https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- https://www.aqr.com/Insights/Research/Journal-Article/Value-and-Momentum-Everywhere

### C. Client-facing quantitative investment products

Bank-issued quantitative strategy indices are one of the few places where exact rules are often public. A methodology must be disclosed because a note, certificate, or other product is linked to it.

These documents can disclose:

- universe;
- lookbacks;
- optimization objective;
- volatility constraint;
- weights;
- rebalancing;
- deductions;
- disruption rules.

They are useful for research and implementation practice, but they are not evidence that the bank’s proprietary trading desk uses that rule or that the product has durable alpha after fees and execution.

This is a legitimate source of algorithms, but it is closer to transparent portfolio engineering than to secret day-trading alpha.

### D. Individual or “retail professional” day traders

This group should be treated separately from institutional market makers. Public claims about profitable individual day trading are heavily affected by selection bias, survivorship, leverage, and self-reporting.

Chague, De-Losso, and Giovannetti, “Day Trading for a Living?” studied persistent individual traders in Brazilian equity futures. Their reported results found that 97% of individuals who persisted for at least 300 trading days lost money, and only 0.4% earned more than a bank-teller wage. This is not evidence that no professional trader can succeed. It is evidence that retail day trading is not a reliable public source of reproducible algorithms.

Source:

- https://doi.org/10.2139/ssrn.3423101

Barber, Lee, Liu, and Odean, “The Cross-Section of Speculator Skill: Evidence from Day Trading,” provides a peer-reviewed study of skill dispersion among day traders rather than a recipe for an algorithm.

Source:

- https://doi.org/10.1016/j.finmar.2013.05.006

## 2. Where professional algorithms actually come from

### 2.1 Academic papers and factor research

Academic research is usually a hypothesis generator, not a production recipe.

Useful public examples include:

- Gao, Han, Li, and Zhou, “Market Intraday Momentum,” Journal of Financial Economics, 2018. The first half-hour return predicts later-session returns in the studied market proxies. The repository tested a related ETF implementation and it failed on the tested data, so the paper is not a reason to change windows or symbols after the fact.
  - https://doi.org/10.1016/j.jfineco.2018.05.009
- Heston, Korajczyk, and Sadka, “Intraday Patterns in the Cross-Section of Stock Returns,” Journal of Finance, 2010. They report half-hour continuation at same-clock intervals and find that short-term reversal is associated with temporary liquidity imbalances and bid-ask bounce. This points toward flow/liquidity measurement rather than another price-only window.
  - https://doi.org/10.1111/j.1540-6261.2010.01573.x
- Chordia and Swaminathan, “Trading Volume and Cross-Autocorrelations in Stock Returns,” Journal of Finance, 2000. High-volume portfolios lead low-volume portfolios, consistent with different speeds of information adjustment. This is an information-diffusion mechanism, not a generic breakout rule.
  - https://doi.org/10.1111/0022-1082.00231
- Hou, “Industry Information Diffusion and the Lead-lag Effect in Stock Returns,” Review of Financial Studies, 2007. This provides a cross-sectional industry-information-diffusion mechanism, but a faithful intraday implementation needs synchronized industry and stock data.
  - https://doi.org/10.1093/revfin/hhm003
- Lou, Polk, and Skouras, “A Tug of War: Overnight versus Intraday Expected Returns,” Journal of Financial Economics, 2019.
  - https://doi.org/10.1016/j.jfineco.2019.03.011
- Bogousslavsky, “The Cross-Section of Intraday and Overnight Returns,” Journal of Financial Economics, 2021.
  - https://doi.org/10.1016/j.jfineco.2020.07.020

The repository has correctly used academic papers as candidate sources. The mistake would be assuming that a paper’s existence makes the exact local implementation plausible after nearby family failures.

### 2.2 Market microstructure research

Professional intraday research often starts with the state of the market, not just the past OHLCV path.

Cont, Kukanov, and Stoikov, “The Price Impact of Order Book Events,” Journal of Financial Econometrics, 2014, study limit orders, market orders, and cancellations using NYSE TAQ data for 50 US stocks. They report that short-interval price changes are mainly driven by order-flow imbalance at the best bid and ask, with a relationship that depends on market depth.

Source:

- https://doi.org/10.1093/jjfinec/nbt003

Hasbrouck, “Measuring the Information Content of Stock Trades,” Journal of Finance, 1991, models trades and quote revisions jointly and finds that price impact can arrive with a lag, depends on trade size, and is related to spreads and information asymmetry.

Source:

- https://doi.org/10.1111/j.1540-6261.1991.tb03749.x

This is a major clue about what the repository is missing. A bar’s close and volume are a compressed summary of market activity. Professional intraday models may use the sequence and imbalance of trades, quotes, cancellations, spread, depth, and venue state before that information is compressed into a bar.

This does not mean we should enter the HFT arms race. It means that a 30-minute non-HFT signal could potentially use aggregated flow and liquidity state, but that is a new data program, not another opening-range formula.

### 2.3 Execution and market-impact research

Professional firms do not treat execution as a fixed percentage deducted from returns. They model the interaction between order size, liquidity, volatility, urgency, spread, market impact, and portfolio transitions.

Almgren and Chriss, “Optimal Execution of Portfolio Transactions,” is a foundational execution framework for balancing market impact and timing risk.

Source:

- https://doi.org/10.21314/jor.2001.041

Hendershott, Jones, and Menkveld, “Does Algorithmic Trading Improve Liquidity?”, Journal of Finance, 2011, use a market-structure change as an instrument and find that algorithmic trading narrowed spreads and reduced adverse selection for large stocks.

Source:

- https://doi.org/10.1111/j.1540-6261.2010.01624.x

The professional question is therefore not merely “does the signal predict the next bar?” It is:

- Can we get filled?
- At what size?
- Against what spread and depth?
- How does our order change the price?
- What happens when all selected names need the same trade?
- Does the signal survive realistic order placement?

### 2.4 Market-design and latency research

Budish, Cramton, and Shim, “The High-Frequency Trading Arms Race,” document mechanical arbitrage opportunities in continuous markets and argue that tiny speed advantages create an arms race.

Source:

- https://doi.org/10.1093/qje/qjv027

Aquilina, Budish, and O’Neill, “Quantifying the High-Frequency Trading Arms Race,” find that latency races in FTSE 100 stocks are extremely fast, often lasting 5–10 microseconds, with a small group of firms accounting for most wins and losses.

Source:

- https://doi.org/10.1093/qje/qjab032

This explains why copying the most visible professional “day-trading” business would be a category error. A market-maker algorithm’s edge may be inseparable from speed, queue position, co-location, and exchange connectivity.

## 3. What professional firms do not get from public sources

Public disclosures generally do not reveal:

- production features;
- exact signal horizons;
- model ensembles;
- data cleaning and vendor corrections;
- historical security identifiers;
- delisted symbols;
- quote/trade filtering;
- order-book reconstruction;
- execution venue selection;
- queue position;
- inventory limits;
- hedge timing;
- borrow and financing terms;
- portfolio interactions;
- capital allocation across strategies;
- live transaction-cost calibration;
- capacity limits;
- model retirement rules.

13F filings do not solve this. They are delayed, omit shorts and many derivatives, and do not disclose intraday signals or execution.

Marketing pages and job postings reveal capabilities, not investable rules.

## 4. What this means for the repository

### Current strengths

The repository already has several institutional-quality habits:

- frozen hypotheses;
- no same-bar execution;
- chronological validation;
- explicit costs;
- WFA/Monte Carlo/DSR checks;
- failure archiving;
- benchmark and utility distinctions;
- broker/paper-operation scaffolding;
- SEC event ingestion and auditable raw caches.

Those are important. The problem is not that the research process is unserious.

### Missing or narrow layers

1. **Intraday data breadth**
   The day-trading experiments mostly use a small ETF panel and bar data. Professionals research many stocks, instruments, venues, and regimes. A three-ETF panel is useful for plumbing but too small to discover a robust cross-sectional institutional effect.

2. **Trade/quote state**
   The repository does not yet have a research-grade historical TAQ/order-book layer for quote depth, spread, trade direction, cancellations, and order-flow imbalance.

3. **Point-in-time information**
   The repository has SEC filing events, but not a complete historical analyst-consensus/revision dataset, timestamped news archive, or broad structured event history. SEC filing presence is not the same as information direction or surprise.

4. **Observed execution calibration**
   The repository has a cost model and paper execution framework. It does not yet have a sufficiently deep history of real fills by symbol, spread state, participation, order type, and urgency to calibrate a professional intraday impact model.

5. **Scale and diversification**
   Professional managers often combine many weak signals across hundreds of markets. The current process has focused heavily on finding one strategy that can stand alone against SPY. That is a stricter and less representative objective than how many institutions build portfolios.

6. **Portfolio-level alpha construction**
   A professional intraday system may not be a directional strategy at all. It may be a set of small predictive signals combined with inventory, risk, and execution controls. Testing one directional opening rule is only one narrow slice of that design space.

## 5. The critical thing we were missing

We were treating “day trading” as a holding period and looking for a price pattern that works within that period.

Professional firms often treat it as an information and trading-state problem:

- What information is arriving now?
- Who has not incorporated it yet?
- Is the move information-driven or liquidity-driven?
- What is the current order-flow imbalance?
- How much depth is available?
- Which instruments lead and which lag?
- Can the expected return exceed implementation cost?
- How can several weak signals be diversified?

That is the critical distinction.

The missing ingredient is probably not a secret formula. It is one or more of:

- broader synchronized data;
- order-flow/liquidity state;
- timestamped fundamental/event information;
- cross-asset lead-lag structure;
- realistic execution feedback;
- or a portfolio of weak signals rather than one “winning setup.”

## 6. Practical research directions

### Direction 1: professional-style non-HFT microstructure scout

Closest to the day-trading objective, but requires new data.

Research only, not yet a frozen strategy:

- obtain historical trades and quotes or a suitable full-market SIP product;
- aggregate order-flow imbalance, spread, depth, volatility, and signed-volume state into 5–30 minute intervals;
- test whether those variables predict the next interval after conservative lagging;
- use broad liquid stocks or ETFs, not only SPY/QQQ/IWM;
- validate gross signal, turnover, capacity, and execution cost separately;
- avoid claiming that a short-interval academic result transfers automatically to a 30-minute strategy.

This is the most direct way to test whether the repo is missing the information layer used by professionals.

### Direction 2: timestamped event-driven trading

Closest to institutional medium-frequency equity research, but less purely “chart-based.”

Potential sources:

- earnings surprises with before-open/after-close timestamps;
- analyst estimate revisions with historical observation timestamps;
- index additions/deletions and effective-date flows;
- merger announcements and deal terms;
- structured corporate actions.

This can be traded intraday or over a few days, but it needs licensed or carefully verified historical data. The current SEC filing cache is not sufficient for the full hypothesis.

### Direction 3: cross-asset information diffusion

This uses the Chordia/Swaminathan and Hou mechanisms:

- synchronized market, sector, futures, ETF, and stock data;
- explicit leader/laggard relationships;
- fixed lag and holding rules;
- broad panel and cost-aware execution.

It may fit 30-minute or hourly trading better than a standalone opening pattern, but it still requires more breadth and careful beta/sector controls.

### Direction 4: accept a different horizon

The most reproducible public institutional research is often daily-to-monthly:

- quality plus momentum;
- earnings drift;
- carry plus trend;
- defensive trend following;
- value/momentum combinations.

These are not day-trading systems, but they are where public research, available data, and execution constraints overlap more favorably.

## 7. Bottom line

Professional firms do not generally discover algorithms by searching for a better version of “opening drive.” They build a data advantage, a market-state model, an execution system, and a diversified portfolio around a mechanism.

The repository is not missing one obvious public day-trading algorithm. It is currently missing the information layer that would let us investigate the same class of mechanisms professionals investigate without copying their microsecond business.

Therefore the next sensible work item is not another day-trading backtest. It is a bounded data-feasibility project for one of these:

1. synchronized trade/quote and order-flow data for a non-HFT microstructure scout;
2. timestamped event/fundamental data for event-driven trading;
3. a broader cross-asset panel for information diffusion.

If none of those data paths is affordable and verifiable, the correct conclusion is that the current OHLCV-only day-trading search space has been adequately explored for now.
