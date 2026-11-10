"""Compile an evidence-linked hypothesis ledger without evaluating new returns."""
from pathlib import Path
import json, re, csv
from collections import Counter
from build_postmortem_20260907 import ROOT, OUT, read

ROWS=[]

def walk(o,p=''):
    if isinstance(o,dict):
        for k,v in o.items(): yield from walk(v,f'{p}.{k}' if p else k)
    elif isinstance(o,list):
        if all(isinstance(v,(str,int,float,bool,type(None))) for v in o): yield p,o
    else: yield p,o

def evidence(o):
    # Keep recorded results and gate decisions, not prices, features or trade ledgers.
    picked={}
    for p,v in walk(o):
        if re.search(r'calibration_table|by_month|by_year|year_pnl|month_pnl|year_counts|daily_|input_audit|threshold|prohibited|params|parameters|definitions|rules|source',p): continue
        if re.search(r'gate|acceptance_criteria|failure|verdict|lesson|decision|passed|status|holdout_policy|ending_cash|ending_equity|net_pnl_usd|fixed_notional_pnl|total_pnl_usd|profit_factor|trades_per_week|entries_per_week|mean_.*bps|^trade_count$|^selected_',p):
            picked[p]=v
    return picked

def failures(o):
    out=[]
    for p,v in walk(o):
        if re.search('gate|acceptance_criteria|failure',p) and (v is False or v=='fail' or (isinstance(v,list) and 'failure' in p)):
            out.append(p+': '+str(v))
    return out

def add(id,name,group,category,stage,why,gap,sources,raw=None,related='',kind='hypothesis'):
    sources=list(dict.fromkeys(str(s).replace('\\','/') for s in sources))
    assert sources and all((ROOT/s).is_file() for s in sources),(id,sources)
    ROWS.append(dict(id=id,name=name,group=group,kind=kind,classification=category,stage=stage,
        postmortem=why,what_would_change_the_evidence=gap,related=related,sources=sources,
        recorded_evidence=evidence(raw) if raw else {},recorded_gate_failures=failures(raw) if raw else []))

def source_v(n):
    return sorted(p.relative_to(ROOT).as_posix() for p in (ROOT/'research_scout').glob('*')
        if p.suffix in ['.md','.json'] and re.search(fr'_v{n}\.json$|_V{n}\.md$',p.name))

def base_metrics(c):
    out=[]
    for label in ['development','secondary_holdout','holdout']:
        v=c.get(label,{})
        if not isinstance(v,dict): continue
        b=v.get('observed_bbo',v.get('base',{}))
        if not b: continue
        pnl=b.get('net_pnl_usd',b.get('fixed_notional_pnl_usd'))
        end=b.get('ending_cash_usd',b.get('cash_account',{}).get('ending_equity_usd'))
        text=f'{label}: '
        text+=f'fixed-notional P&L ${pnl:.2f}; ' if isinstance(pnl,(int,float)) else ''
        text+=f'ending cash ${end:.2f}; ' if isinstance(end,(int,float)) else ''
        text+=f'PF {b["profit_factor"]:.3f}; ' if isinstance(b.get('profit_factor'),(int,float)) else ''
        out.append(text.rstrip('; '))
    return '. '.join(out)

EARLY_NOTES={
 'late_volume_clock_compass':('protocol','Passed its original economic checks but failed required frequency. Later curiosity holdout exposure is separately recorded; it cannot be called untouched.'),
 'longest_run_recency':('robustness','Positive development and cost/tail diagnostics, but a development year was negative. This is an annual-consistency gate rejection, not proof of zero gross edge.'),
 'silence_entropy_order':('robustness','Passed development, then lost in later years. Binary activity regularity did not generalize.'),
 'opening_center_migration_bbo_benchmark':('robustness','Prior ES mechanism transported to cash wrappers; development passed but the cash-ETF holdout lost.'),
 'quiet_variance_carry':('robustness','Weak long-only effect failed SPY, annual and winner-concentration requirements; later cash gain was small.'),
 'breadth_consensus':('robustness','Positive pooled returns did not clear benchmark and robustness requirements. More related index ETFs did not establish incremental alpha.'),
 'paired_variance_harvest':('economic','Paired leverage variance effect was too small or adverse after execution; it did not deliver a tradable variance premium.'),
}

def early():
    for p in sorted((ROOT/'research_scout').glob('*results_v*.json')):
        m=re.search(r'_v(\d+)\.json$',p.name)
        if not m or int(m[1])>12: continue
        if not (p.name.startswith('upro_') or p.name.startswith('spy_sh_')): continue
        v=read(p)
        if not isinstance(v.get('candidates'),dict): continue
        n=int(m[1]); tag='SPY-SH' if p.name.startswith('spy_sh') else f'V{n}'
        for key,c in v['candidates'].items():
            cat,note=EARLY_NOTES.get(key,('economic','The recorded marketable-execution rule failed its frozen economic and/or robustness gates. The name does not establish the proposed institutional flow.'))
            if key not in EARLY_NOTES:
                d=c.get('development',{}).get('observed_bbo',c.get('development',{}).get('base',{}))
                pnl=d.get('net_pnl_usd',d.get('fixed_notional_pnl_usd',-1))
                if pnl>0: cat='robustness'; note='Positive aggregate development P&L was insufficient: recorded annual, direction, cost, concentration or benchmark gates failed.'
            gap='No identified missing field explains this rejection. Preserve the frozen result; new signal evidence requires a distinct measurement and fresh validation.'
            if cat=='protocol': gap='A future mandate may allow a sparse sleeve, but do not relax this frozen test or label exposed historical dates fresh.'
            related='Related variants share data and multiple-testing exposure; not independent trials.'
            src=[p.relative_to(ROOT).as_posix()]
            spec=v.get('specification')
            if spec and (ROOT/spec).is_file(): src.append(spec)
            add(f'{tag}:{key}',key.replace('_',' ').title(),'Cash ETF batches',cat,'Historical P&L',base_metrics(c)+'. '+note,gap,src,c,related)
    singles=[(3,'upro_spxu_sparse_volume_clock_results_v3.json','Sparse Volume Clock','economic','Sparse extension of V2; base P&L, PF, annual, sleeve, cost, delay and winner-deletion gates failed.'),
      (6,'upro_spxu_density_invariant_sync_2026_result.json','Density-Invariant Synchronization','measurement','Zero trades on 138 eligible 2026 sessions. The activity state ceased to discriminate; zero P&L is not evidence of profitable or unprofitable fills.'),
      (7,'upro_spxu_expanding_analog_memory_result_v7.json','Expanding Analog Memory','robustness','Walk-forward nearest-history construction failed frozen acceptance requirements; adaptation did not overcome benchmark, sleeve and tail weakness.'),
      (8,'upro_sh_sensor_actuator_result_v8.json','UPRO/SH Sensor-Actuator Substitution','robustness','Changing the inverse execution vehicle improved some metrics but still failed SPY, annual/sleeve and concentration requirements; independent overlap lost.'),
      (13,'upro_spxu_index_simplex_results_v13.json','Index Simplex','robustness','Sparse, winner-dependent development; later-period and benchmark gates failed. Broad-index geometry was not a stable improvement over breadth.'),
      (14,'upro_spxu_leverage_spectrum_results_v14.json','Leverage Spectrum','measurement','Cross-feed action agreement only 38.46%; independent reconstruction lost. Endpoint leverage residual was not a stable state, alongside economic failures.')]
    for n,f,name,cat,note in singles:
        v=read(ROOT/'research_scout'/f)
        add(f'V{n}',name,'Cash ETF batches',cat,'Historical P&L / forward-period check',note,
            'No historical parameter rescue. Resolve feed/state semantics for measurement failures; otherwise only distinct information or new forward evidence.',source_v(n)+[f'research_scout/{f}'],v)

# id | name | classification | stage | postmortem | evidence-changing observation
NUMBERED='''
15|Listing-Venue Participation Tilt|measurement|Pre-return screen|Arca volume was not contained in the comparison feed; median supposed shares exceeded 100%. 612/666 signals selected UPRO. The denominator did not measure consolidated participation.|A true comparable consolidated volume denominator could measure venue share; it still would not identify AP/customer identity.
16|Cross-Inverse Aggressor Relay|robustness|Development|Ending cash $154.41, but removing ten best sessions made fixed P&L -$5.69; inverse sleeve failed and cross-feed score correlation was only 0.251.|No purchase is justified by this result alone; better signed-flow measurement would be a new measurement, not validation of the old rule.
17|Liquidity Thermostat|protocol|Pre-return screen|Only 0.711 signals/week despite full window coverage. No P&L.|No missing quote coverage explains the cadence; a sparse mandate is a future design choice, not a data repair.
18|Signed-Impact Asymmetry|economic|Development|Ending cash $79.52; raw aggressor-count control was stronger. Delay positivity did not rescue the original rule.|No established missing-data remedy; preserve the failure.
19|Premarket Wrapper Premium|economic|Development|Ending cash $62.36, PF 0.887; annual, sleeve, cost and benchmark gates failed.|A premium label did not establish a tradable arbitrage; executable premarket prices and actual basket value would define a different question.
20|ES Scar Transported to Cash ETFs|robustness|Development|Ending cash $156.80, but deleting ten winners made fixed P&L -$2.14. A positive headline above SPY did not survive frozen concentration checks.|Full holding-window executable quotes and untouched forward trades can assess implementation; they do not erase known tail dependence.
21|Dual-Scar Corridor|protocol|Pre-return screen|252 fully quoted entries; 1.615/week below the frozen two/week. Other recorded gates passed. No P&L.|This is mandate/cadence failure, not missing data or disproved profitability.
22|ES Three-Clock Cash-ETF Transfer|protocol|Pre-return screen|551 fully quoted entries; reload component had 17 entries versus minimum 25. No P&L.|No execution-data deficiency established. Future portfolio component minimums must be justified ex ante.
23|ES Scar Polarity Flip|protocol|Pre-return screen|16 fully quoted entries, 0.103/week; inadequate annual counts. No P&L.|More transformations do not increase independent occurrences; rare-event mandate would be different.
24|Sequential Auction Barycenter|protocol|Pre-return screen|281 entries, 1.801/week; annual counts below 100. Cross-feed action agreement 94.14%. No P&L.|Cadence rather than a missing causal field stopped this exact rule.
25|Signed Inventory Flux|measurement|Pre-return screen|394 entries and full primary quotes, but cross-feed cash-including actions agreed only 47%. No P&L.|Comparable full event streams could test whether flux is feed sampling; unsigned volume cannot identify inventory owners.
26|BTC Spot-Flow Baton to ETFs|economic|Development|Ending cash $58.57; PF 0.905. Failed costs, SPY and BTC-price control.|More BTC flow transforms are not a new economic channel.
27|Accepted-Value Retest Rent|protocol|Pre-return screen|186 entries, 1.192/week; annual cadence and cross-feed action gate failed. No P&L.|Cadence plus marginal action replication; no demonstrated payoff deficiency or data purchase remedy.
28|SH/SPXU Leverage-Escalation Latency|measurement|Pre-return screen|713 measurable entries, but cross-feed direction agreement 55.71% and action agreement 51.20%. No P&L.|Complete comparable quote updates are needed before interpreting an apparent lead-lag as economic latency.
29|Auction Value/Price Phase Lag|economic|Development|Ending cash $52.61, PF 0.917; SPXU lost heavily and 2023 dominated losses.|Price-anchor phase terminology did not create an identified inventory variable.
30|Signal-Free Actuator Hurdle|diagnostic|Exposure diagnostic|Always-UPRO ended $146.13 versus price-only SPY $181.68 in 2021–2025; SPXU ended $12.68. This is a benchmark audit, not another signal.|Useful cost/beta baseline. An impossible hindsight selector proves payoff variation, not predictable opportunity.
31|Closing Liquidity Memory Reset|protocol|Pre-return screen|104 quoted entries, 0.667/week; 96.39% cross-feed action agreement. No P&L.|Cadence failure. More quotes will not create more occurrences of the frozen state.
32|BTC Attention Gate times SPY Gap|economic|Development|Ending cash $64.50; lagged placebo and unfiltered gap controls were stronger; independent overlap lost.|Contemporaneous BTC spot activity did not identify usable SPY information.
33|Inverse-Leverage Liquidity Curvature|economic|Development|Ending cash $46.24; every development year and independent execution lost despite stable measurement.|Not explained by a missing consolidated feed alone.
34|Final Opening-Imbalance Buy Continuation|economic|Development|Fixed P&L -$15.40, PF 0.914; lagged placebo positive. Official imbalance sign alone failed.|Full auction data existed; final-sign inversion would be an outcome-derived repair.
35|Opening Auction Absorption Failure|protocol|Pre-return screen|20 feature signals, 0.135/week; seven executable development-overlap signals. No P&L.|Extremely sparse state; better quotes cannot by themselves create a frequent rule.
36|Opening Price/Quantity Disagreement|measurement|Pre-return screen|Cadence passed, but neighboring-cutoff actions agreed only 53.91%/44.59%, execution evidence failed, and no 2026 signals. No P&L.|Quote completion alone does not solve endpoint instability or temporal participation.
37|Indicative-Price Leadership|data|Pre-return screen|Frequent, balanced and locally stable, but all-timing quote coverage 88.37% versus 90%; separate critique questioned the reference-price anchor. No P&L.|Opening quote updates can address coverage; semantic/economic critique remains a separate obstacle.
38|Official Uncross Overshoot Rejection|measurement|Pre-return screen|18 development signals, unbalanced and unstable under adjacent observations; execution also failed. No P&L.|Better execution does not resolve a sparse, timestamp-sensitive signal construction.
39|Opening Market-Order Urgency|data|Pre-return screen|Zero 2021–2025 signals and seven 2026 signals: selected opening market-order field was largely unavailable. No P&L.|Verify feed/venue semantics and field-population regime; buying more of the same absent field is not a remedy.
40|Cross-Leverage Opening Quantity Consensus|data|Pre-return screen|Balanced stable features, but primary quote coverage 89.44% and relevant ladder 69.85% failed. No P&L.|Historical SIP/full quote updates could address execution coverage. Auction quantities are not proof of causal demand.
41|Closing Market-Urgency Hedge Window|protocol|Pre-return screen|86 development features, 11 executable overlap signals; cadence, side balance and execution coverage failed. No P&L.|Closing quotes help measurement but do not resolve rare feature cadence.
42|Late Closing Market-Urgency Acceleration|measurement|Pre-return screen|45 development features; no 2026/post-break participation and weak adjacent-clock actions despite 93.33% execution coverage. No P&L.|Fixing quotes alone cannot resolve feature regime and stability failures.
43|Early Auction to Premarket Handoff|data|Pre-return screen|725 stable/balanced features, but only 3.92% primary entry-exit quote coverage and extreme spread tails; no 2026/post-break features. No P&L.|Premarket SIP quotes plus protocol-population audit. A broad missingness fix must precede any evaluation; spreads remain economic risk.
44|BTC Perpetual Fresh-Position Transfer|economic|Development|Ending cash $40.83, PF 0.841; independent overlap also lost. Open-interest expansion did not identify persistent equity demand.|No evidence that additional BTC positioning proxies rescue this mapping.
45|Official Macro-Release Delayed Discovery|economic|Development|378 trades, ending cash $68.13; PF 0.835. Known announcement clocks plus initial SPY direction failed.|Actual surprise/expectation vintages would add information; event calendars alone were already tested.
46|VX Curve Confirmation Failure|protocol|Pre-return screen|219 executable signals, 1.401/week; almost complete data and strong roll/feed stability. No P&L.|Cadence rather than absent options data blocked this specific daily-VX rule.
47|VX Forward-Stress Persistence|robustness|Development and holdout|Passed development ($100 to $408.90), then 2024–2025 ended $30.60. Strong developmental stress tests did not generalize.|No historical regime/contract selection. New forward evidence only for a separately justified mechanism.
48|Official-Open Cross-Leverage Basis|protocol|Pre-return screen|310 development signals, 1.982/week; 2023 only 95 versus 100; some statistics arrived after boundary. No P&L.|Availability timestamps matter, but a later boundary or rounded cadence would change the frozen rule.
49|Six-Fund Fair-Value Simplex|data|Pre-return screen|Zero synchronized 2023 states under the frozen five-second six-fund requirement. Trade-event TBBO was insufficient. No P&L.|Complete synchronized quote updates; the local 09:20–09:40 MBP-1 acquisition now partly addresses this, but not full 2021–2023 coverage or fill probability.
50|Indicative Revision-Intensity Acceleration|measurement|Pre-return screen|365 features; left-window agreement 59.877% versus 60%, quote coverage 87.387% versus 90%. No P&L.|Complete opening quotes may solve coverage; separate near-threshold stability failure must remain recorded.
51|Cross-Auction Inventory Persistence|protocol|Pre-return screen|99 development signals, 0.633/week, and 70.39% execution coverage. No P&L.|Sparse hard-order state plus missing quotes; no economic evidence yet.
52|Routine Opening-Freeze Transfer|measurement|Pre-return screen|579 signals and 90.65% execution coverage, but transition-only action agreement 36.68%; excessive selection share. No P&L.|Endpoint sensitivity is a feature-definition failure, not primarily a missing data subscription.
53|Reserve-Liquidity Price Wedge|measurement|Pre-return screen|210 signals, 1.342/week; neighboring actions only 48.39%/21.86%. No P&L.|Real field distinctions did not create a stable state; full quotes alone insufficient.
54|Cross-Leverage Auction-Completion Latency|semantic|Causal screen|Substituted official-statistic timing into V40 pair-consensus topology; processing semantics ambiguous. No audit or P&L.|Require distinct economically interpretable measurement; no clock-field substitution to manufacture novelty.
55|VX Fresh-Position Risk Transfer|protocol|Pre-return screen|28 executable signals, 0.179/week, only four bearish. No P&L.|Rare daily-OI condition; no claim that options data would repair its cadence.
56|Joint Stock/Bond Macro Impulse|robustness|Development|Ending cash $117.80 versus SPY $132.40; extra-cent fixed P&L -$2.86 and delete-ten -$29.51.|Generic daily stock/bond signs did not establish macro surprises or robust net alpha.
57|Commodity/Treasury Inflation Impulse|economic|Development|Fixed P&L -$32.18; PF 0.911; independent overlap -$15.37.|DBC/IEF opposition did not uniquely identify inflation shocks. More ETF substitutions repeat the ambiguity.
58|Treasury Maturity Impulse|economic|Development|Fixed P&L -$7.46; PF 0.989; component and lagged controls stronger; independent overlap lost.|IEF-minus-SHY was not DV01-neutral. A properly measured rates mechanism differs from another return-sign pair.
59|Historical Leveraged-Fund Holdings|data|Data admission audit|Only three archived dated holdings files for 753 development sessions; historical publication times unknown. No P&L.|Point-in-time holdings/exposures with publication vintages. They still do not reveal actual dealer net hedging.
60|Official Creations and Redemptions|diagnostic|Data admission audit|NAV/AUM/share data passed; 748/753 paired states nonzero. This is an admitted input, not a strategy pass.|Already acquired. V61–V64 subsequently tested uses; do not list this as still missing.
61|Primary Flow times Opening Auction|economic|Development|373 trades; ending cash $76.15, PF 0.882, every year negative. Independent overlap lost.|Creation sign plus opening imbalance did not identify a directional edge; more AUM history alone is not the issue.
62|Creation-Conditioned Wrapper Discount|robustness|Development|315 signals; ending cash $108.84 versus SPY $132.40; extra-cent, delete-ten, temporal and independent-feed gates failed; redemption control stronger.|Minute quotes and creation data existed. Genuine basket/hedge measurement is different from repainting the same discount.
63|Four-Fund Rebalance plus Auction Capacity|semantic|Pre-return screen|704 signals; 96.18% action agreement with plain late-day model/momentum. No P&L.|Need a flow measurement that changes predictions beyond momentum; more AUM cannot fix an algebraic sign collapse.
64|Opposing-Auction Absorption Deficit|protocol|Pre-return screen|335 balanced stable signals and full independent action agreement; only 73 in 2021 versus required 90. No P&L.|Measured but stopped by a mandate gate. Not a missing-data priority and not evidence of an economic failure.
65|CFTC Participant Transfer times ES Opening|robustness|Development; timing caveat|Ending cash $101.47 versus SPY $132.40; cost, report-cluster and controls failed. Later V87 audit identified the 2023 CFTC publication outage requiring exclusions.|Historical actual report release dates, including outage, are needed for exact causal reconciliation. Old claim of universally safe lag is qualified; this does not promote the rule.
66|Treasury Dealer Dollar-Years|robustness|Development|Ending cash $99.96 versus SPY $132.40; extra-cent and cluster deletion negative; dealer allocation did not prove next-morning unhedged inventory.|Actual position/hedge timing would be distinct information. Weights on award shares were already tested.
67|Leveraged-Fund Gamma plus ES Inventory|economic|Development|733 signals; ending cash $77.89; every year and both wrappers lost despite stable cross-feed features.|Observed aggressor flow is not dealer net inventory. A better arithmetic combination is not new information.
68|3x/2x Delta-Neutral Ladder|data|Pre-return screen|Zero measurable full-period sessions because SSO/SDS continuous quotes were missing despite NAV coverage. No P&L.|Historical SIP may fill quote windows without a new plan. Requires historical borrow/execution evidence and a new admitted sample; opening MBP-1 alone does not cover 2021–2023.
69|ProShares Delta-Neutral Triangle|measurement|Pre-return screen|736 eligible sessions and complete quotes, but neighboring actions agreed only 54.89%/57.81%. No P&L.|Fresh same-time quotes did not establish a persistent basis state; not a missing-quote failure.
70|UPRO/SPXU Even-Mode Convergence|measurement|Pre-return screen|736 eligible sessions and complete quotes, but neighboring actions agreed only 63.59%/62.64%. No P&L.|Opening residual sign is unstable; more synchronized rows alone do not fix that.
71|Treasury Settlement plus RRP Netting|semantic|Pre-return screen|383 signals; 90.60% action agreement with RRP alone. No P&L.|Need independently identified dealer cash demand, not rescaling already-seen RRP inputs.
72|Settling-CUSIP Collateral Scarcity|semantic|Pre-return screen|281 signals, 261 bullish/20 bearish; 100% agreement with raw matched sum, 88.24% bill contribution. No P&L.|Distinctness/imbalance failed even before resolving first-publication and revision semantics highlighted later.
73|SEC Earnings Breadth to Index|robustness|Development|438 signals; ending cash $110.35 versus SPY $132.40; costs, uncertainty, concentration and controls failed.|Announcement content and prior expectations are missing, but this does not establish them as a profitable fix; coarse filing-reaction aggregation was tested.
74|Realized TGA Reserve Transfer|economic|Development|745 signals, ending cash $55.09; costs, delays, cluster uncertainty and controls failed.|Published realized transfers did not identify unanticipated intraday demand. Adding lags is not independent evidence.
75|Constituent Participation Acceleration|semantic|Pre-return screen|316 signals; 90.51% action agreement with SPY opening momentum and insufficient annual count. No P&L.|Broad constituent prices already existed. Need incremental information rather than another breadth confirmation.
76|Common-Factor Dispersion Compression|robustness|Development|376 signals, ending cash $123.29 versus SPY $132.40; simple two-half SPY control stronger; tail/year/sleeve gates failed.|Stable dispersion measurement was insufficient. Wider universe alone has not been shown to solve this.
77|Constituent Liquidity Relay|semantic|Pre-return screen|149 signals, 0.989/week; weak subuniverse replication and 95.30% momentum agreement. No P&L.|Venue volume did not identify parent-order migration. Consolidated data can change measurement, not retroactively validate relay identity.
78|FINRA Wrapper Short-Volume Direction|semantic|Causal screen|Short-sale prints do not identify net short positions or customer direction. Rejected before acquisition or P&L.|Participant/transaction context, not a normalized daily short-volume ratio, is required for the proposed sign interpretation.
79|Cross-Asset Primary Flow Transfer|semantic|Pre-return screen|Cross-asset NAV/share flows available, but HYG dominated 86.1% of actions; failed distinctness. No P&L.|Independent flow innovations rather than another vote dominated by one component.
80|Month-End SPY Avoidance|scope|Withdrawn proposal|Held overnight and was withdrawn after day-trading clarification. No P&L.|Out of current mandate; V83 is the separately frozen intraday relative.
81|Downside-Variance SPY Challenger|semantic|Rejected proposal|Duplicate of the V9 variance-state family. No new P&L.|No independent evidence from renaming a previously tested variance construction.
82|Transaction-Cost-Aware Online ETF Allocation Mixture|scope|Withdrawn proposal|Held overnight and was withdrawn after day-trading clarification. No P&L.|Out of current mandate; preserve as proposal history only.
83|Month-End Stock/Bond Pressure|robustness|Development|107 trades; $100 to $116.56 versus SPY $132.37. Cost/delay checks passed, but SPY wealth and excess-return uncertainty failed.|Potential defensive role is unvalidated and differs from the objective. Do not choose a new blend after seeing its winners.
84|Opening Quote Replenishment|economic|Development|105 trades; $100 to $85.03 versus SPY $121.43. Passed blind measurement tests using full opening quote updates.|Detailed quotes were present and the rule still lost. More depth is not an established remedy.
85|Earnings Peer-Network Propagation|robustness|Development|335 trades; $100 to $104.26 versus SPY $132.37; 44.8% daily drawdown and failed robustness.|Prior expectations/content could support a distinct question; simply adding sector ETF labels repeats existing peer/breadth work.
86|BTC Funding-Settlement Unwind|economic|Development|44 trades; $100 to $88.02 under 30 bps modeled round-trip costs. No observed quote execution validation.|Quotes can improve the cost model but do not establish a profitable funding-unwind effect.
87|CFTC Positions per Trader|semantic|Pre-return screen|364 signals; 327 bullish/37 bearish; 95.6% agreement with plain net positions. No P&L; 2023 outage excluded.|Trader-count normalization did not identify a new mechanism; report availability is independently essential.
88|Treasury Bid Dispersion|data|Data blocked|Historical first-publication times of auction results unverified; no P&L.|Archived first-release timestamps/vintages, not more auction rows or guessed clocks.
89|NY Fed Securities-Lending Fees|data|Data blocked|Historical first-publication and revision timing unverified; operation launch is not results publication. No P&L.|Archived actual results availability and version history.
90|Futures Maturity-Spread Dislocation|data|Data blocked|Simultaneous front/next executable quotes absent; futures capital/margin assumptions unresolved. No P&L.|Synchronized raw-contract quotes plus roll definitions and realistic two-leg execution.
91|Buyback-Window Reopening|data|Data blocked|Issuer-specific policies, authorization/capacity history and supporting afternoon stock execution absent. No P&L.|Actual issuer policy/authorization availability; a generic post-earnings date does not establish buyback demand.
92|Polymarket Complete-Set Arbitrage|data|Data blocked|Sampled outcome prices do not establish simultaneous executable asks and depth. No P&L.|Timestamp-aligned books, fees and two-leg fill mechanics; outcomes alone cannot measure arbitrage.
'''

def numbered():
    registry='research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md'
    for line in NUMBERED.strip().splitlines():
        n,name,cat,stage,why,gap=line.split('|'); n=int(n)
        src=source_v(n)
        if 80<=n<=82: src=['research_scout/SPY_CHALLENGER_HYPOTHESES_V80_V82.md']
        if n>=83:
            src=['research_scout/TEN_DAYTRADE_HYPOTHESES_V83_V92.md','research_scout/daytrade_batch_v83_v92/artifacts/FINAL_REPORT.md','research_scout/daytrade_batch_v83_v92/specification.json']
            src += [p.relative_to(ROOT).as_posix() for p in (ROOT/'research_scout/daytrade_batch_v83_v92/artifacts').glob(f'v{n}_*.json')]
        if not src: src=[registry]
        raw={}
        for s in src:
            if s.endswith('.json') and re.search('result|returns_blind|audit_v|_blind',s) and 'cash_etf_auction_research_results' not in s: raw[s]=read(ROOT/s)
        add(f'V{n}',name,'Numbered continuation',cat,stage,why,gap,src,raw,kind='diagnostic' if n in [30,59,60] else 'hypothesis')

def futures():
    excluded=['returns_blind','scar_to_leveraged','diagnostic_plan','forward_paper']
    for p in sorted((ROOT/'research_scout').glob('*.json')):
        if not p.name.startswith(('es_','mes_')) or any(s in p.name for s in excluded): continue
        if not ('prereg' in p.name or p.name in ['es_compressed_opening_auction_convexity_v1.json','es_midday_inventory_reload_v1.json','es_opening_auction_center_migration_v1.json','es_opening_dual_engine_portfolio_v1.json','es_spatial_topological_opening_convexity_v1.json','es_three_engine_intraday_portfolio_v1.json']): continue
        v=read(p); status=v.get('status','proposal')
        note=v.get('lesson',v.get('verdict',v.get('decision',status)))
        if isinstance(note,dict): note=json.dumps(note,ensure_ascii=False)
        cat='robustness' if any(s in status for s in ['holdout','paper','fragility','robustness']) else 'pending'
        d=v.get('development_result',{})
        if status=='rejected_on_development_without_holdout_access':
            cat='economic' if d.get('net_pnl_usd',0)<0 else 'robustness'
        src=[p.relative_to(ROOT).as_posix()]
        if p.name=='es_close_flow_prereg_v1.json':
            cat='robustness';note='Development positive, executable 2024–2025 holdout negative; rejected for paper/live. Observed ES aggressor confirmation did not generalize.'
            src.append('docs/research_scout/ESCloseAlignedAggressorFlow-v1-results.md')
        if p.name=='es_compressed_opening_auction_convexity_v1.json': cat='robustness'
        name=v.get('name',p.stem.replace('_',' ').title())
        add('ES:'+p.stem,name,'ES/MES',cat,'Historical P&L',str(note),
          'Futures execution/capital is not interchangeable with a $100 cash-ETF account. Weak retained candidates require full holding-window MES quotes and fresh forward evidence; no outcome-driven repair.',src,v,
          related='Shares ES history with other opening/value/flow variants; retained paper labels are research recommendations, not broker authorization.',
          kind='portfolio' if 'portfolio' in p.name or 'challenger' in p.name else 'hypothesis')

def formal():
    for p in sorted((ROOT/'experiments').glob('*/metadata.json')):
        v=read(p); q=p.parent/'validation/report.json'; r=read(q) if q.exists() else {}
        strategy=v.get('strategy','unknown'); freq=v.get('data_version',{}).get('bar_frequency','unknown')
        cat='robustness'; note='Frozen formal validation failed: '+'; '.join(r.get('gauntlet',{}).get('failure_reasons',[]))
        if v.get('promotion_status')=='validation_passed':
            cat='outside_daytrade_positive'; note='Passed formal daily validation. Monthly allocation holds overnight; not a day-trading SPY challenger. Duplicate UUID evidence does not create a second independent successful family.'
        if strategy=='pairs_trading':cat='protocol';note='Zero trades; all 72 rebalances skipped. This did not test an active pairs strategy and does not establish that pairs economics fail.'
        if strategy=='volatility_standardized_intraday_momentum':cat='data';note='Static 20-name hourly panel yielded 15 trades and 19,832/19,833 skipped rebalances; broad intended cross-section was not implemented. WFA/stability failed. Recorded total return and CAGR require annualization reconciliation before reuse.'
        if strategy in ['cross_sectional_mean_reversion','residual_reversal_stat_arb','residual_vol_momentum','market_intraday_momentum','opening_range_breakout','same_clock_intraday_seasonality']:cat='economic'
        if 'corrected WFA' in v.get('label',''): note+=' Corrected WFA supersedes the older zero-OOS diagnostic for economic interpretation; both UUIDs remain in provenance.'
        if strategy=='same_clock_intraday_seasonality': note+=' Holding-period gate was five bars versus one required; operational semantics also failed.'
        if not q.exists():cat='pending';note='Metadata exists but no canonical validation report found in this directory; do not infer a completed test from its status label alone.'
        src=[p.relative_to(ROOT).as_posix()]+([q.relative_to(ROOT).as_posix()] if q.exists() else [])
        add('EXP:'+p.parent.name,v.get('label',p.parent.name),'Formal experiments',cat,'Formal validation',note,
            'Respect actual '+freq+' horizon. Price/feed improvements alone are not evidence of new alpha. Reconcile corrected versions, historical universe and execution before reuse.',src,r,
            related=strategy,kind='experiment instance')

def other():
    defs=[
      ('IEX-OF','IEX Order-Flow Predictiveness','economic','data/parquet/alpaca_iex_orderflow_v1/development/report.json','Mean signed midpoint -11.42 bps; crossing plus friction -41.94 bps. The signal failed before and after execution.','Consolidated tape is a measurement improvement, not permission to flip or refit this failed composite.'),
      ('BTC-PROB','BTC Five-Minute Probability Model','pending','data/parquet/bitcoin_5m_probability_binance_v1/report.json','A statistical directional model, not an executable trading strategy. Small probability discrimination does not establish an edge over market prices.','Fresh executable market probabilities/quotes, calibrated net expected value and independent days.'),
      ('BTC-SQUEEZE','Confirmed Short-Squeeze Continuation','protocol','data/parquet/bitcoin_confirmed_short_squeeze_continuation_v1/feasibility/report.json','Returns-blind feasibility stopped the frozen intersection of funding, OI, premium and spot-flow states. No profitability test.','Sparse conditions/availability must be distinguished; do not relax thresholds after seeing counts.'),
      ('BTC-UNWIND','Crowded Long Unwind','robustness','data/parquet/bitcoin_crowded_long_unwind_binance_v1/development/report.json','Only 15 selected days, none in 2022; uncertainty included losses. Positive pooled gross expectancy did not satisfy sample/robustness gates.','More independent occurrences, not a threshold optimized to create them.'),
      ('BTC-CARRY','Delta-Neutral Funding Carry','protocol','data/parquet/bitcoin_delta_neutral_funding_carry_binance_v1/internal_validation/report.json','41 development trades passed, but 2023 validation produced zero qualifying trades. Seven-day holds are outside day trading.','Regime participation and funding/capital/quote execution; do not call development success a day-trading solution.'),
      ('BTC-BASIS','Spot/Perpetual Basis Convergence','economic','data/parquet/bitcoin_spot_perp_basis_convergence_binance_v1/development/report.json','Gross +1.03 bps of capital per selected event became -23.97 bps under conservative costs despite 68.8% contraction accuracy.','Small convergence is not enough for four-leg friction; no hypothetical midpoint fill rescue.'),
      ('BTC-CLOSE','BTC US-Session Close Momentum','economic','data/parquet/bitcoin_us_session_close_momentum_binance_v1/development/report.json','621 selected sessions; mean gross -0.62 bps, conservative -30.62 bps. Price momentum did not transfer economically.','No identified new-data fix for this exact rule.'),
      ('SEC-CONT','SEC Item 2.02 Stock Continuation','economic','data/parquet/sec_item_202_premarket_continuation_v1/development/report.json','411 events; stock mean +5.24 bps gross and -4.76 bps after fixed costs; residual net -0.90 bps. Coverage and uncertainty gates also failed.','Original announcement content and prior expectations would be new information; filing presence and initial return alone were tested.'),
      ('FUND-REV','Fundamental Event Smart Reversal','economic','docs/reports/fundamental_event_smart_reversal_scout.json','Gross -5.56%, wrong-sign near-zero rank IC, default net -43.47%. SEC-veto proxy was incomplete, but core signal already lacked gross edge.','News/expectation data could define a different signal; not a demonstrated repair for reversal.'),
      ('CARRY-TREND','Cross-Asset Carry plus Trend','outside_daytrade_positive','docs/reports/cross_asset_carry_trend_scout.json','Public-data scout passed, net Sharpe 0.608 with SPY diversification utility. Daily futures carry/trend is outside the intraday mandate and not formally validated.','Raw-contract replication, roll/cost/capital checks; useful separate program, not day-trade proof.'),
    ]
    for id,name,cat,s,note,gap in defs:
        src=[s]
        if id=='BTC-CARRY':src.append('data/parquet/bitcoin_delta_neutral_funding_carry_binance_v1/development/report.json')
        add(id,name,'Other scouts',cat,'Recorded scout / validation',note,gap,src,read(ROOT/s))
    mddefs=[
      ('IBB','IBB Afternoon Recovery','economic','docs/research_scout/IBBIntradayAfternoonRecovery-v1-results.md','124 trades; mean gross -0.092%, net -0.192%; both chronological halves negative. An individual ETF was already tested.','No post-loss threshold, time or ETF substitution.'),
      ('SPY-CORR','SPY Opening-Hour Correlation','economic','docs/research_scout/SPYOpeningHourCorrelation-v1-results.md','721 sessions; first/last Pearson 0.0285, Spearman -0.0391; conditional spread negative. This is a descriptive prediction failure, not a net-P&L backtest.','No demonstrated payoff edge; more attractive clock selection is not independent evidence.'),
      ('POLY-PROXY','BTC Model to Polymarket Outcome Transfer','pending','docs/research_scout/Bitcoin5mPolymarketProxyCheck-v1.md','3,951 matched outcomes over 14 already-exposed days; slight Brier improvement with interval including zero. No contemporaneous executable decision prices.','Forward paired model probabilities and executable asks/depth; label accuracy alone cannot measure trading edge.'),
      ('BTC-CAPITULATION','Binance Capitulation to Coinbase Spot','pending','research_scout/bitcoin_binance_capitulation_coinbase_spot_v1.json','Frozen proposal located; no completed result artifact found for this exact cross-venue rule.','Establish source/target price alignment and availability before evaluating returns.'),
      ('IREN','IREN Two-Month Reversal','scope','experiments/iren_two_month_reversal_v1/results.json','Two-month return-recurrence study lies outside the day-trading objective; retained for complete repository history.','Do not present a multi-month result as intraday evidence.'),
    ]
    for id,name,cat,s,note,gap in mddefs: add(id,name,'Other scouts',cat,'Recorded scout or proposal',note,gap,[s],read(ROOT/s) if s.endswith('.json') else None)

def proposals_and_diagnostics():
    # Preserve screened and unimplemented ideas, with explicit lineage instead of
    # silently counting proposal aliases as independent completed backtests.
    definitions=[
      ('V15-R1','Early Closing-Rebalance Footprint','semantic','research_scout/UPRO_SPXU_DESK_GRADE_HYPOTHESIS_SCREEN_V15.md','Unsigned ETF share volume did not measure derivative hedge demand; weaker proxy for already-tested closing flow.','Later AUM/flow acquisitions led to V61–V67; those outcomes supersede the old claim that all these inputs remain absent.','V63; V67'),
      ('V15-R3','Primary/Secondary-Market Convexity Gap','data','research_scout/UPRO_SPXU_DESK_GRADE_HYPOTHESIS_SCREEN_V15.md','Intraday NAV/baskets and financing marks unavailable; trade-price residual not proof of AP imbalance.','Daily NAV/shares were later acquired. Intraday basket valuation and actual hedge demand remain different missing objects.','V59–V62; V68–V70'),
      ('V15-R4','Futures-Cash Basis Relay','data','research_scout/UPRO_SPXU_DESK_GRADE_HYPOTHESIS_SCREEN_V15.md','Asynchronous minute prints cannot measure executable basis; a one-legged index bet mismatches the hedge.','Synchronized quotes, fair-carry inputs and realistic two-leg execution; fast arbitrage economics remain unproven.','V90 is maturity spread, not the same basis'),
      ('V15-R5','Constituent-Breadth Internalization Gap','data','research_scout/UPRO_SPXU_DESK_GRADE_HYPOTHESIS_SCREEN_V15.md','Historical membership, corporate actions and timestamped opening information absent.','Later first-hour panels improve breadth but not point-in-time membership; V75–V77 failed different specific constructions.','V75–V77'),
      ('V35-R1','Final Auction-Sign Reversal','semantic','research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md','Rejected as outcome-derived inversion of failed V34. No P&L.','A new name or sign does not reset multiplicity.','V34'),
      ('V35-R2','Closing-Auction After-Close Continuation','scope','research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md','After-close continuation violated the flat-by-close mandate. No P&L.','An overnight mandate is different; pre-close alternatives V41/V42 were subsequently screened.','V41; V42'),
      ('V35-R3','Exceptional Freeze/Extension/Collar Events','data','research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md','Sparse exceptional events and incomplete venue-code semantics. No P&L.','Validated event semantics and a rare-event research mandate, not a frequent-strategy claim.','V52 routine freeze is distinct'),
      ('V35-R4','Pure Cross-Leverage Quote Lag','data','research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md','Quote age and full updates missing from minute/trade-associated snapshots. No P&L.','Opening MBP-1 partially changes availability; historical SIP and actual execution latency remain to be admitted.','V49; V84 is replenishment, not parity lag'),
      ('V35-R5','Auction-Only versus Continuous Clearing Disagreement','data','research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md','Continuous clearing-price field insufficiently populated for the proposed opening comparison. No P&L.','Validate populated venue/schema semantics before defining a signal.','V53 related but different wedge'),
      ('V44-S1','Scheduled Macro Delayed Discovery Proposal','alias','research_scout/SPY_DAY_TRADING_HYPOTHESIS_SCREEN_V44.md','Proposal later implemented as V45 and rejected.','Use V45 as the economic evidence, not the older optimistic proposal.','V45'),
      ('V44-S2','Credit-to-Equity Delayed Stress Diffusion','data','research_scout/SPY_DAY_TRADING_HYPOTHESIS_SCREEN_V44.md','Required synchronized HYG/IEI intraday prices absent; bond marks and direction identification uncertain.','Existing SIP may supply the ETF leg, but duration/credit decomposition and causality still need validation.','V79 is primary flow, not an exact test of this credit residual'),
      ('V44-S3','SEC Earnings-Information Breadth Proposal','alias','research_scout/SPY_DAY_TRADING_HYPOTHESIS_SCREEN_V44.md','Later related V73 and V85 evaluated earnings transmission and failed; proposal itself is not another pass.','Do not claim broad earnings read-through was never investigated.','V73; V85'),
      ('V44-S4','Megacap Breadth versus SPY Disagreement','semantic','research_scout/SPY_DAY_TRADING_HYPOTHESIS_SCREEN_V44.md','Static twenty-name selection, coarse bars and consumed breadth lineage caused screen rejection.','Point-in-time universe is a real gap, but it does not validate another breadth vote.','V11; V13; V75–V77'),
      ('V44-S5','Same-Day Volatility-Control Deleveraging','semantic','research_scout/SPY_DAY_TRADING_HYPOTHESIS_SCREEN_V44.md','Realized variance did not identify actual mandates or selling; adjacent to consumed variance states.','Observable mandate exposures/trading schedules rather than assumed same-day flows.','V9; V63'),
      ('DT1','Opening Range Breakout Proposal','alias','docs/research_scout/DayTradeAlgorithmCandidates-v1.md','Later formal ETF ORB experiment failed.','Use the actual experiment, not the original proposal ranking.','EXP:b561f4a3-d360-4e1e-b663-a81a54e63375'),
      ('DT2','Same-Clock Seasonality Proposal','alias','docs/research_scout/DayTradeAlgorithmCandidates-v1.md','Later local formal result failed with operational/holding-period issues as well.','Retain local-evidence status; no favorable clock selection.','EXP:9a08eaef-e9d5-4517-989a-3b35575519d7'),
      ('DT3','Overnight Loser Open-to-Close Reversal','data','docs/strategy_sources/OvernightCrossPeriodReversal-v1.md','Frozen intraday proposal, not an overnight position; no completed result found. Requires historical S&P membership and five-minute stock execution.','Point-in-time universe and stock opening/execution history; related daily reversal failures constrain interpretation but are not this exact test.','Daily reversal families are related, not identical'),
      ('DT4','Intraday ETF Pairs Mean Reversion','pending','docs/research_scout/DayTradeAlgorithmCandidates-v1.md','Proposal located; no completed exact intraday pair experiment found. Daily pairs had zero trades; leveraged wrapper convergence tested separately.','Specify relationship formation, synchronized quotes and capital/borrow before claiming it was tested.','Daily pairs; V68–V70'),
      ('DT5','Sector/Market Lead-Lag Continuation','pending','docs/research_scout/DayTradeAlgorithmCandidates-v1.md','Proposal located; exact broad sector-ETF implementation not found. Prior broad-index diffusion tests were completed and failed.','Show incremental information beyond consumed broad-index momentum; synchronized sector data alone does not establish novelty.','V11; V12; market-to-sector proposal'),
      ('DT6','Cross-Sectional Morning Loser Reversal','pending','docs/research_scout/DayTradeAlgorithmCandidates-v1.md','Proposal located; no completed exact broad-stock morning-reversal result found. IBB afternoon recovery and daily reversal are related evidence.','Historical universe plus precise entry/exit data; no relabeling of IBB or daily reversal outcomes.','IBB; daily reversal; DT3'),
      ('DT7','Source-Faithful Market Intraday Momentum','alias','docs/research_scout/DayTradeAlgorithmCandidates-v1.md','The formal IEX market intraday momentum rule failed; source-faithful reconstruction is not automatically an independent alpha.','Any implementation difference must be stated before reuse.','EXP:004c70b3-81d4-491c-87cf-9a4af22c8574'),
      ('DT8','Pre-FOMC Morning Drift','pending','docs/research_scout/DayTradingCandidatesAfterEvidence-v2.md','Proposal located; no completed exact pre-announcement morning test found. V45 tested post-release delayed discovery, a different clock/mechanism.','Official event timing and enough independent events; frequency is inherently low.','V45 is related, not an exact falsification'),
      ('DT9','Market-to-Sector Delayed Information Diffusion','alias','docs/research_scout/DayTradingCandidatesAfterEvidence-v2.md','Same broad proposal lineage as sector/market lead-lag, not an additional completed backtest.','Refer to DT5; generic sector claims must acknowledge V11/V12 history.','DT5'),
      ('INST1','Point-in-Time Earnings Revision Drift','data','docs/research_scout/InstitutionalSystematicStrategyCandidates-v1.md','Ranked proposal, no exact completed result found. Historical analyst estimate vintages are missing.','Actual timestamped revisions/consensus, event linkage and horizon specification; daily drift is not automatically intraday.','SEC-CONT; FUND-REV; V73; V85 are weaker/different measurements'),
      ('INST2','Point-in-Time Quality/Profitability Momentum','scope','docs/research_scout/InstitutionalSystematicStrategyCandidates-v1.md','Slow fundamental allocation proposal, not completed intraday evidence.','Point-in-time fundamentals would support another horizon, not the current goal.','Daily factor research'),
      ('INST3','Cross-Asset Carry/Trend Proposal','alias','docs/research_scout/InstitutionalSystematicStrategyCandidates-v1.md','Later public-data scout passed; outside day trading and awaiting raw-contract replication.','Use the completed CARRY-TREND evidence.','CARRY-TREND'),
      ('INST4','Announced Cash-Merger Arbitrage','scope','docs/research_scout/InstitutionalSystematicStrategyCandidates-v1.md','Slow event-spread proposal with no exact completed test found; normally carries event risk across sessions.','Deal terms, announcements, breaks, borrow/capital and proper holding mandate.','Not an intraday SPY challenger'),
      ('INST5','Public Index-Reconstitution Flow','data','docs/research_scout/InstitutionalSystematicStrategyCandidates-v1.md','Proposal with no completed exact implementation found. Known effective dates alone do not measure surprise or trade size.','Point-in-time announced additions/deletions, weights, announcement/effective times and executable prices.','Related to flow research but a different institutional event'),
      ('CRYPTO-TREND','Cost-Aware Multi-Asset Crypto Intraday Trend','pending','docs/research_scout/CostAwareCryptoIntradayTrendCandidate-v1.md','Candidate-selection memo; exact estimator/horizons not frozen and no completed result found. No explicit flat-by-date boundary.','Broad symbol history, costs, fixed rule and a declared day-trading session; cannot infer success from trend literature.','BTC-CLOSE and BTC-PROB constrain but do not exactly test it'),
    ]
    for id,name,cat,s,why,gap,rel in definitions:
        add(id,name,'Screened / proposed ideas',cat,'Proposal or causal screen',why,gap,[s],related=rel,kind='proposal alias' if cat=='alias' else 'screened/proposed hypothesis')
    diagnostics=[
      ('DIAG-V2','Late Volume-Clock Curiosity Holdout','research_scout/upro_spxu_late_volume_clock_curiosity_2024_2025.json','Later outcome exposure after the original cadence rejection. Positive pooled P&L but weak years/sides and severe winner dependence; explicitly not clean confirmation.','V2:late_volume_clock_compass'),
      ('DIAG-V4','First Synchronization Pulse Diagnostic','research_scout/first_synchronization_pulse_diagnostic_v4.json','Non-actionable post-failure breakdown; not another independent hypothesis or repaired selection rule.','V4:first_synchronization_pulse'),
      ('DIAG-V6','Density-Invariant Zero-Trade Diagnostic','research_scout/upro_spxu_density_invariant_sync_2026_zero_trade_diagnostic.json','Explains the absence of frozen signals without calculating alternative-rule P&L.','V6'),
      ('DIAG-ES-SCAR','ES Scar Deep-Dive Controls','research_scout/es_prior_close_volume_scar_diagnostic_plan_v1.json','Post-result diagnostic plan completed without parameter changes; controls and attribution are additional exposure, not new confirmation.','ES:es_prior_close_volume_scar_handoff_prereg_v1'),
      ('PROTOCOL-ES','ES Forward Paper Protocol','research_scout/es_forward_paper_validation_protocol_v1.json','Protocol specifies prospective evidence; its existence is not a completed paper session or authorization.','ES benchmark/challenger'),
    ]
    for id,name,s,why,rel in diagnostics:
        add(id,name,'Diagnostics / protocols','diagnostic','Diagnostic or protocol',why,'Preserve original conclusions and exposure history; do not promote diagnostic subsets.',[s],read(ROOT/s),rel,kind='diagnostic')
    add('DIAG-TSM-REPLAY','ETF TSM Runtime Replay','Diagnostics / protocols','diagnostic','Simulation replay',
        'Operational replay passed structural checks, but research ending equity $50,944 and replay mark-to-market $27,759 differ materially. It is not a second alpha validation or proof of economic replication.',
        'Reconcile sizing, target timing, costs and constraints before presenting research returns as deployable runtime returns.',
        ['docs/reports/etf_tsm_engine_replay/etf_tsm_engine_replay.md'],related='Validated daily ETF TSM family',kind='diagnostic')

def attach_support():
    mapping={
      'IEX-OF':'alpaca_iex_orderflow_v1.json','BTC-PROB':'bitcoin_5m_probability_binance_v1.json',
      'BTC-SQUEEZE':'bitcoin_confirmed_short_squeeze_continuation_v1.json','BTC-UNWIND':'bitcoin_crowded_long_unwind_binance_v1.json',
      'BTC-CARRY':'bitcoin_delta_neutral_funding_carry_binance_v1.json','BTC-BASIS':'bitcoin_spot_perp_basis_convergence_binance_v1.json',
      'BTC-CLOSE':'bitcoin_us_session_close_momentum_binance_v1.json','SEC-CONT':'sec_item_202_premarket_continuation_v1.json',
      'IREN':'iren_two_month_reversal_prereg_v1.json'}
    for r in ROWS:
        if r['id'] in mapping:r['sources'].append('research_scout/'+mapping[r['id']])
        if r['id']=='BTC-PROB':r['postmortem']+=' Final-holdout accuracy 51.19%; Brier improvement only 0.000196 over constant prior.'
        if r['id']=='BTC-SQUEEZE':r['postmortem']+=' All inputs passed implemented availability checks; only three stage-two setups across the complete sample versus 50 required trades. Primarily recurrence, not missing input.'
        if r['id']=='IREN':r['postmortem']+=' All four primary success gates failed: raw 42-day lag correlation 0.00317, negative-correlation permutation p=0.599, adjusted p=0.288. This was a descriptive recurrence test, not a completed trading P&L.'
        if r['id']=='V65':r['sources'] += ['research_scout/audit_cftc_transfer_opening_acceptance_v65.py','research_scout/daytrade_batch_v83_v92/backtest.py','research_scout/daytrade_batch_v83_v92/artifacts/FINAL_REPORT.md']
        if r['id']=='V6':r['postmortem']+=' The original artifact calls this prospective because outcomes were uninspected before acquisition; the specification was saved July 26 for data ending July 24. It is a withheld historical extension, not live-forward trading.'
        if r['id'] in ['V37','V40','V49','V68']:r['sources'] += ['research_scout/data_gap_audit_20260907/historical_sip_probe.json','research_scout/data_gap_audit_20260907/local_inventory.json']
        if r['classification']=='outside_daytrade_positive' and r['group']=='Formal experiments':r['sources'].append('docs/reports/etf_tsm_spy_comparison.md')
        r['mechanism']=''
        candidate=r['id'].split(':',1)[1] if r['group']=='Cash ETF batches' and ':' in r['id'] else None
        for s in r['sources']:
            if not s.endswith('.json') or not ('prereg' in s or (r['group']=='ES/MES')): continue
            obj=read(ROOT/s); node=obj
            if candidate:
                candidates=obj.get('candidates',obj.get('hypotheses',[]))
                if isinstance(candidates,dict):node=candidates.get(candidate,{})
                elif isinstance(candidates,list):node=next((x for x in candidates if isinstance(x,dict) and x.get('id')==candidate),{})
            if isinstance(node,str):r['mechanism']=node
            if isinstance(node,dict):
                for k in ['economic_claim','hypothesis','mechanism','economic_hypothesis','signal','purpose']:
                    if isinstance(node.get(k),str):r['mechanism']=node[k];break
            if r['mechanism']:break

def save():
    ids=[r['id'] for r in ROWS]; assert len(ids)==len(set(ids))
    OUT.mkdir(exist_ok=True)
    (OUT/'hypothesis_ledger.json').write_text(json.dumps(ROWS,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    fields=['id','name','group','kind','classification','stage','mechanism','postmortem','what_would_change_the_evidence','related','sources']
    with (OUT/'hypothesis_ledger.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in ROWS:w.writerow({k:'; '.join(r[k]) if k=='sources' else r[k] for k in fields})
    count=Counter(r['classification'] for r in ROWS)
    (OUT/'counts.json').write_text(json.dumps({'records':len(ROWS),'by_classification':count,'by_group':Counter(r['group'] for r in ROWS),'by_kind':Counter(r['kind'] for r in ROWS)},indent=2),encoding='utf-8')
    lines=['# All-hypothesis evidence ledger','', 'These are identifiable research records, not independent statistical trials. Batches are expanded; formal reruns and portfolio combinations remain labeled. Recorded metrics are copied, not recomputed. Fixed-notional P&L is not compounded cash and dollar amounts across different sizing models must not be pooled.','', 'Classification: economic = tested economic/prediction failure; robustness = positive portions but benchmark/generalization/cost/concentration failure; measurement = unstable or invalid observable; data = necessary observation missing; semantic = duplicate or unidentified causal sign; protocol = cadence/component/mandate gate; pending = no completed tradable-edge test; scope = outside day trading; diagnostic = input/benchmark audit; outside_daytrade_positive = positive nonintraday evidence.','']
    for group in dict.fromkeys(r['group'] for r in ROWS):
        lines+=['## '+group,'','| ID | Hypothesis / instance | Classification | Stage |','|---|---|---|---|']
        lines += ['| '+ ' | '.join(str(r[k]).replace('|','/') for k in ['id','name','classification','stage'])+' |' for r in ROWS if r['group']==group]
        lines+=['']
        for r in [r for r in ROWS if r['group']==group]:
            lines+=['### '+r['id']+' — '+r['name'],'','**'+r['classification']+'; '+r['stage']+'.** '+r['postmortem'],'','**What could change the evidence:** '+r['what_would_change_the_evidence'],'']
            if r['mechanism']:lines+=['**Original claim (not established causality):** '+r['mechanism'],'']
            if r['related']: lines+=['**Relationship:** '+r['related'],'']
            lines+=['**Sources:** '+', '.join('['+Path(s).name+']('+str(ROOT/s).replace('\\','/')+')' for s in r['sources']),'']
            if r['recorded_gate_failures']: lines+=['Recorded failed gates: '+ '; '.join(r['recorded_gate_failures'])+'.','']
    (OUT/'ALL_HYPOTHESES.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'records':len(ROWS),'classes':count}))

if __name__=='__main__':
    early(); numbered(); futures(); formal(); other(); proposals_and_diagnostics(); attach_support(); save()
