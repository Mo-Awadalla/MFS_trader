"""Dated public-model forecast error; not a market-consensus surprise."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def chart_date(period, label):
    year, month = (int(z) for z in period.split("-"))
    mm, dd = (int(z) for z in label.split("/"))
    # Historical monthly charts begin in the target month and extend into the next two.
    if mm < month:
        year += 1
    result = date(year, mm, dd)
    if not 0 <= (result-date(int(period.split("-")[0]), month, 1)).days <= 100:
        raise ValueError("Unrecognized monthly chart date")
    return result.isoformat()


def announced_round(value):
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def model_error_event(chart):
    period = chart["chart"]["subcaption"]
    labels = [x["label"] for x in chart["categories"][0]["category"] if x.get("vline") != "true"]
    series = {s["seriesname"]: s["data"] for s in chart["dataset"]}
    used = ["CPI Inflation", "Core CPI Inflation", "Actual CPI Inflation", "Actual Core CPI Inflation"]
    assert all(len(series[s]) == len(labels) for s in used)
    real = {}
    for name in used[2:]:
        observations = [(i, x) for i, x in enumerate(series[name]) if x["value"] != ""]
        if len(observations) != 1:
            raise ValueError("Missing or ambiguous first release")
        i, item = observations[0]
        assert item["tooltext"].split("{br}")[1] == labels[i]
        real[name] = (i, item["value"])
    at = real[used[2]][0]
    assert at == real[used[3]][0]
    release = chart_date(period, labels[at])
    result = {"reference_month": period, "release_date": release, "actual_chart_index": at,
              "bls_url": "https://www.bls.gov/news.release/archives/cpi_"+release[5:7]+release[8:]+release[:4]+".htm"}
    for forecast, actual, prefix in [(used[0], used[2], "headline"), (used[1], used[3], "core")]:
        earlier = [(i, x) for i, x in enumerate(series[forecast])
                   if x["value"] != "" and chart_date(period, labels[i]) < release]
        if not earlier:
            raise ValueError("No strictly prior dated forecast")
        idx, item = earlier[-1]
        assert item["tooltext"].split("{br}")[1] == labels[idx]
        vintage = chart_date(period, labels[idx])
        if not 1 <= (date.fromisoformat(release)-date.fromisoformat(vintage)).days <= 5:
            raise ValueError("Forecast more than five days old")
        result.update({prefix+"_forecast": float(item["value"]), prefix+"_vintage_date": vintage,
                       prefix+"_forecast_chart_index": idx, prefix+"_first_actual_unrounded": float(real[actual][1]),
                       prefix+"_announced": announced_round(real[actual][1])})
        result[prefix+"_error_pp"] = result[prefix+"_announced"]-result[prefix+"_forecast"]
    c, h = result["core_error_pp"], result["headline_error_pp"]
    result["symbol"] = "SPY" if c <= -.10 and h < 0 else "SH" if c >= .10 and h > 0 else ""
    result["content_trigger"] = bool(result["symbol"])
    return result
