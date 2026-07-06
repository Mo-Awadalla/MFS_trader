# Swing / day-trading-ish strategy source scout v1

Purpose: identify credible, testable sources for a more active strategy family. This is source discovery only, not a validated strategy and not permission to tune until something passes.

## Recommendation

Prioritize intraday momentum / opening-range continuation on liquid ETFs, using 30-minute bars and strict flat-by-close rules. This is closest to the desired "option B" day-trading-ish behavior while avoiding one-minute scalping and tick-level fill assumptions.

Best first hypothesis family:

- Universe: SPY, QQQ, IWM first; optionally add GLD, TLT/IEF after the core path works.
- Bar size: 30 minutes.
- Signal: first 30-minute or first-hour market move predicts last 30-minute / afternoon continuation.
- Execution: no same-bar execution; signal observed after the opening window, enter next bar or at a frozen scheduled time, exit before close.
- Positioning: long/flat first. Consider short only as a separate Experiment.
- Validation: session-aware WFA, intraday-aware annualization, flat-by-close check, minimum trades/sessions, strict costs/slippage, day-level profit concentration cap.

## Credible source candidates

### 1. Market intraday momentum

Citation:
Lei Gao, Yufeng Han, Sophia Zhengzi Li, Guofu Zhou, "Market intraday momentum", Journal of Financial Economics, 2018.
DOI: 10.1016/j.jfineco.2018.05.009
Crossref citations observed: 204
URL: https://doi.org/10.1016/j.jfineco.2018.05.009

Why credible:
Published in Journal of Financial Economics and directly studies intraday continuation. It is the cleanest source for the requested day-trading-ish direction.

Testable rule shape:
- Use broad market ETF proxy such as SPY/QQQ.
- Measure early-session return, e.g. open to first 30 minutes / first half-hour.
- Trade later-session continuation, e.g. final 30 minutes or afternoon window.
- Flat by close.

Repo fit:
Good conceptual fit, but requires intraday bars and session-aware validation. Start with 30-minute bars rather than 1-minute bars.

Main risks:
Small edge, spread/slippage sensitivity, execution timing, PDT/account constraints, market regime decay.

### 2. First half-hour predicts last half-hour

Citation:
Lei Gao, Yufeng Han, Guofu Zhou, "Intraday Momentum: The First Half-Hour Return Predicts the Last Half-Hour Return", SSRN Electronic Journal.
DOI: 10.2139/ssrn.2440866
Crossref citations observed: 10
URL: https://doi.org/10.2139/ssrn.2440866

Why credible:
Earlier/narrower version of the intraday momentum idea; less authoritative than the JFE paper but very directly maps to a simple validation hypothesis.

Testable rule shape:
- If first half-hour return is positive, buy for last half-hour; if negative, either stay flat in v1 or short in a separate v2.
- Flat by close.
- Use market ETFs first.

Repo fit:
Very good for a minimal day-trading validation scaffold because it creates one scheduled entry and one scheduled exit per day.

Main risks:
Requires reliable intraday timestamps, accurate session calendars, and a conservative assumption for late-day fills.

### 3. Opening range breakout profitability

Citation:
Ulf Holmberg, Carl Lönnbark, Christian Lundström, "Assessing the profitability of intraday opening range breakout strategies", Finance Research Letters, 2013.
DOI: 10.1016/j.frl.2012.09.001
Crossref citations observed: 33
URL: https://doi.org/10.1016/j.frl.2012.09.001

Why credible:
Peer-reviewed and directly about opening-range breakout. This is the closest named technical-trading pattern with academic/practitioner research support.

Testable rule shape:
- Define opening range from first 30 or 60 minutes.
- Enter long on breakout above range high, optionally short on break below range low in a separate Experiment.
- Stop/exit rule must be frozen before testing; v1 should use flat-by-close and no discretionary stop tuning.

Repo fit:
Good "option B" candidate after intraday validation tooling exists.

Main risks:
Parameter temptation is high: range length, breakout buffer, stop, target, time stop, volatility filter. Must freeze one canonical rule before testing.

### 4. Timely opening range breakout on index futures

Citation:
Yi-Cheng Tsai, Mu-En Wu, Jia-Hao Syu, Chin-Laung Lei, "Assessing the Profitability of Timely Opening Range Breakout on Index Futures Markets", IEEE Access, 2019.
DOI: 10.1109/access.2019.2899177
Crossref citations observed: 19
URL: https://doi.org/10.1109/access.2019.2899177

Why credible:
Less finance-top-tier than JFE/FRL but useful as a second ORB implementation reference.

Testable rule shape:
- Index futures in the paper; approximate with SPY/QQQ/IWM ETFs only if we explicitly accept ETF proxy differences.
- Avoid ML additions in v1; freeze a simple ORB rule.

Repo fit:
Secondary support for ORB, not the primary source.

### 5. Overnight versus intraday expected returns

Citation:
Dong Lou, Christopher Polk, Spyros Skouras, "A tug of war: Overnight versus intraday expected returns", Journal of Financial Economics, 2019.
DOI: 10.1016/j.jfineco.2019.03.011
Crossref citations observed: 299
URL: https://doi.org/10.1016/j.jfineco.2019.03.011

Why credible:
Top journal and strong citation count. It is not a simple ORB system, but it gives a serious basis for separating overnight and intraday return components.

Testable rule shape:
- Swing/day boundary strategy: classify recent overnight and intraday return components separately.
- Trade continuation/reversal at the open/close boundary.
- Could be tested first on highly liquid ETFs or large-cap stocks.

Repo fit:
Good for swing/day-boundary strategies using daily open/close data, less direct for pure intraday ORB.

Main risks:
Cross-sectional implementation may need a broader stock universe and realistic open/close fills.

### 6. Cross-section of intraday and overnight returns

Citation:
Vincent Bogousslavsky, "The cross-section of intraday and overnight returns", Journal of Financial Economics, 2021.
DOI: 10.1016/j.jfineco.2020.07.020
Crossref citations observed: 129
URL: https://doi.org/10.1016/j.jfineco.2020.07.020

Why credible:
Top journal and directly about intraday/overnight return cross-section.

Testable rule shape:
- Separate overnight and intraday components across stocks.
- Rank/select based on component behavior.
- Likely better as a later broader-universe swing strategy, not first day-trading implementation.

Repo fit:
Medium. Needs stock universe breadth and open/close precision.

## Candidate ranking for this repo

1. Market intraday momentum / first half-hour to last half-hour on SPY/QQQ/IWM.
2. Opening range breakout on SPY/QQQ/IWM 30-minute bars.
3. Overnight/intraday tug-of-war swing strategy on liquid large caps or ETFs.
4. Cross-sectional intraday/overnight stock strategy after broader data plumbing is ready.

## Validation requirements before implementing any candidate

The daily/monthly gauntlet alone is insufficient for these. Add day-trading-ish gates:

- Intraday-aware annualization factor: 252 * bars_per_session, not always 252.
- Session-aware WFA: splits must be date/session based and preserve full days.
- Flat-by-close check for strict day-trade Experiments.
- Maximum holding period in bars.
- Minimum trade count and minimum trading-session count.
- Max trades/session and max turnover/session.
- Profit concentration cap by trading day.
- Conservative slippage/spread stress.
- No same-bar execution.
- Broker paper evidence must prove scheduled bar ingestion, signal generation, order submission/cancel/fill handling, and end-of-day reconciliation.

## Frozen first implementation proposal, not yet tested

Name: market_intraday_momentum_v1

Hypothesis:
For liquid US index ETFs, the first 30-minute return predicts late-day continuation. A long/flat ETF strategy that enters only when the opening 30-minute return is positive, uses no shorting, and exits before the close can produce positive out-of-sample risk-adjusted returns after conservative costs.

Universe:
SPY, QQQ, IWM.

Data:
30-minute adjusted OHLCV bars from Alpaca SIP if available; otherwise block validation rather than silently using a feed with known timestamp/volume mismatch.

Rules:
- Opening signal window: first 30-minute regular-session bar.
- Entry: next eligible bar after the opening signal, not same-bar.
- Exit: final regular-session bar before close.
- No overnight exposure.
- Long-only v1.
- Equal capital per triggered ETF, max gross 1.0.

Falsification:
Fail if it does not pass WFA/MC/DSR/stability plus intraday-specific gates after costs. Do not rescue it by changing window length, adding shorts, or switching symbols after results.
