"""Frozen, chronological earnings-answer experiment: source collection and timing.

All new artifacts live in a new directory. No trading or paid inference endpoints.
Run with python -m research_scout.v98_earnings_answers_20260907 <stage>.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import exchange_calendars as xc
import pandas as pd
import requests

from research_scout.v98_transcript_roles_20260907 import extract_page

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/v98_earnings_answers_20260907"
PILOT = ROOT / "research_scout/edge_discovery_20260907"
NY = "America/New_York"
ALIASES = {"FB": "META", "GOOG": "GOOGL"}
PUBLIC_LOCAL = threading.local()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(name: str, value) -> None:
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(target)


def read(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def calendar():
    return xc.get_calendar("XNYS", start="2017-12-01", end="2024-01-15")


def freeze():
    OUT.mkdir(exist_ok=True)
    if (OUT / "specification.json").exists():
        print("Existing immutable specification retained", flush=True)
        return
    old = ROOT / "research_scout/new_information_tests_20260907/specification.json"
    universe = json.loads(old.read_text(encoding="utf-8"))["common"]["universe"]
    originals = [
        old,
        ROOT / "data/parquet/equity/yahoo_chart/SPY_1d.parquet",
        ROOT / "research/intraday_contract.py",
        ROOT / "research_scout/audit_transcript_pilot_20260907.py",
        *[p for p in PILOT.rglob("*") if p.is_file()],
    ]
    spec = {
        "experiment": "V98",
        "created_utc": datetime.now(UTC).isoformat(),
        "status": "Rules frozen before new stock outcomes or fitted forecasts",
        "mechanism": "Management answers may contain information not yet incorporated by 10:00 on the first full session after transcript availability. Test whether answers add same-day predictive value beyond prepared remarks, company identity, opening gap, and the first half-hour stock and SPY price response.",
        "objective": "Fully funded, long-only individual stocks; flat each day; exceed SPY adjusted buy-and-hold return after costs across every 2021-2023 session.",
        "universe": universe,
        "membership": "Fixed pre-existing 132-stock SEC/SIP intersection. Retrospective survivor universe, not historical index membership. Historical ticker aliases only FB->META and GOOG->GOOGL (same issuer, trade GOOGL class); all other source symbols must match directly. No merger predecessor inference.",
        "aliases": ALIASES,
        "source": "Motley Fool monthly public sitemaps January 2018-December 2023. At most 5000 matching transcript URLs, two concurrent requests, at least 0.35 seconds per worker after each request. Existing source copies reused byte-for-byte. At most two attempts per URL per collection run, with finite timeouts; record all failures. No replacement data vendor or paid service.",
        "source_eligibility": "Require unique prepared, Q&A and participant headings, resolved speaker roles, at least 500 management words in each section, timezone-aware publication/modification metadata, matching headline ticker. Exclude analyst/operator text, current-price introductions, recommendations, disclosures and ads. Original-version uncertainty remains: exclude revisions changing the first eligible session; current metadata alone does not prove historical text vintage. Exclusions are retrospective and the economic screen is corpus-conditional, not an unbiased point-in-time backtest.",
        "duplicates": "One transcript per canonical issuer per publication-derived entry session. If multiple different URLs survive, exclude that issuer-session as ambiguous; identical URL only once.",
        "availability": "First full XNYS session whose 09:30 open is strictly later than max(publication, modification)+30 minutes. Publication and current-version clocks must map to the same session. Early-close dates skipped by text eligibility; portfolio remains cash on early-close dates. Features observe only 09:30-09:55 five-minute bars, all completed by 10:00. One minute processing gives 10:01 signal availability.",
        "price_data": "Historical Alpaca SIP 5Min bars, split adjustment, asof=2023-12-29, only required event sessions and preceding exchange sessions, plus SPY on event sessions. All pagination retained with raw response hashes. No latest/live endpoints. Missing required signal/fill data block that evaluation day's full equity; never treated as a neutral score or a zero return.",
        "training": ["2018-01-01", "2020-12-31"],
        "evaluation": ["2021-01-04", "2023-12-29"],
        "refit": "Expanding, monthly. Fit only events whose exit precedes the month's first calendar instant in New York. All preprocessing, vocabulary, IDF, scaling and coefficients fitted on the training partition only. Minimum 300 training events across at least 30 issuers, else missing. No random split, CV, threshold, alpha or vocabulary search.",
        "models": {
            "baseline": "Prepared management remarks TF-IDF, ticker one-hot, standardized log(open/previous-session-close), log(09:55 close/09:30 open) for stock and SPY.",
            "augmented": "Identical baseline feature definition plus a separate management Q&A TF-IDF block. Fit target directly with the same Ridge settings.",
            "tfidf": {
                "ngram_range": [1, 2],
                "min_df": 5,
                "max_features": 1500,
                "sublinear_tf": True,
                "norm": "l2",
                "lowercase": True,
                "token_pattern": "(?u)\\b[a-zA-Z][a-zA-Z]+\\b",
            },
            "ridge": {
                "alpha": 10.0,
                "fit_intercept": True,
                "solver": "lsqr",
                "tol": 1e-6,
                "max_iter": 2000,
            },
            "numeric_features": ["stock_gap", "stock_first30", "spy_first30"],
            "target": "log(stock 15:55 bar open / stock 10:05 bar open)",
        },
        "trade": "Buy all eligible stocks equally at 10:05 bar open if augmented predicted log return exceeds log(1.0005/0.9995) and augmented prediction is strictly greater than baseline prediction. Sell at 15:55 bar open; fractional shares, one simultaneous basket, no borrowing, idle cash earns zero. No parameter adjustments or inverted rule after observing results.",
        "costs": {
            "all_in_bps_each_side": 5.0,
            "additional_fees": 0.0,
            "stress_bps_each_side": 10.0,
            "price_basis": "bar_reference",
        },
        "benchmark": "SPY legacy adjusted OHLC proxy from existing Yahoo cache, first 2021 session adjusted open through final 2023 session adjusted close. Full XNYS calendar, including all strategy cash days. No 2024+ candidate outcomes.",
        "controls": [
            "Prepared-plus-price baseline model with its prediction above the same cost hurdle, same sizing and clocks",
            "Equal-weight all eligible transcript events, same sizing and clocks",
            "Paired event forecast errors and within-calendar same-day performance; diagnostic, not independent hypotheses",
        ],
        "gates": "Distinct data-readiness, signal-stability, economics, incremental-value, robustness and confirmation fields. Even a positive return cannot pass historical-vintage or survivor-universe limitations. Require net full-calendar ending equity > SPY and incremental value over controls before expensive quote-based replay or confirmation.",
        "abort": "A complete conditional economic failure against SPY ends this candidate without alternative parameters, reversal, different clock, or 2024+ outcome inspection. Compute already-fitted paired controls only for attribution. Missing data or a model implementation defect gets a bounded diagnostic; it is not itself a realized loss.",
        "exposed_history": "2021-2025 prices used in prior repository experiments; this is a new signal but 2021-2023 is exposed development history, not fresh independent confirmation. Two MSFT 2023 transcripts and Q1 2021 source pilot inspected before this specification without candidate returns.",
        "confirmation": "No genuinely untouched historical price period certified. Do not use 2024+ on failure. A promising screen would require a separate future/live paper observation protocol and reliable original text vintages before any deployment.",
        "variants": [
            "V98 primary rule",
            "V98 baseline diagnostic control",
            "V98 all-event diagnostic control",
        ],
        "permissions": "Existing files and free public downloads only. No orders, subscription changes, paid data or external model inference.",
        "original_file_hashes": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in originals},
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as handle:
        json.dump(spec, handle, indent=2)
    print(f"Frozen V98; {len(universe)} issuers; no candidate returns inspected", flush=True)


def reuse_sources():
    entries = []
    for item in json.loads((PILOT / "source_probe_retrieval.json").read_text(encoding="utf-8")):
        if item.get("status") == 200 and item["url"].startswith("https://www.fool.com/"):
            entries.append((item["url"], ROOT / item["path"], False))
    manifest = json.loads((PILOT / "pilot_manifest.json").read_text(encoding="utf-8"))
    for item in manifest:
        path = PILOT / "pilot_raw" / f"{item['symbol']}.gz"
        if item.get("url") and path.exists():
            entries.append((item["url"], path, True))
    for month in ["02", "03"]:
        path = PILOT / "pilot_raw" / f"sitemap_2021{month}.gz"
        if path.exists():
            entries.append((f"https://www.fool.com/sitemap/2021/{month}", path, True))
    return {url: (path, compressed) for url, path, compressed in entries}


def source_fetch(url: str, category: str, reused: dict):
    if urlparse(url).hostname != "www.fool.com":
        raise ValueError("Unexpected public source host")
    key = sha(url.encode())[:24]
    dest = OUT / "raw" / category / f"{key}.html.gz"
    meta_path = dest.with_suffix(".json")
    if dest.exists() and meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    record = {
        "url": url,
        "key": key,
        "category": category,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
    raw = None
    if url in reused:
        path, compressed = reused[url]
        raw = gzip.decompress(path.read_bytes()) if compressed else path.read_bytes()
        record.update(status=200, reused_from=str(path.relative_to(ROOT)))
    else:
        if not hasattr(PUBLIC_LOCAL, "session"):
            PUBLIC_LOCAL.session = requests.Session()
            PUBLIC_LOCAL.session.headers.update({"User-Agent": "mfs-trader public research/1.0"})
        for attempt in range(2):
            try:
                with PUBLIC_LOCAL.session.get(url, timeout=(8, 18)) as response:
                    record.update(
                        status=response.status_code, final_url=response.url, attempt=attempt + 1
                    )
                    if urlparse(response.url).hostname != "www.fool.com":
                        raise ValueError("Unexpected redirect host")
                    if response.status_code == 200:
                        raw = response.content
                        if len(raw) > 5_000_000:
                            raise ValueError("Public document exceeds 5 MB bound")
                        break
                    if response.status_code not in {429, 500, 502, 503, 504}:
                        break
            except (requests.RequestException, ValueError) as exc:
                record["error_type"] = type(exc).__name__
            finally:
                time.sleep(0.35)
    if raw is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(gzip.compress(raw, mtime=0))
        record.update(path=str(dest.relative_to(ROOT)), bytes=len(raw), sha256=sha(raw))
        meta_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def collect_maps():
    spec = read("specification.json")
    reused = reuse_sources()
    urls = [
        f"https://www.fool.com/sitemap/{y}/{m:02d}" for y in range(2018, 2024) for m in range(1, 13)
    ]
    records = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(source_fetch, url, "sitemaps", reused) for url in urls]
        for future in as_completed(pending):
            records.append(future.result())
            if len(records) % 12 == 0:
                print(f"Sitemaps {len(records)}/{len(urls)}", flush=True)
    records.sort(key=lambda r: r["url"])
    save("sitemap_retrieval.json", records)
    if any(r.get("status") != 200 or not r.get("path") for r in records):
        raise ValueError(
            "Incomplete sitemap collection; inspect retrieval manifest before proceeding"
        )
    symbols = set(spec["universe"]) | set(ALIASES)
    found = {}
    for r in records:
        raw = gzip.decompress((ROOT / r["path"]).read_bytes())
        for node in ET.fromstring(raw).iter():
            url = node.text or ""
            # Older slugs say "earnings-conference-call" or are truncated. The
            # publisher's transcript path identifies the source independently
            # of its display title and the company's subsequent performance.
            if not node.tag.endswith("loc") or "/earnings/call-transcripts/" not in url:
                continue
            if not re.search(r"/(201[89]|202[0-3])/", url):
                continue
            tokens = set(
                urlparse(url).path.split("/")[-2 if url.endswith("/") else -1].upper().split("-")
            )
            matches = sorted(tokens & symbols)
            if matches:
                found[url] = {"url": url, "source_ticker_candidates": matches}
    if len(found) > 5000:
        raise ValueError("Frozen source document bound exceeded")
    manifest = [found[url] for url in sorted(found)]
    save("source_manifest.json", manifest)
    print(f"Matching transcript URLs: {len(manifest)}", flush=True)


def collect_texts():
    manifest = read("source_manifest.json")
    reused = reuse_sources()
    records = []
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(source_fetch, r["url"], "transcripts", reused) for r in manifest]
        for future in as_completed(pending):
            records.append(future.result())
            if len(records) % 50 == 0:
                save("transcript_retrieval_progress.json", records)
                print(
                    f"Transcripts {len(records)}/{len(manifest)}; usable responses {sum('path' in r for r in records)}; elapsed {time.monotonic() - start:.0f}s",
                    flush=True,
                )
    records.sort(key=lambda r: r["url"])
    save("transcript_retrieval.json", records)
    print(
        f"Collection complete: {len(records)} attempted; {sum('path' in r for r in records)} saved",
        flush=True,
    )


def first_session(value, full_opens):
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("Naive publication clock")
    index = full_opens.searchsorted(timestamp + pd.Timedelta(minutes=30), side="right")
    return (
        full_opens[index].tz_convert(NY).strftime("%Y-%m-%d") if index < len(full_opens) else None
    )


def parse_sources():
    records = read("transcript_retrieval.json")
    manifest = {r["url"]: r for r in read("source_manifest.json")}
    schedule = calendar().schedule
    full_opens = pd.DatetimeIndex(
        schedule.loc[schedule.close.dt.tz_convert(NY).dt.strftime("%H:%M") == "16:00", "open"]
    )
    audit, events = [], []
    for i, r in enumerate(records):
        row = {"url": r["url"], "key": r["key"], "problems": []}
        if "path" not in r:
            row["problems"].append("source_retrieval_failed")
            audit.append(row)
            continue
        raw = gzip.decompress((ROOT / r["path"]).read_bytes())
        if sha(raw) != r["sha256"]:
            raise ValueError("Raw source hash mismatch")
        parsed = extract_page(raw.decode("utf-8"))
        row["problems"].extend(parsed["problems"])
        matches = [
            s
            for s in manifest[r["url"]]["source_ticker_candidates"]
            if f"({s})" in (parsed["headline"] or "")
        ]
        canonical = sorted({ALIASES.get(s, s) for s in matches})
        if len(canonical) != 1:
            row["problems"].append("headline_ticker_ambiguous_or_unmatched")
        row.update(
            symbol=canonical[0] if len(canonical) == 1 else None,
            headline=parsed["headline"],
            published=parsed["published"],
            modified=parsed["modified"],
            word_counts=parsed["management_word_counts"],
            unknown_speakers=parsed["unknown_speakers"],
        )
        if parsed["conservative_page_available_at"]:
            pub_day = first_session(parsed["published"], full_opens)
            day = first_session(parsed["conservative_page_available_at"], full_opens)
            row.update(
                day=day,
                publication_day=pub_day,
                available_at=parsed["conservative_page_available_at"],
            )
            if pub_day != day:
                row["problems"].append("revision_changes_entry_session")
            if day is None or not "2018-01-01" <= day <= "2023-12-29":
                row["problems"].append("entry_outside_frozen_period")
        else:
            row["problems"].append("availability_unresolved")
        # Persist parsed source independently of eventual admission or outcomes.
        save(f"parsed/{r['key']}.json", parsed)
        if not row["problems"]:
            events.append(
                {
                    **row,
                    "prepared_text": "\n".join(
                        p["text"] for p in parsed["management_sections"]["prepared"]
                    ),
                    "qa_text": "\n".join(p["text"] for p in parsed["management_sections"]["qa"]),
                }
            )
        audit.append(row)
        if (i + 1) % 250 == 0:
            print(f"Parsed {i + 1}/{len(records)}", flush=True)
    counts = Counter((r["symbol"], r["day"]) for r in events)
    ambiguous = {key for key, n in counts.items() if n > 1}
    for row in audit:
        if not row["problems"] and (row["symbol"], row["day"]) in ambiguous:
            row["problems"].append("ambiguous_multiple_issuer_session_documents")
    events = sorted(
        [r for r in events if (r["symbol"], r["day"]) not in ambiguous],
        key=lambda r: (r["day"], r["symbol"]),
    )
    save("source_audit.json", audit)
    save("eligible_events.json", events)
    summary = {
        "documents": len(records),
        "eligible_events": len(events),
        "eligible_symbols": len({r["symbol"] for r in events}),
        "eligible_by_year": dict(sorted(Counter(r["day"][:4] for r in events).items())),
        "problem_counts": dict(Counter(p for r in audit for p in r["problems"])),
        "conditional_historical_vintage": True,
        "no_price_outcomes_read": True,
    }
    save("source_summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["freeze", "maps", "texts", "parse"])
    args = parser.parse_args()
    {"freeze": freeze, "maps": collect_maps, "texts": collect_texts, "parse": parse_sources}[
        args.stage
    ]()
