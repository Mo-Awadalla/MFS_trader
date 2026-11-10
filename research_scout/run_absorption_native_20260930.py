"""Preserve absorption hypotheses; correct all execution states to native T."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from itertools import groupby

import pandas as pd

from research.absorption_hft import SCENARIOS
from research.crypto_symbol_cache import digest
from research.native_depth_execution import TargetBook, replay
from research_scout.audit_force_order_full_20260930 import ASSETS
from research_scout.fetch_absorption_native_20260930 import OUT
from research_scout.run_absorption_hft_20260930 import DATES, ROOT
from research_scout.run_absorption_hft_20260930 import OUT as STUDY


def stream(files, day, symbol):
    start = pd.Timestamp(day, tz="UTC").value // 1000
    last_end, last_capture = None, -1
    for file in sorted(files, key=lambda f: f["minute"]):
        if last_end is not None and last_end != file["minute"]:
            yield {"disconnect": True, "reason": "unrequested_context_gap"}
        last_end = file["minute"] + file["slice_minutes"]
        path = ROOT / file["path"]
        assert digest(path) == file["compressed_sha256"]
        payload = gzip.decompress(path.read_bytes())
        assert len(payload) == file["decoded_bytes"]
        assert hashlib.sha256(payload).hexdigest() == file["decoded_sha256"]
        for line_number, line in enumerate(payload.splitlines()):
            if not line.strip():
                yield {"disconnect": True, "file": file["path"], "line": line_number}
                continue
            stamp, encoded = line.split(b" ", 1)
            time = datetime.fromisoformat(stamp.decode().replace("Z", "+00:00"))
            assert time.date().isoformat() == day and time.utcoffset().total_seconds() == 0
            capture = ((time.hour * 3600 + time.minute * 60 + time.second) * 1000000 + time.microsecond)
            assert capture >= last_capture
            last_capture = capture
            wrapper = json.loads(encoded)
            raw = wrapper.get("data", wrapper)
            assert raw.get("e") == "depthUpdate" and raw.get("s") == symbol
            yield {"disconnect": False, "local_us": capture, "E_us": int(raw["E"]) * 1000 - start,
                   "T_us": int(raw["T"]) * 1000 - start, "U": int(raw["U"]), "u": int(raw["u"]),
                   "pu": int(raw["pu"]), "b": raw["b"], "a": raw["a"], "file": file["path"], "line": line_number}


def reconstruct(quotes, files, day, symbol):
    selected = quotes.loc[quotes.clock_kind.eq("exchange")].drop_duplicates("target_us")
    pending = defaultdict(list)
    for quote in selected.to_dict("records"):
        pending[int(quote["quote_local_us"])].append(quote)
    active, done = [], {}
    messages = 0
    for capture, raw_group in groupby(stream(files, day, symbol), lambda r: r.get("local_us", -1)):
        group = list(raw_group)
        messages += sum(not r["disconnect"] for r in group)
        expected = pending.pop(capture, [])
        counts = Counter(r["E_us"] for r in group if not r["disconnect"])
        for quote in expected:
            if counts[int(quote["quote_exchange_us"])] != 1:
                done[int(quote["target_us"])] = {"target_us": int(quote["target_us"]), "complete": False,
                                                "reason": "ambiguous_or_missing_source_capture"}
        for raw in group:
            for target in active:
                target.advance(raw)
                if "complete" in target.result:
                    done[target.target] = target.result
            active = [t for t in active if "complete" not in t.result]
            for quote in expected:
                if (int(quote["target_us"]) not in done and not raw["disconnect"]
                        and raw["E_us"] == quote["quote_exchange_us"]):
                    target = TargetBook(quote, raw, ASSETS[symbol]["tick_size"])
                    if "complete" in target.result:
                        done[target.target] = target.result
                    else:
                        active.append(target)
    for target in active:
        target.fail("no_successor_in_acquired_context")
        done[target.target] = target.result
    for quotes_missing in pending.values():
        for q in quotes_missing:
            done[int(q["target_us"])] = {"target_us": int(q["target_us"]), "complete": False, "reason": "missing_source_capture"}
    assert set(done) == set(selected.target_us)
    return done, messages


def process_day(symbol, day, files):
    folder = OUT / symbol
    quotes = pd.read_parquet(STUDY / symbol / "panels" / f"{day}_quotes.parquet")
    events = pd.read_parquet(STUDY / symbol / "panels" / f"{day}_events.parquet")
    states, messages = reconstruct(quotes, files, day, symbol)
    path = folder / f"{day}_states.json.gz"
    path.write_bytes(gzip.compress(json.dumps(states, separators=(",", ":")).encode(), compresslevel=3, mtime=0))
    records = {}
    for mechanism in ("hold_fade", "break_follow"):
        for hold in (15, 30):
            name = f"{mechanism}_{hold}s"
            records[name] = {name: replay(events, quotes, states, mechanism, hold, scenario,
                                         ASSETS[symbol]["tick_size"], ASSETS[symbol]["quantity_step"])
                             for name, scenario in SCENARIOS.items()}
    audit = {"symbol": symbol, "date": day, "raw_messages": messages, "targets": len(states),
             "state_reasons": dict(Counter(s["reason"] for s in states.values())),
             "targets_with_timestamp_ties": sum(s.get("timestamp_ties", 0) > 0 for s in states.values()),
             "states_path": str(path.relative_to(ROOT)), "states_sha256": digest(path),
             "events_sha256": digest(STUDY / symbol / "panels" / f"{day}_events.parquet"),
             "quotes_sha256": digest(STUDY / symbol / "panels" / f"{day}_quotes.parquet")}
    return symbol, day, records, audit


def summarize(frame, days):
    daily = []
    for day in days:
        group = frame.loc[frame.date.eq(day)]
        complete = bool(group.complete.all())
        lo, hi = float(group.pnl_lower.sum()), float(group.pnl_upper.sum())
        daily.append({"date": day, "complete": complete, "closed_lower": lo, "closed_upper": hi,
                      "net_lower": lo if complete else None, "net_upper": hi if complete else None,
                      "mandatory_trades": int((group.status.eq("bounded") & ~group.entry_optional.fillna(False)).sum()),
                      "possible_trades": int(group.status.eq("bounded").sum())})
    complete = all(d["complete"] for d in daily)
    lo, hi = sum(d["closed_lower"] for d in daily), sum(d["closed_upper"] for d in daily)
    return {"complete": complete, "net_lower": lo if complete else None, "net_upper": hi if complete else None,
            "closed_lower": lo, "closed_upper": hi, "mandatory_trades": sum(d["mandatory_trades"] for d in daily),
            "possible_trades": sum(d["possible_trades"] for d in daily),
            "positive_dates": sum(d["net_lower"] > 0 for d in daily) if complete else None,
            "without_best_date": lo - max(d["closed_lower"] for d in daily) if complete else None,
            "outcomes": frame.status.value_counts().to_dict(), "daily": daily}


def main():
    spec_path = OUT / "replay_specification.json"
    if spec_path.exists():
        raise FileExistsError("Native replay already frozen; do not overwrite outcomes")
    manifest = json.loads((OUT / "manifest.json").read_text())
    assert manifest["complete"]
    original = json.loads((STUDY / "specification.json").read_text())
    for path, sha in original["code_sha256"].items():
        assert digest(ROOT / path) == sha
    acquisition = json.loads((OUT / "acquisition_specification.json").read_text())
    for path, sha in acquisition["quote_panel_sha256"].items():
        assert digest(ROOT / path) == sha
    code = ["research/native_depth_execution.py", "research_scout/run_absorption_native_20260930.py"]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "new_hypotheses": 0, "corrected_implementation_versions": 8,
            "session_configurations": 116, "session_implementation_versions": 164,
            "original_specification_sha256": digest(STUDY / "specification.json"),
            "acquisition_specification_sha256": digest(OUT / "acquisition_specification.json"),
            "raw_manifest_sha256": digest(OUT / "manifest.json"),
            "invariants": "Original signals, dates, target times, causal sizing, FOK collars, fees, adverse allowance, fixed ACK holds, no-overlap cooldown and progression gates unchanged. No fresh outcomes or optimized parameters.",
            "clock": "Match normalized snapshot to exactly one raw capture/E pair; initial T must precede target. Validate initial delta quantities inside known top-five coverage. Replay native T through target, including updates published at E after target. Stop at first sequenced T>target. Require pu/u continuity, nondecreasing T and no disconnect/context gaps. No arbitrary standing-quote expiry.",
            "depth": "Initial five levels define contiguous known price coverage, including empty prices between levels. Absolute deltas may remove levels or add better levels. Initial deeper liquidity remains unknown. No arrival-time resizing. A FOK rejection requires a known worse price or known coverage spanning the complete collar; otherwise insufficient depth is unknown.",
            "ties": "All pre/post-update states at T==order time retained. Mixed fill/rejection includes zero cashflow. Filled entry/exit extrema form conservative conditional cash intervals; no favorable branch selected. Any unpriceable branch retains possible/known inventory and halts the date. Capital interval crossing the fixed eligibility threshold also halts.",
            "limitations": "Conditional historical feed-state model. Batched depth updates do not identify every intervening matching-engine state, live order priority or market impact. Bounds apply to observed timestamp-tie branches, not to every possible physical execution. All six dates already exposed discovery. A positive result would require fresh dates and measured forward execution.",
            "code_sha256": {p: digest(ROOT / p) for p in code}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    for symbol in ASSETS:
        (OUT / symbol).mkdir(exist_ok=True)
    batches, audits = {}, []
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(process_day, symbol, day, [f for f in manifest["files"] if f["symbol"] == symbol and f["date"] == day])
                for symbol in ASSETS for day in DATES]
        for job in as_completed(jobs):
            symbol, day, records, audit = job.result()
            batches[symbol, day] = records
            audits.append(audit)
            print(json.dumps({k: v for k, v in audit.items() if "sha256" not in k and k != "states_path"}), flush=True)
    results, advance = {}, []
    for symbol in ASSETS:
        results[symbol] = {}
        for mechanism in ("hold_fade", "break_follow"):
            for hold in (15, 30):
                name, scenarios = f"{mechanism}_{hold}s", {}
                for scenario in SCENARIOS:
                    rows = [dict(row, date=day, symbol=symbol) for day in DATES for row in batches[symbol, day][name][scenario]]
                    frame = pd.DataFrame(rows)
                    frame.to_parquet(OUT / symbol / f"{name}_{scenario}_attempts.parquet", index=False)
                    scenarios[scenario] = {"all": summarize(frame, DATES),
                        "development": summarize(frame.loc[frame.date.isin(DATES[:3])], DATES[:3]),
                        "selection": summarize(frame.loc[frame.date.isin(DATES[3:])], DATES[3:])}
                passed = True
                for period in ("development", "selection"):
                    base = scenarios["base"][period]
                    passed &= (all(s[period]["complete"] and s[period]["net_lower"] > 0 for s in scenarios.values())
                               and base["mandatory_trades"] >= 50 and base["positive_dates"] >= 2 and base["without_best_date"] > 0)
                if passed:
                    advance.append(f"{symbol}/{name}")
                results[symbol][name] = {"scenarios": scenarios, "needs_additional_evidence": bool(passed)}
                print(f"{symbol} {name}: {json.dumps(scenarios['base']['all'])}; advance={passed}", flush=True)
    assert all(digest(ROOT / p) == sha for p, sha in spec["code_sha256"].items())
    (OUT / "results.json").write_text(json.dumps({"results": results, "source_audits": audits,
        "candidates_for_additional_evidence": advance, "reliable_edge_established": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
