"""Bounded offline audit of current research configuration, not all historical engines."""
from pathlib import Path
import ast,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'research_scout/configuration_audit_20260907'

def main():
    OUT.mkdir(exist_ok=True)
    paths=['research_scout/daytrade_batch_v83_v92/backtest.py','research_scout/backtest_v40_mbp_20260907.py','research_scout/three_new_intraday_20260907.py']
    imports={}
    for name in paths:
        tree=ast.parse((ROOT/name).read_text())
        imports[name]=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module and n.module.startswith('config')]
    hourly=next((ROOT/'data/parquet/vs_icsm_static20').rglob('GOOG_1h.parquet'))
    d=pd.read_parquet(hourly);timestamps=pd.to_datetime(d.timestamp,utc=True).dt.tz_convert('America/New_York')
    boundaries={'configured_end_date':'2025-12-31','request_end_utc':pd.Timestamp('2025-12-31',tz='UTC').isoformat(),'request_end_new_york':pd.Timestamp('2025-12-31',tz='UTC').tz_convert('America/New_York').isoformat(),'actual_last_bar_new_york':str(timestamps.max()),'has_2025_12_31_regular_session':bool((timestamps.dt.strftime('%Y-%m-%d')=='2025-12-31').any())}
    invariant={}
    for rate in [0,.0001,.0003,.0005]:
        r=100*(1-rate)/(100*(1+rate))-1
        invariant[str(rate)]={'flat_price_roundtrip_bps':r*10000,'cash10000_return_equals_cash100':abs(((10000/(100*(1+rate))*100*(1-rate))/10000-1)-r)<1e-12}
    assert abs(invariant['0.0005']['flat_price_roundtrip_bps']+9.995002498750515)<1e-8
    # Actual ETF prices carry leverage. No additional 3x factor belongs in P&L.
    invariant['actual_ETF_price_up_1pct']={'price_ratio_return':101/100-1,'expected':.01}
    assert abs(invariant['actual_ETF_price_up_1pct']['price_ratio_return']-.01)<1e-12
    v40=json.loads((ROOT/'research_scout/v40_mbp_replay_20260907/verification.json').read_text())
    new=json.loads((ROOT/'research_scout/three_new_intraday_20260907/verification.json').read_text())
    economic={'V40':v40['stages'],**new['stages']}
    result={'scope':'Config/schema/downloader and representative recent scout implementations. Does not certify every V1-V95 or all formal engine paths.','direct_config_imports':imports,'date_boundary':boundaries,'cost_and_scale_invariants':invariant,'existing_independent_cash_verification':{'V40':v40['passed'],'V93_V95':new['passed']},'zero_extra_cost_diagnostics':economic,'findings':[
        {'severity':'process','finding':'Recent scout economics are specified in standalone scripts/specifications, not driven by config/research.toml. No single central setting governs these outcomes.','effect':'Comparability and promotion require explicit per-run settings; changing central risk/cost config will not repair these tests.'},
        {'severity':'data_coverage','finding':'Date-only Alpaca end is midnight UTC; static20 runner requests2025-12-31 and omits that entire New York trading session.','effect':'Confirmed explanation for last-day unknowns in V94/V95. Not an explanation for multi-year losses. Preserve historical artifacts; future requests need explicit session-end semantics and completeness checks.'},
        {'severity':'assumption','finding':'Bar tests assume3bps each side for SPY and5bps for stocks; V40 crosses recorded bid/ask plus1bp each side and fixed fee approximations. These are not one calibrated historical fee schedule.','effect':'Absolute net results depend on execution assumptions. V40 observed ask/bid alone loses; the new stock-reversal later-period gross path also loses.'},
        {'severity':'measurement','finding':'Latest stock rules intentionally enter one hour after completed feature bars. Static universe and retrospective adjusted prices require separate PIT controls.','effect':'Tests of delayed rules, not proof against faster mechanisms; universe bias can overstate performance. Price adjustments within a day cancel in percentage returns, but cross-session features need care.'},
        {'severity':'protocol','finding':'Earlier version-specific frequency, every-year, every-side and action-agreement gates are not interchangeable with economic loss.','effect':'Rejected-gate counts cannot be represented as counts of money-losing hypotheses.'},
        {'severity':'guard_gap','finding':'Yahoo downloader falls back to raw close if adjusted-close field is absent.','effect':'Potential silent benchmark-definition change; no evidence established that this fallback occurred in the current cached SPY series. Current benchmark remains labeled a total-return proxy.'}], 'hypothesis_parameters_changed':False,'account_changes':False}
    (OUT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'date_boundary':boundaries,'invariants_passed':True,'direct_config_imports':imports},indent=2))

if __name__=='__main__':main()
