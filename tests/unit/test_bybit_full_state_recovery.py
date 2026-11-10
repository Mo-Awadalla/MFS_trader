import pandas as pd

from research.bybit_full_state_recovery import advance_snapshots


def rows(values):
    return pd.DataFrame([{"exchange":"bybit","symbol":s,"timestamp":t,"local_timestamp":t,
                          "funding_timestamp":1000,"funding_rate":r,"mark_price":2.} for s,t,r in values])


def test_strict_asof_and_symbol_specific_ties():
    selected={8:{}}
    advance_snapshots(rows([("AUSDT",50,.001),("BUSDT",60,.003),("AUSDT",60,.002),("AUSDT",60,.004),("AUSDT",100,.05)]),selected,0,{8:100})
    assert selected[8]["AUSDT"]["funding_rate"]==.004
    assert selected[8]["AUSDT"]["source_position"]==3
    assert selected[8]["BUSDT"]["funding_rate"]==.003


def test_chunks_preserve_old_cutoff_and_update_later_cutoff():
    selected={8:{},16:{}}
    advance_snapshots(rows([("AUSDT",50,.001)]),selected,0,{8:100,16:200})
    advance_snapshots(rows([("AUSDT",120,.002),("BTCUSD",130,.5)]),selected,10,{8:100,16:200})
    assert selected[8]["AUSDT"]["funding_rate"]==.001
    assert selected[16]["AUSDT"]["funding_rate"]==.002 and selected[16]["AUSDT"]["source_position"]==10
    assert "BTCUSD" not in selected[16]


def test_new_unknown_field_is_not_replaced_by_old_known_value():
    selected={8:{}}
    advance_snapshots(rows([("AUSDT",50,.003),("AUSDT",60,float("nan"))]),selected,0,{8:100})
    assert selected[8]["AUSDT"]["funding_rate"] is None
