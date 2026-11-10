import json

from research.bybit_funding_screen import NS, snapshot

TARGET = 8*3600*NS


def line(second,data,seq=1,kind="delta"):
    event = {"topic":"tickers.TESTUSDT","type":kind,"data":{"symbol":"TESTUSDT",**data},"cs":seq,"ts":int((7*3600+59*60+second)*1000)}
    whole = int(second)
    fraction = round((second-whole)*1_000_000_000)
    return f"1970-01-01T07:59:{whole:02d}.{fraction:09d}Z "+json.dumps(event)


def test_known_large_rate_is_routed_without_inventing_missing_settlement():
    rows,_ = snapshot([line(49,{"fundingRate":"-0.003","markPrice":"1"})],TARGET)
    assert rows[0]["route_for_recovery"] and not rows[0]["native_complete"]
    assert rows[0]["missing_fields"] == "nextFundingTime"


def test_delta_carries_only_already_observed_fields_with_provenance():
    rows,_ = snapshot([line(10,{"nextFundingTime":str(TARGET//1_000_000),"markPrice":"1"}),line(49,{"fundingRate":"0.002"},2)],TARGET)
    row = rows[0]
    assert row["native_complete"] and row["route_for_recovery"]
    assert json.loads(row["field_provenance"])["nextFundingTime"]["line_index"] == 1


def test_exact_cutoff_and_later_values_do_not_repair_a_missing_field():
    rows,_ = snapshot([line(49,{"fundingRate":"0.002"}),line(49.75,{"nextFundingTime":str(TARGET//1_000_000),"markPrice":"1"},2)],TARGET)
    assert not rows[0]["native_complete"] and rows[0]["line_index"] == 1


def test_disconnect_and_snapshot_clear_fields():
    initial = line(45,{"fundingRate":"0.003","nextFundingTime":str(TARGET//1_000_000),"markPrice":"1"})
    rows,_ = snapshot([initial,"",line(49,{"fundingRate":"0.003"},2)],TARGET)
    assert not rows[0]["native_complete"]
    rows,_ = snapshot([initial,line(49,{"fundingRate":"0.003"},2,"snapshot")],TARGET)
    assert not rows[0]["native_complete"]


def test_stale_large_rate_does_not_become_a_fresh_signal():
    rows,_ = snapshot([line(40,{"fundingRate":"0.05"})],TARGET)
    assert not rows[0]["route_for_recovery"] and rows[0]["reason"] == "stale_or_invalid_publication"


def test_conflicting_sequence_invalidates_last_observation():
    rows,_ = snapshot([line(48,{"fundingRate":"0.002"},8),line(49,{"fundingRate":"0.05"},7)],TARGET)
    assert not rows[0]["route_for_recovery"] and not rows[0]["sequence_ok"]
