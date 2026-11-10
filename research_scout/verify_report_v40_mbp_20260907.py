"""Independent cash ledger verification and V40 report."""
from pathlib import Path
from decimal import Decimal, getcontext
import json,hashlib
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'research_scout/v40_mbp_replay_20260907'

def main():
    getcontext().prec=40
    r=json.loads((OUT/'economic_result.json').read_text());trades=json.loads((OUT/'trade_ledger.json').read_text());g=json.loads((OUT/'gate_result.json').read_text())
    daily=json.loads((OUT/'daily_returns.json').read_text());cashrows=[];checks={}
    assert len({t['day'] for t in trades})==len(trades)
    assert {t['day'] for t in trades}==set(g['executable_signal_dates'])
    cache=ROOT/'research_scout/v49_mbp_replay_20260907/quote_cache'
    for stage,s in r['stages'].items():
        cash=Decimal(100);fixed=Decimal(0);ts=[t for t in trades if t['stage']==stage]
        mid=Decimal(100);askbid=Decimal(100)
        for t in ts:
            rows=json.loads((cache/(t['day']+'.json')).read_text())['quotes']
            qs={z['target']:z for z in rows if z['symbol']==t['symbol']}
            a,b=qs['09:31:05'],qs['09:35:00']
            assert a['ask']==t['entry_ask'] and b['bid']==t['exit_bid']
            assert pd.Timestamp(t['entry_recv'])<pd.Timestamp(t['exit_recv'])
            assert pd.Timestamp(t['exit_recv']).tz_convert('America/New_York').strftime('%Y-%m-%d')==t['day']
            buy=(Decimal(str(a['ask'])))*Decimal('1.0001');sell=Decimal(str(b['bid']))*Decimal('.9999')
            shares=cash/buy;proceeds=shares*sell;fees=proceeds*Decimal('.0000051')+shares*Decimal('.000119');after=proceeds-fees
            net=after/cash-1;assert abs(float(net)-t['net_return'])<1e-12
            assert abs(daily[stage]['strategy'][t['day']]-float(net))<1e-12
            fixed+=100*net
            cashrows.append({'day':t['day'],'stage':stage,'cash_before':float(cash),'shares':float(shares),'gross_sale_proceeds':float(proceeds),'sell_fees':float(fees),'cash_after':float(after),'ending_position':0})
            cash=after
            mid*=Decimal(str((b['bid']+b['ask'])/(a['bid']+a['ask'])))
            askbid*=Decimal(str(b['bid']/a['ask']))
        assert abs(float(cash)-s['primary']['ending_cash'])<1e-8
        assert abs(float(fixed)-s['primary']['fixed_100_pnl'])<1e-8
        assert sum(v!=0 for v in daily[stage]['strategy'].values())==len(ts)
        benchmark=Decimal(100)
        for v in daily[stage]['SPY'].values():benchmark*=1+Decimal(str(v))
        assert abs(float(benchmark)-s['SPY_total_return_proxy']['ending_cash'])<1e-8
        checks[stage]={'ending_cash_decimal_reconstruction':float(cash),'fixed_100_pnl_reconstruction':float(fixed),'frictionless_midpoint_ending_cash_diagnostic':float(mid),'observed_ask_to_bid_before_extra_costs_ending_cash':float(askbid),'trades':len(ts)}
    verification={'passed':True,'errors':[],'trades_verified':len(trades),'all_original_executable_dates_accounted_for':True,'all_positions_flat_same_day':True,'stages':checks}
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
    (OUT/'verified_cash_ledger.json').write_text(json.dumps(cashrows,indent=2)+'\n')
    lines=['# V40 opening-auction demand consensus — September 7, 2026 UTC','','**Decision: all 14 signal-only gates pass; the costed strategy fails development. No deployment or retuning.**','',
    'V40 buys UPRO when both the 3x and 2x long/inverse ETF pairs show relatively stronger opening-auction quantity surprises on the long side; it buys SPXU when both favor the inverse side. Disagreement means cash. The original trailing 20-session median and strict comparisons are unchanged.','',
    '## Feasibility repaired','',
    f"All original quantity signals are identical to the prior audit. Full MBP-1 updates replace trade-triggered TBBO only for execution evidence. Primary coverage is {g['all_overlap']['primary_quote_coverage_pct']:.2f}% ({g['all_overlap']['executable_signals']}/{g['all_overlap']['signals']} overlap signals), versus 89.44% previously. Relevant-side 1x/2x/3x ladder coverage is 100%, versus 69.85%. Both delay targets exist for all 433 executable signals.",'',
    'The original economic development window is March 28–December 2023. The 2021–2022 records contribute to the original signal-frequency and history checks; this does not claim a 2021–2022 execution backtest.','',
    '## Costed results','',
    'Every stage starts independently at $100. SPY is a buy-and-hold adjusted-price total-return proxy over the same full stage calendar, including strategy cash days.','',
    '| Stage | Trades | Strategy ending cash | SPY ending value | Strategy return | Daily-close drawdown |','|---|---:|---:|---:|---:|---:|']
    for name,s in r['stages'].items():
        m=s['primary'];lines.append(f"| {s['start']}–{s['end']} ({name.replace('_',' ')}) | {m['trades']} | ${m['ending_cash']:.2f} | ${s['SPY_total_return_proxy']['ending_cash']:.2f} | {m['total_return']:.2%} | {m['max_daily_drawdown']:.2%} |")
    dev=r['stages']['development'];dm=dev['primary']
    lines+=['',f"Development win rate is {dm['win_rate']:.2%}, profit factor {dm['profit_factor']:.3f}, daily Sharpe {dm['sharpe']:.3f}, and mean net return {dm['mean_trade_bps']:.3f} basis points per trade. Fixed $100 per trade loses ${-dm['fixed_100_pnl']:.2f}. The five-session block-bootstrap 95% interval for mean daily excess versus SPY is [{dev['bootstrap_mean_daily_excess_95'][0]*100:.3f}%, {dev['bootstrap_mean_daily_excess_95'][1]*100:.3f}%]. It does not support excess performance.",'',
    '| Development robustness check | Ending cash |','|---|---:|',
    f"| Additional one-cent adverse entry and exit | ${dev['cent_stress']['ending_cash']:.2f} |",f"| Remove the ten best trades | ${dev['remove_top_ten']['ending_cash']:.2f} |"]
    for clock,v in dev['delays'].items():lines.append(f"| Entry at {clock}, matched dates | ${v['delayed']['ending_cash']:.2f} |")
    lines+=['','## Why it fails','',
    f"In development, frictionless midpoint movement averages {dm['mean_trade_bps']+dev['mean_midpoint_to_net_drag_bps']:.3f} basis points per trade, while spread plus modeled execution drag averages {dev['mean_midpoint_to_net_drag_bps']:.3f} basis points. The measured movement is too small to pay execution costs. Midpoints are a diagnostic, not attainable fill prices.",'',
    f"The development midpoint-only diagnostic ends at ${checks['development']['frictionless_midpoint_ending_cash_diagnostic']:.2f}; crossing the observed ask/bid alone ends at ${checks['development']['observed_ask_to_bid_before_extra_costs_ending_cash']:.2f}, before the additional slippage and fees. Thus the rejection does not depend solely on the extra fee assumptions.",'',
    'The original delay variants also lose. Both 2024 and 2025 lose separately, and the available complete 2026 prefix loses. Later periods are descriptive, contaminated history and cannot rescue the failed development test.','',
    '## Controls','',
    'Controls use the same primary signal dates; they are diagnostics, not newly optimized standalone strategies. The price control compares UPRO and SPXU official close-to-open returns; the raw participation control compares unnormalized UPRO+SSO and SPXU+SDS opening shares. Definitions were frozen before P&L.','',
    '| Development control | Ending cash |','|---|---:|']
    for name,c in dev['controls'].items():lines.append(f"| {name.replace('_',' ')} | ${c['metrics']['ending_cash']:.2f} |")
    lines+=['','All control missing/cash dates and matched-session passive SPY statistics are in `economic_result.json`. No control was selected to replace the primary rule.','',
    '## Execution, coverage and verification','',
    '- Primary entry crosses the first valid observed ask after 09:31:05; exit crosses the bid after 09:35, within the original 60-second wait cap. All trades are fractional long UPRO/SPXU and flat the same day.',
    '- Costs are observed spread plus one basis point per side, then a fixed sell-notional rate of 0.0000051 and $0.000119/share. Zero commission is assumed. These are research assumptions, not a reconstruction of historical broker fees. Fractional execution, settlement and capacity are not operationally validated.',
    '- The full-quote dataset lacks 28 requested late-2026 sessions. Twelve original signals remain unresolved. The 2026 equity result ends June 11, before the first missing local session, rather than treating missing signals as cash. No result through July 24 is claimed.',
    '- Benchmark data come from cached Yahoo adjusted OHLC; the downloader rescales OHLC by adjusted-close/raw-close. This is a total-return proxy, not an independently reconstructed dividend ledger. SPY benchmark friction is omitted, making this comparison slightly more demanding for the strategy.',
    '- All 433 executable original dates are accounted for. An independent high-precision cash ledger reconstructed shares, proceeds, sell fees, fixed-dollar P&L and compounded cash, matched cached quote prices, and checked same-day flat positions. No verification errors.',
    '- Full-period and daily-close metrics do not measure intraday drawdown. No timing, rolling length, sign, threshold or filter was changed after outcomes. No trades, purchases or external account changes occurred.','',
    '## Current position','',
    'V40 is now an economic rejection, rather than a quote-data blocker. V49 remains a signal-stability rejection. Neither supplies a validated SPY-beating intraday strategy. The useful distinction is that V40 could be measured consistently, but its price movement did not cover execution costs.','',
    'Evidence: `specification.json`, `gate_result.json`, `gate_verification.json`, `economic_scope.json`, `economic_result.json`, `trade_ledger.json`, `daily_returns.json`, `verified_cash_ledger.json`, and `verification.json`. Original historical artifacts are preserved.','']
    (OUT/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(verification,indent=2))

if __name__=='__main__':main()
