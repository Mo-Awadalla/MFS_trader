"""Three new, frozen, offline UPRO/SPXU experiments; no orders or downloads."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal, getcontext
from pathlib import Path

import exchange_calendars as xc
import numpy as np
import pandas as pd

from research.intraday_contract import Costs, Leg, benchmark_returns, evaluate, path_metrics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/leveraged_three_v99_v101_20260907"
INPUTS = {
    "transcripts": "research_scout/v98_earnings_answers_20260907/eligible_events.json",
    "sec": "data/parquet/sec_filings/sec_filing_events.parquet",
    "spy_minutes": "external_artifacts/databento_fractional_etf/ARCX.PILLAR/bars/spy_sh_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst",
    "etf_quotes": "external_artifacts/databento_leveraged_etf/ARCX.PILLAR/bbo/upro_spxu_bbo_1m_2021-01-01_2026-01-01.dbn.zst",
    "condition": "external_artifacts/databento_fractional_etf/ARCX.PILLAR/dataset_condition_2021_2025.json",
    "benchmark": "data/parquet/equity/yahoo_chart/SPY_1d.parquet",
    "archive": "research_scout/postmortem_20260907/hypothesis_ledger.json",
}
START, END = "2021-01-04", "2023-12-29"
NY = "America/New_York"
TOPICS = {
    "demand": r"\b(?:demand|orders|order intake|bookings?|backlog|unit volumes?|sales volumes?|customer traffic|guest traffic)\b",
    "cost": r"\b(?:input costs?|freight costs?|raw material costs?|commodity costs?|transportation costs?|cost inflation|supply chain(?: costs?| disruptions?| constraints?| pressures?| bottlenecks?))\b",
}
CUES = {
    "demand": {
        1: r"^(?:strong\w*|strength\w*|grow\w*|grew|improv\w*|robust|resilien\w*|accelerat\w*|healthy|recover\w*|increas\w*)$",
        -1: r"^(?:slow\w*|weak\w*|declin\w*|decreas\w*|soft\w*|contract\w*|deteriorat\w*|reduc\w*|lower|fall\w*|fell)$",
    },
    "cost": {
        1: r"^(?:increas\w*|rise|rises|rising|rose|higher|upward|elevated|worsen\w*)$",
        -1: r"^(?:declin\w*|decreas\w*|abat\w*|moderat\w*|eas\w*|normaliz\w*|improv\w*|lower|reduc\w*|fall\w*|fell)$",
    },
}


def save(name, obj, *, exclusive=False):
    OUT.mkdir(exist_ok=True)
    with (OUT / name).open("x" if exclusive else "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.write("\n")


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def spec_name():
    if (OUT / "specification_repair2.json").exists():
        return "specification_repair2.json"
    return "specification_repair1.json" if (OUT / "specification_repair1.json").exists() else "specification.json"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def calendars():
    us = xc.get_calendar("XNYS", start="2017-01-01", end="2023-12-31").schedule
    uk = xc.get_calendar("XLON", start="2020-12-01", end="2023-12-31").schedule
    us.index = us.index.strftime("%Y-%m-%d")
    uk.index = uk.index.strftime("%Y-%m-%d")
    return us, uk


def at(day, clock, tz=NY):
    return pd.Timestamp(f"{day} {clock}", tz=tz)


def london_times(day, offset_minutes=0):
    anchor = at(day, "16:30", "Europe/London") + pd.Timedelta(minutes=offset_minutes)
    return {
        "start": anchor - pd.Timedelta(minutes=10),
        "end": anchor + pd.Timedelta(minutes=10),
        "available": anchor + pd.Timedelta(minutes=10, seconds=5),
        "entry": anchor + pd.Timedelta(minutes=11),
        "exit": anchor + pd.Timedelta(minutes=60),
    }


def freeze():
    spec = {
        "created_utc": datetime.now(UTC).isoformat(),
        "status": "frozen before new candidate features and returns",
        "objective": "Three new hypotheses, traded using actual UPRO/SPXU prices, fully funded and flat daily; beat SPY total wealth after costs.",
        "period": [START, END],
        "later_history": "No candidate outcomes after 2023 will be evaluated by this experiment. 2021-2025 has extensive prior research exposure; this is falsification, not pristine confirmation.",
        "V99": {
            "name": "Cost relief versus demand destruction",
            "mechanism": "A fall in business input-cost pressure has different equity implications when customer demand holds up than when demand deteriorates. A cross-company narrative may be incorporated into index risk more slowly than individual earnings headlines.",
            "new_measurement": "Prepared-remarks demand and input-cost language changes versus the same issuer's preceding admitted transcript 45-200 calendar days earlier; no Q&A, fitted forecast, future language model, company return, or V98 prediction is used.",
            "text_rule": "Split at sentence punctuation/newlines/semicolon and but/however/whereas/while. For each topic use cues within eight words of the topic span, excluding the topic itself. Abstain on conflicting directions or no/not/never/without within the local context. Average unambiguous clause signs within document. Demand + means stronger; cost + means greater pressure. Require at least one unambiguous clause in both current and earlier document for a topic delta.",
            "topics": TOPICS,
            "cues": CUES,
            "availability": "Use existing admitted source day, never earlier than max(page published,page modified)+30 minutes, and require strictly before today's 09:30. Current website archive and static surviving issuer coverage are conditional sources, not certified historical publication vintages.",
            "aggregation": "Latest eligible news per issuer in current and preceding four XNYS sessions. Equal weight issuer deltas separately by topic. At least two issuers in each topic, three in their union, and at least one newly available valid event today. Missing topic evidence causes deliberate abstention; known source archive incompleteness remains a source limitation.",
            "action": "If mean cost-pressure delta<0 and demand delta>=0, UPRO. If mean cost-pressure delta<=0 and demand delta<0, SPXU. Otherwise cash. No threshold fitting.",
            "entry": "09:32", "exit": "15:55",
            "controls": ["Demand-delta direction only on primary active dates", "UPRO on primary active dates"],
            "novelty": "Related data domain to V73/V85 and V98, but those measured reporter price diffusion or learned Q&A forecasts for stocks. This measures a specified economic distinction in prepared language and trades the index. No previous outcome sign is flipped or old test reopened.",
        },
        "V100": {
            "name": "European closing-pressure unwind",
            "mechanism": "Global baskets may transmit a temporary pressure pulse into US equities around the European closing auction. If it is deadline pressure, the displacement should partly reverse after the European close.",
            "formation": "SPY exact 1-minute bars from 16:20 through16:39 Europe/London, with positive volume and all20 bars. Compare open-to-final-close log return with sample standard deviation of the previous20 eligible same-window returns, and volume with their median. Require abs(return)>=1sigma and volume>=median. Direction is opposite the displacement.",
            "calendar": "Only full XNYS and full XLON sessions. The anchor follows Europe/London daylight saving, including US/UK mismatch weeks. First20 eligible windows are explicit warmup cash. A missing required window poisons dependent20-window history rather than disappearing from it.",
            "available": "16:40:05 Europe/London", "entry": "16:41 Europe/London", "exit": "17:30 Europe/London",
            "controls": ["Same-signal continuation instead of reversal", "UPRO on primary active dates", "Identical rule at a placebo clock60 minutes later, with its own strictly lagged normalization"],
            "novelty": "Calendar-linked cross-region pressure is distinct from prior SPY opening geometry and same-clock seasonality. London timings are observed; actual European hedger orders are not observed. Pressure transmission is a hypothesis, not an identified causal fact.",
        },
        "V101": {
            "name": "Disclosure congestion and delayed index discovery",
            "mechanism": "A burst of firm disclosures competes for attention. On an unusually busy disclosure morning, a large index repricing may diffuse into remaining portfolios more slowly, creating later continuation.",
            "congestion": "From prior actual XNYS close through today10:25, count distinct CIKs filing nonamended10-K/10-Q or8-K with exact Item2.02. Collapse accessions and issuer repeats; no sentiment or issuer price is used. Require count>=5 and strictly above75th percentile of preceding60 XNYS morning counts. Acceptance+5 minutes is a research dissemination allowance, not first news publication.",
            "price": "SPY exact09:30-10:29 minute bars. Require abs(log(close/open))>= sample standard deviation of previous20 full-session opening-hour returns. Follow the sign.",
            "available": "10:30:05", "entry": "10:32", "exit": "15:55",
            "controls": ["Identical opening shock without the congestion gate, over all eligible days", "Same price shock with five-session-old congestion gate", "UPRO on primary active dates"],
            "novelty": "V73/V85 used the signed price response of reporting companies and peer links. This tests aggregate information-processing load, never reporter return direction. V96's individual filing earliness is also not reused.",
        },
        "common": {
            "capital": "$100, fractional research normalization, one100%-cash long ETF at a time, no additional leverage, cash interest0, no overnight. Each hypothesis has its own account; not three simultaneous100% allocations.",
            "calendar": "All753 XNYS sessions retained in benchmark. Early closes are predeclared cash. Indicator warmup is cash; required market-data gaps are missing, never silently cash.",
            "quotes": "Exact ARCX.PILLAR interval-end bbo-1m snapshots, positive finite noncrossed prices and positive displayed sizes, one unique row per symbol and interval. Never forward-fill or use future quotes to patch a target. ts_event is LAST TRADE time, not quote freshness; record it without imposing a false quote-age filter. Quote change timestamps, NBBO and exact arrival-time fills cannot be certified by these interval snapshots. This is a venue-quote execution scenario.",
            "condition_policy": "Preserve dataset condition flags and report affected fills, but do not decide cash retrospectively from full-day condition metadata. Required interval validation still applies. Positive evidence would need event-level/independent-feed validation.",
            "costs": asdict(Costs()),
            "cost_note": "Buy observed ask and sell bid; add1bp each side and fixed existing research sell fees. No double leverage or double-counted spread. Fees are assumptions, not a dated historical regulatory schedule.",
            "benchmark": "Existing Yahoo adjusted SPY proxy: initial day open-to-close then close-to-close over full calendar, zero benchmark friction.",
            "stresses": "Double extra bps, delay entry1 minute keeping signal/exit fixed, remove five best primary trade days. Controls are diagnostics and cannot be promoted as new discoveries.",
            "inference": "5000 paired five-session circular-block bootstrap draws, seed99100101, central98.333333% intervals for family of3; report index-excess and primary-minus-controls. This corrects this batch only, not the repository's full search history. No minimum-trade or positive-every-year veto.",
            "stop": "Run all three primary backtests. A complete net result below full-calendar SPY is an economic failure; stop that candidate without retuning or opening later years. Missing data makes exact full-calendar result unknown. Positive candidates additionally require stress and incremental-control evidence; none may be called validated from these reused years.",
        },
        "sources": {k: {"path": v, "sha256": sha(ROOT / v)} for k, v in INPUTS.items()},
        "primary_documentation": [
            "https://www.proshares.com/our-etfs/leveraged-and-inverse/upro",
            "https://www.proshares.com/our-etfs/leveraged-and-inverse/spxu",
            "https://docs.londonstockexchange.com/sites/default/files/documents/Service%20Technical%20Description-%2010.11.2020.pdf",
            "https://www.sec.gov/info/edgar/specifications/pds-dissemination-spec022315.pdf",
            "https://databento.com/docs/schemas-and-data-formats/bbo",
        ],
        "packages": {x: importlib.metadata.version(x) for x in ["pandas", "numpy", "databento", "exchange_calendars"]},
    }
    save("specification.json", spec, exclusive=True)
    print("Frozen three new rules and seven existing source hashes.", flush=True)


def text_scores(text):
    clauses = re.split(r"[.!?;\n]+|\b(?:but|however|whereas|while)\b", text.lower())
    evidence = {k: [] for k in TOPICS}
    for clause in clauses:
        tokens = list(re.finditer(r"[a-z]+(?:'[a-z]+)?", clause))
        for topic, pattern in TOPICS.items():
            signs = set()
            for match in re.finditer(pattern, clause):
                left = [i for i, t in enumerate(tokens) if t.end() <= match.start()]
                right = [i for i, t in enumerate(tokens) if t.start() >= match.end()]
                indices = left[-8:] + right[:8]
                words = [tokens[i].group() for i in indices]
                if set(words) & {"no", "not", "never", "without"}:
                    continue
                local = {sign for sign, cue in CUES[topic].items() if any(re.match(cue, w) for w in words)}
                signs |= local
            if len(signs) == 1:
                evidence[topic].append({"sign": signs.pop(), "clause": clause.strip()})
    return {
        topic: {"score": float(np.mean([x["sign"] for x in hits])) if hits else None, "hits": len(hits), "evidence": hits}
        for topic, hits in evidence.items()
    }


def price_window(frame, start, end):
    expected = pd.date_range(start.tz_convert("UTC"), end.tz_convert("UTC"), freq="1min", inclusive="left")
    if (frame.index.get_indexer(expected) < 0).any():
        return None
    window = frame.loc[expected]
    if len(window) != len(expected) or window.index.has_duplicates:
        return None
    a = window[["open", "high", "low", "close", "volume"]].to_numpy(float)
    if not np.isfinite(a).all() or (a <= 0).any():
        return None
    if ((window.low > window[["open", "close"]].min(axis=1)) | (window.high < window[["open", "close"]].max(axis=1))).any():
        return None
    return {"log_return": float(np.log(window.close.iloc[-1] / window.open.iloc[0])), "volume": float(window.volume.sum())}


def normalized_shock(current, history):
    if len(history) < 20:
        return {"status": "warmup"}
    recent = history[-20:]
    if current is None or any(x is None for x in recent):
        return {"status": "missing"}
    sigma = float(np.std([x["log_return"] for x in recent], ddof=1))
    volume_median = float(np.median([x["volume"] for x in recent]))
    return {"status": "known", "sigma": sigma, "volume_median": volume_median, "price_shock": sigma > 0 and abs(current["log_return"]) >= sigma, "direction": int(np.sign(current["log_return"]))}


def filing_counts(frame, us):
    f = frame.drop_duplicates("accession_number").copy()
    earnings = f["items"].fillna("").astype(str).map(lambda s: "2.02" in {x.strip() for x in s.split(",")})
    f = f[f.form.isin(["10-K", "10-Q"]) | ((f.form == "8-K") & earnings)]
    f["accepted"] = pd.to_datetime(f.acceptance_datetime, utc=True)
    out = {}
    for previous, day in zip(us.index, us.index[1:], strict=False):
        select = f[(f.accepted > us.loc[previous, "close"]) & (f.accepted <= at(day, "10:25"))]
        out[day] = {"count": int(select.cik.nunique()), "accessions": sorted(select.accession_number.tolist()), "window_start": us.loc[previous, "close"].isoformat()}
    return out


def order(day, direction, available, entry, exit_, **extra):
    return {"day": day, "direction": direction, "symbol": "UPRO" if direction > 0 else "SPXU", "available": pd.Timestamp(available).isoformat(), "entry": pd.Timestamp(entry).isoformat(), "exit": pd.Timestamp(exit_).isoformat(), **extra}


def transcript_signals(us, days, full):
    events = json.loads((ROOT / INPUTS["transcripts"]).read_text(encoding="utf-8"))
    scored = []
    by_symbol = defaultdict(list)
    examples = []
    for e in sorted(events, key=lambda e: (e["day"], e["available_at"], e["key"])):
        if e["day"] > END:
            continue
        availability = pd.Timestamp(e["available_at"]) + pd.Timedelta(minutes=30)
        assert availability < at(e["day"], "09:30")
        assert pd.Timestamp(e["available_at"]) == max(pd.Timestamp(e["published"]), pd.Timestamp(e["modified"]))
        s = text_scores(e["prepared_text"])
        prior = [p for p in by_symbol[e["symbol"]] if 45 <= (pd.Timestamp(e["day"]) - pd.Timestamp(p["day"])).days <= 200]
        p = prior[-1] if prior else None
        changes = {t: s[t]["score"] - p["scores"][t] if p is not None and s[t]["score"] is not None and p["scores"][t] is not None else None for t in TOPICS}
        row = {"key": e["key"], "symbol": e["symbol"], "day": e["day"], "availability": availability.isoformat(), "prior_key": p["key"] if p else None, "prior_day": p["day"] if p else None, "scores": {t: s[t]["score"] for t in TOPICS}, "hits": {t: s[t]["hits"] for t in TOPICS}, "changes": changes}
        by_symbol[e["symbol"]].append(row)
        scored.append(row)
        # Source-only review examples selected from pre-2021, never by return.
        if e["day"] < START and len(examples) < 30 and s["cost"]["hits"]:
            examples.append({"key": e["key"], "day": e["day"], "symbol": e["symbol"], "evidence": {t: s[t]["evidence"][:2] for t in TOPICS}})
    signals, controls, features = {}, {"demand_only": {}, "UPRO": {}}, {}
    positions = {d: i for i, d in enumerate(us.index)}
    for day in days:
        if day not in full:
            continue
        eligible = [e for e in scored if e["day"] in positions and 0 <= positions[day] - positions[e["day"]] <= 4 and any(v is not None for v in e["changes"].values())]
        latest = {e["symbol"]: e for e in eligible}
        groups = {t: [e for e in latest.values() if e["changes"][t] is not None] for t in TOPICS}
        new_today = any(e["day"] == day for e in latest.values())
        complete = min(map(len, groups.values())) >= 2 and len(latest) >= 3 and new_today
        f = {"new_valid_event_today": new_today, "issuers": sorted(latest), "topic_counts": {t: len(g) for t, g in groups.items()}, "keys": [e["key"] for e in latest.values()], "eligible": complete}
        if complete:
            demand = float(np.mean([e["changes"]["demand"] for e in groups["demand"]]))
            cost = float(np.mean([e["changes"]["cost"] for e in groups["cost"]]))
            direction = 1 if cost < 0 and demand >= 0 else (-1 if cost <= 0 and demand < 0 else 0)
            f.update(demand_delta=demand, cost_delta=cost, direction=direction)
            available = max(pd.Timestamp(e["availability"]) for e in latest.values())
            if demand:
                controls["demand_only"][day] = order(day, int(np.sign(demand)), available, at(day, "09:32"), at(day, "15:55"))
            if direction:
                signals[day] = order(day, direction, available, at(day, "09:32"), at(day, "15:55"))
                controls["UPRO"][day] = {**signals[day], "direction": 1, "symbol": "UPRO"}
        features[day] = f
    save("transcript_topic_scores.json", scored, exclusive=True)
    save("pre2021_language_examples.json", examples, exclusive=True)
    return signals, controls, features


def prepare():
    read(spec_name())
    us, uk = calendars()
    days = [d for d in us.index if START <= d <= END]
    full = {d for d in days if us.loc[d, "close"].tz_convert(NY).strftime("%H:%M") == "16:00"}
    signals, controls, features, missing = {}, {}, {}, {}
    signals["V99"], controls["V99"], features["V99"] = transcript_signals(us, days, full)
    missing["V99"] = {}
    print("V99 language features complete; no ETF outcomes calculated.", flush=True)
    import databento as db

    bars = db.DBNStore.from_file(ROOT / INPUTS["spy_minutes"]).to_df()
    bars = bars[(bars.symbol == "SPY") & (bars.index < at("2024-01-01", "00:00"))].sort_index()
    assert not bars.index.has_duplicates
    # Only feature windows are extracted. No candidate exit or ETF return here.
    histories = {"V100": [], "V100_placebo": [], "V101": []}
    for h in ["V100", "V101"]:
        signals[h], features[h], missing[h] = {}, {}, {}
    controls["V100"] = {"continuation": {}, "UPRO": {}, "later_clock": {}}
    controls["V101"] = {"no_congestion": {}, "stale_congestion": {}, "UPRO": {}}
    control_missing = {"V100": {"later_clock": {}}, "V101": {"no_congestion": {}, "stale_congestion": {}}}
    counts = filing_counts(pd.read_parquet(ROOT / INPUTS["sec"]), us)
    congestion = {}
    count_history = []
    for d in us.index:
        if d not in counts:
            continue
        n = counts[d]["count"]
        q = float(np.quantile(count_history[-60:], .75)) if len(count_history) >= 60 else None
        congestion[d] = {"count": n, "prior60_q75": q, "busy": q is not None and n >= 5 and n > q}
        count_history.append(n)
    pos = {d: i for i, d in enumerate(us.index)}
    for day in days:
        if day not in full:
            continue
        if day in uk.index and uk.loc[day, "close"].tz_convert("Europe/London").strftime("%H:%M") == "16:30":
            for label, offset in [("V100", 0), ("V100_placebo", 60)]:
                times = london_times(day, offset)
                current = price_window(bars, times["start"], times["end"])
                norm = normalized_shock(current, histories[label])
                histories[label].append(current)
                f = {"window": current, **norm, "entry": times["entry"].isoformat()}
                target = signals["V100"] if label == "V100" else controls["V100"]["later_clock"]
                if norm["status"] == "missing":
                    target_missing = missing["V100"] if label == "V100" else control_missing["V100"]["later_clock"]
                    target_missing[day] = "incomplete required20-minute window or lagged history"
                elif norm["status"] == "known" and norm["price_shock"] and current["volume"] >= norm["volume_median"]:
                    target[day] = order(day, -norm["direction"], times["available"], times["entry"], times["exit"])
                    if label == "V100":
                        o = target[day]
                        controls["V100"]["continuation"][day] = {**o, "direction": -o["direction"], "symbol": "SPXU" if o["symbol"] == "UPRO" else "UPRO"}
                        controls["V100"]["UPRO"][day] = {**o, "direction": 1, "symbol": "UPRO"}
                features["V100"].setdefault(day, {})[label] = f
        current = price_window(bars, at(day, "09:30"), at(day, "10:30"))
        norm = normalized_shock(current, histories["V101"])
        histories["V101"].append(current)
        f = {"window": current, **norm, **congestion[day]}
        features["V101"][day] = f
        stale = congestion[us.index[pos[day] - 5]]["busy"]
        if norm["status"] == "missing":
            if f["busy"]:
                missing["V101"][day] = "required opening-hour window or prior20 history missing"
            control_missing["V101"]["no_congestion"][day] = "opening price data missing"
            if stale:
                control_missing["V101"]["stale_congestion"][day] = "opening price data missing"
        elif norm["status"] == "known" and norm["price_shock"]:
            o = order(day, norm["direction"], at(day, "10:30:05"), at(day, "10:32"), at(day, "15:55"))
            controls["V101"]["no_congestion"][day] = o
            if stale:
                controls["V101"]["stale_congestion"][day] = o
            if f["busy"]:
                signals["V101"][day] = o
                controls["V101"]["UPRO"][day] = {**o, "symbol": "UPRO", "direction": 1}
    payload = {"days": days, "signals": signals, "controls": controls, "features": features, "feature_missing": missing, "control_feature_missing": control_missing, "early_close_cash": sorted(set(days) - full)}
    save("signals.json", payload, exclusive=True)
    save("filing_loads.json", {d: {**counts[d], **congestion[d]} for d in counts if START <= d <= END}, exclusive=True)
    save("feature_summary.json", {h: {"proposed_trades": len(signals[h]), "directions": dict(Counter(x["symbol"] for x in signals[h].values())), "missing_feature_dates": list(missing[h])} for h in signals}, exclusive=True)
    print(json.dumps(read("feature_summary.json"), indent=2), flush=True)


def valid_quote(row):
    if row is None or isinstance(row, pd.DataFrame):
        return False
    v = np.array([row.bid_px_00, row.ask_px_00, row.bid_sz_00, row.ask_sz_00], dtype=float)
    return bool(np.isfinite(v).all() and (v > 0).all() and row.bid_px_00 <= row.ask_px_00)


def paired_family_interval(a, b):
    if len(a) != len(b) or not len(a):
        return None
    z = np.array(a) - np.array(b)
    rng = np.random.default_rng(99100101)
    starts = rng.integers(0, len(z), (5000, (len(z) + 4) // 5))
    ix = ((starts[:, :, None] + np.arange(5)) % len(z)).reshape(5000, -1)[:, :len(z)]
    return np.quantile(z[ix].mean(axis=1), [.05 / 6, 1 - .05 / 6]).tolist()


def run():
    spec = read(spec_name())
    if (OUT / "summary.json").exists():
        raise FileExistsError("Outcomes already frozen; do not rerun or tune")
    for source in spec["sources"].values():
        assert sha(ROOT / source["path"]) == source["sha256"]
    save("implementation_freeze.json", {"created_utc": datetime.now(UTC).isoformat(), "files": {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / "tests/unit/test_leveraged_three_v99_v101.py", ROOT / "research/intraday_contract.py"]}, "signals_sha256": sha(OUT / "signals.json"), "specification_sha256": sha(OUT / "specification.json"), "active_specification": spec_name(), "active_specification_sha256": sha(OUT / spec_name())}, exclusive=True)
    payload = read("signals.json")
    days = payload["days"]
    spy = pd.read_parquet(ROOT / INPUTS["benchmark"])
    spy.index = pd.to_datetime(spy.timestamp, utc=True).dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    benchmark = benchmark_returns(spy, days, basis="legacy_adjusted_proxy")
    import databento as db

    quotes = db.DBNStore.from_file(ROOT / INPUTS["etf_quotes"]).to_df()
    quotes = quotes[quotes.index < at("2024-01-01", "00:00")].reset_index().set_index(["symbol", "ts_recv"]).sort_index()
    assert not quotes.index.has_duplicates
    condition = json.loads((ROOT / INPUTS["condition"]).read_text(encoding="utf-8"))
    degraded = {r["date"] for r in condition["conditions"] if r["condition"] == "degraded"}
    evidence = []

    def execute(name, orders, feature_missing, delay=False):
        decisions = dict.fromkeys(days, "cash")
        reasons = dict(feature_missing)
        for day in reasons:
            decisions[day] = "missing"
        legs = []
        for day, o in orders.items():
            entry = pd.Timestamp(o["entry"]) + pd.Timedelta(minutes=int(delay))
            exit_ = pd.Timestamp(o["exit"])
            rows = []
            for role, t in [("entry", entry), ("exit", exit_)]:
                key = (o["symbol"], t.tz_convert("UTC"))
                row = quotes.loc[key] if key in quotes.index else None
                rows.append(row)
                evidence.append({"case": name, "day": day, "role": role, "symbol": o["symbol"], "interval": t.isoformat(), "valid": valid_quote(row), "last_trade_time": pd.Timestamp(row.ts_event).isoformat() if row is not None and pd.notna(row.ts_event) else None, "bid_size": float(row.bid_sz_00) if row is not None else None, "ask_size": float(row.ask_sz_00) if row is not None else None, "degraded_day": day in degraded})
            if not all(valid_quote(r) for r in rows):
                decisions[day] = "missing"
                reasons[day] = "invalid or absent exact entry/exit BBO"
                continue
            a, b = rows
            legs.append(Leg(day, o["symbol"], o["available"], entry.isoformat(), exit_.isoformat(), 1., float(a.bid_px_00), float(a.ask_px_00), float(b.bid_px_00), float(b.ask_px_00)))
            decisions[day] = "trade"
        result = evaluate(legs, decisions, benchmark)
        result["missing_reasons"] = reasons
        result["degraded_trade_days"] = sorted({x.day for x in legs} & degraded)
        save(name + "_evaluation.json", result, exclusive=True)
        save(name + "_legs.json", [asdict(x) for x in legs], exclusive=True)
        save(name + "_decisions.json", decisions, exclusive=True)
        return result

    summary = {}
    for h, orders in payload["signals"].items():
        primary = execute(h, orders, payload["feature_missing"][h])
        delayed = execute(h + "_delay", orders, payload["feature_missing"][h], True)
        controls = {}
        for name, cs in payload["controls"][h].items():
            cm = dict(payload["feature_missing"][h]) if name in {"UPRO", "continuation", "demand_only"} else payload["control_feature_missing"].get(h, {}).get(name, {})
            result = execute(h + "_control_" + name, cs, cm)
            pair_days = sorted(set(primary["daily_returns"]["net"]) & set(result["daily_returns"]["net"]))
            gap = np.array([primary["daily_returns"]["net"][d] - result["daily_returns"]["net"][d] for d in pair_days])
            controls[name] = {"ending_cash": result["ending_cash"], "available_case_ending_cash": result["available_case_metrics"]["net"]["ending_cash"], "missing_dates": result["missing_dates"], "trade_days": result["trade_days"], "paired_known_days": len(pair_days), "primary_minus_control_mean": float(gap.mean()), "family_interval": paired_family_interval(gap, np.zeros(len(gap)))}
        daily = primary["daily_returns"]["net"]
        trade_days = [d for d in orders if d in daily]
        top = sorted(trade_days, key=lambda d: daily[d], reverse=True)[:5]
        removed = path_metrics([0. if d in top else r for d, r in daily.items()])
        ci = paired_family_interval(list(daily.values()), benchmark.loc[list(daily)].to_numpy()) if primary["complete_equity"] else None
        beats = primary["ending_cash"] is not None and primary["ending_cash"] > primary["SPY"]["ending_cash"]
        if not primary["complete_equity"]:
            verdict = "incomplete_data_no_full_calendar_verdict"
        elif not beats:
            verdict = "aborted_economic_failure"
        else:
            checks = delayed["ending_cash"] is not None and delayed["ending_cash"] > 100 and primary["available_case_metrics"]["cost_stress"]["ending_cash"] > 100 and removed["ending_cash"] > 100 and ci[0] > 0 and all(c["primary_minus_control_mean"] > 0 and not c["missing_dates"] for c in controls.values())
            verdict = "historical_candidate_requires_fresh_validation" if checks else "aborted_robustness_or_incrementality_failure"
        summary[h] = {"name": spec[h]["name"], "status": verdict, "complete_equity": primary["complete_equity"], "net_ending_cash": primary["ending_cash"], "reference_ending_cash": primary["available_case_metrics"]["reference"]["ending_cash"] if primary["complete_equity"] else None, "available_case_metrics": primary["available_case_metrics"], "SPY": primary["SPY"], "calendar_sessions": len(days), "trade_days": primary["trade_days"], "missing_dates": primary["missing_dates"], "directions": dict(Counter(o["symbol"] for d, o in orders.items() if d in daily)), "delay_ending_cash": delayed["ending_cash"], "delay_missing_dates": delayed["missing_dates"], "remove_best_five_known_day_metrics": removed, "removed_days": top, "family_adjusted_excess_interval": ci, "controls": controls, "yearly_known_day_metrics": {year: path_metrics([r for d, r in daily.items() if d.startswith(year)]) for year in ["2021", "2022", "2023"]}, "degraded_trade_days": primary["degraded_trade_days"]}
        print(h, verdict, "net", primary["ending_cash"], "trades", primary["trade_days"], "missing", len(primary["missing_dates"]), flush=True)
    save("quote_evidence.json", evidence, exclusive=True)
    save("summary.json", summary, exclusive=True)


def verify():
    getcontext().prec = 40
    checks = {}
    for p in sorted(OUT.glob("*_evaluation.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        cash = Decimal(100)
        c = r["costs"]
        slip = Decimal(str(c["extra_bps_each_side"])) / Decimal(10000)
        fee = Decimal(str(c["sell_notional_rate"]))
        per_share = Decimal(str(c["sell_per_share"]))
        for row in sorted(r["accounting"], key=lambda x: (x["day"], x["entry_time"])):
            assert row["weight"] == 1 and row["symbol"] in {"UPRO", "SPXU"}
            qty = cash / (Decimal(str(row["entry_ask"])) * (1 + slip))
            cash = qty * (Decimal(str(row["exit_bid"])) * (1 - slip) * (1 - fee) - per_share)
            assert pd.Timestamp(row["signal_available"]) < pd.Timestamp(row["entry_time"]) < pd.Timestamp(row["exit_time"])
        error = abs(float(cash) - r["available_case_metrics"]["net"]["ending_cash"])
        assert error < 1e-9
        assert r["calendar_sessions"] == 753
        checks[p.name] = {"decimal_known_day_product": float(cash), "error": error, "complete": r["complete_equity"]}
    spec = read(spec_name())
    assert all(sha(ROOT / s["path"]) == s["sha256"] for s in spec["sources"].values())
    implementation = read("implementation_freeze.json")
    assert all(sha(ROOT / p) == h for p, h in implementation["files"].items())
    assert sha(OUT / "signals.json") == implementation["signals_sha256"]
    assert sha(OUT / "specification.json") == implementation["specification_sha256"]
    assert sha(OUT / implementation["active_specification"]) == implementation["active_specification_sha256"]
    save("verification.json", {"status": "passed", "decimal_reconciliations": checks, "source_hashes_unchanged": True, "code_and_signal_hashes_unchanged": True, "market_data_downloads": 0, "orders": 0, "purchases": 0}, exclusive=True)
    print("Independent Decimal accounting and source preservation passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "prepare", "run", "verify"])
    args = parser.parse_args()
    {"freeze": freeze, "prepare": prepare, "run": run, "verify": verify}[args.action]()
