from copy import deepcopy

import pytest

from research.cpi_model_error import announced_round, chart_date, model_error_event


def chart():
    values = {"CPI Inflation": [".2", "9", ""], "Core CPI Inflation": [".45", "9", ""],
              "Actual CPI Inflation": ["", "-.08", ""], "Actual Core CPI Inflation": ["", ".3026", ""]}
    labels = ["01/11", "01/12", "01/13"]
    return {"chart": {"subcaption": "2022-12"}, "categories": [{"category": [{"label": s} for s in labels]}],
            "dataset": [{"seriesname": s, "data": [{"value": v, "tooltext": s+"{br}"+d+"{br}"}
                         for v, d in zip(a, labels, strict=True)]} for s, a in values.items()]}


def test_year_rollover_is_anchored_to_reference_month():
    assert chart_date("2022-12", "01/12") == "2023-01-12"
    with pytest.raises(ValueError):
        chart_date("2022-2", "10/12")


def test_announced_precision_includes_negative_values():
    assert announced_round("-.079437") == -.1
    assert announced_round(".55061") == .6
    assert announced_round("-.05") == -.1


def test_same_day_model_update_is_never_used():
    event = model_error_event(chart())
    assert event["core_forecast"] == .45 and event["core_vintage_date"] == "2023-01-11"
    assert event["symbol"] == "SPY"
    assert event["bls_url"].endswith("cpi_01122023.htm")


def test_missing_first_actual_is_not_inferred_from_later_data():
    x = deepcopy(chart())
    x["dataset"][3]["data"][1]["value"] = ""
    with pytest.raises(ValueError):
        model_error_event(x)


def test_disagreeing_headline_prevents_trade():
    x = chart()
    x["dataset"][2]["data"][1]["value"] = ".4"
    assert not model_error_event(x)["content_trigger"]
