"""Original V40 gates with existing full-quote cache; preserves historical outputs."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from research_scout import audit_leveraged_etf_opening_auction_demand_consensus_v40 as original

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research_scout/v40_mbp_replay_20260907'
CACHE=ROOT/'research_scout/v49_mbp_replay_20260907/quote_cache'

def main():
    OUT.mkdir(exist_ok=True)
    spec={'created_utc':datetime.now(timezone.utc).isoformat(),'original_code_sha256':hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest(),'measurement_amendment':'Use already extracted MBP-1 earliest valid event quote at each original execution target instead of trade-triggered TBBO. Original signals, dates, thresholds, exclusions and denominators unchanged.','features':'2021-01-01 through 2026-07-24; execution original overlap starts 2023-03-28','quote_source':str(CACHE.relative_to(ROOT)),'economic_stage_only_if_all_gates_pass':True,'economic_preregistration':{'development':['2023-03-28','2023-12-31'],'later_stages':'2024-2025 contaminated validation and available 2026 extension reported separately; none is pristine confirmation','entry':'09:31:05 ask','exit':'09:35:00 bid','delays':['09:31:01','09:32:00'],'capital':'$100 compounded, and fixed $100 per trade; idle cash zero interest','costs':'Observed spread plus 1bp adverse execution each side, sell notional fee 0.0000051 plus $0.000119/share; fixed research assumptions, not historical fee reconstruction. Stress adds $0.01/share on each side.','robustness':'Matched delay subsets, remove top ten primary trades, 5-session block bootstrap excess versus SPY total return (5000 draws, seed 400907).','benchmark':'SPY adjusted daily close total-return proxy, first day adjusted open to close then close-to-close, over full stage calendar; separate matched-session passive SPY and same-window SPY ask-to-bid controls. Missing signal execution is unresolved, not cash.','controls':'Original overnight sign; prior-close-to-official-open UPRO return minus SPXU return sign; raw UPRO+SSO opening quantity minus SPXU+SDS sign (deliberately unnormalized raw participation control); prior trading-session consensus direction. Controls use matched executable primary dates; no sign optimization. Relevant 1x/2x/3x ladder also reported.','admission':'Development compounded net return must exceed SPY; bootstrap lower 95% excess bound >0; cent stress and remove-top-ten must remain profitable. Failure is terminal; later historical stages descriptive only.','limits':'Full local quotes absent for 28 late-2026 dates; never invent fills or mark missing signals as cash. Fractional fills, settlement and executable capacity not operationally validated; daily drawdown only.'}}
    with (OUT/'specification.json').open('x',encoding='utf-8') as f:json.dump(spec,f,indent=2)
    rows=[r for p in sorted(CACHE.glob('*.json')) for r in json.loads(p.read_text())['quotes']]
    load=original.shared.load_json
    with patch.object(original.shared,'load_json',side_effect=lambda path: {'returns_read':False,'quotes':rows} if path==original.shared.TARGET_QUOTES else load(path)),patch.object(original,'OUTPUT',OUT/'gate_result.json'):
        original.main()
    result=json.loads((OUT/'gate_result.json').read_text())
    prior=json.loads((ROOT/'research_scout/leveraged_etf_opening_auction_demand_consensus_returns_blind_audit_v40.json').read_text())
    assert result['signals']==prior['signals'], 'Quote substitution must not change quantity signals'
    assert hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest()==spec['original_code_sha256']
    (OUT/'gate_verification.json').write_text(json.dumps({'original_signals_identical':True,'original_code_unchanged':True,'gate_passed':result['gate_passed'],'failed_gates':[k for k,v in result['gates'].items() if not v],'quote_states':len(rows)},indent=2))

if __name__=='__main__':main()
