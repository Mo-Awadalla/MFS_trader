"""Meaningful causal-feature and trading-accounting checks for this research."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent))
from run import enhanced_features,ledger


def run():
    times=pd.date_range('2025-01-01',periods=400,freq='5min',tz='UTC')
    price=100*np.exp(np.arange(400)*.0001+np.sin(np.arange(400))*.0002)
    b=pd.DataFrame(dict(open_time=times,open=price,close=price*1.0001,high=price*1.0003,low=price*.9997,
                        volume=np.ones(400)*10,taker_buy_base_volume=np.ones(400)*6))
    a=enhanced_features(b)
    altered=b.copy()
    for col in ['open','close','high','low','volume','taker_buy_base_volume']:
        altered.loc[310:,col]*=3
    changed=enhanced_features(altered)
    pd.testing.assert_frame_equal(a.loc[:times[310]],changed.loc[:times[310]])
    # Exactly known long/short price payoff and funding event inside the interval.
    b2=b.iloc[:5].copy()
    b2['open']=[100,101,102,103,104]
    p=b2[['open_time']].copy()
    funding=pd.DataFrame(dict(calc_time=[times[0]+pd.Timedelta(milliseconds=5)],last_funding_rate=[.001]))
    long=ledger(p,b2,funding,np.ones(5)*.6,.55,1,'probability')
    short=ledger(p,b2,funding,np.ones(5)*.4,.55,1,'probability')
    np.testing.assert_allclose(long.gross_return.iloc[0],.01,atol=1e-12)
    np.testing.assert_allclose(short.gross_return.iloc[0],-.01,atol=1e-12)
    np.testing.assert_allclose(long.funding_return.iloc[0],-.001,atol=1e-12)
    np.testing.assert_allclose(short.funding_return.iloc[0],.001,atol=1e-12)
    np.testing.assert_allclose(long.net_12bps.iloc[0],.01-.001-.0012*1.005,atol=1e-12)
    h2=ledger(p,b2,funding,np.ones(5)*.6,.55,2,'probability')
    assert (h2.entry_time.iloc[1:].to_numpy()>=h2.exit_time.iloc[:-1].to_numpy()).all()
    gap=ledger(p,b2.drop(index=1),funding,np.ones(5)*.6,.55,2,'probability')
    assert not (gap.entry_time==times[0]).any()
    none=ledger(p,b2,funding,np.ones(5)*.5,.55,1,'probability')
    assert none.empty
    result=dict(status='PASS',checks=['future-bar perturbation leaves current/past features unchanged',
        'long and short quantity/price P&L','millisecond-offset funding cash flow sign and magnitude',
        'both-side notional cost accounting','no overlapping fixed-horizon positions',
        'missing intermediate price blocks a trade','no signal means no trade'])
    (Path(__file__).resolve().parent/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    run()
