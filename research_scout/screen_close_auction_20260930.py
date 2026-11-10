"""Cost-aware predecision screen for a limit-on-close discount / seconds exit."""

from __future__ import annotations

import json
import math
import warnings
from datetime import UTC, datetime
from pathlib import Path

import databento as db
import exchange_calendars as xc
import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/close_auction_hft_20260930"
BASE = ROOT / "external_artifacts/databento_cash_etf_budget_v1"
AUCTION = BASE / "ARCX.PILLAR/imbalance/spy_imbalance_2021-01-01_2026-07-27.dbn.zst"
PREFIX = BASE / "EQUS.MINI/tbbo/cash_etf_tbbo_2023-03-28_2026-07-27.dbn.partial.dbn.zst"
TAIL = BASE / "EQUS.MINI/tbbo/cash_etf_tbbo_tail_2024-10-03_2026-07-27.dbn.zst"
BOUNDARY = pd.Timestamp("2024-10-03", tz="America/New_York").value
END = pd.Timestamp("2026-01-01", tz="America/New_York").value
AUCTION_FIELDS = ["auction_time", "ref_price", "ind_match_price", "paired_qty", "total_imbalance_qty",
                  "market_imbalance_qty", "side", "auction_type", "auction_status", "freeze_status"]
QUOTE_FIELDS = ["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00", "flags", "publisher_id"]


def screen(auction, quote, decision_ns, close_ns):
    result = {"eligible": False}
    for state, age, label in ((auction, 2000000000, "auction"), (quote, 250000000, "quote")):
        if (state is None or not 0 < decision_ns - state["receive_ns"] <= age
                or not 0 < decision_ns - state["event_ns"] <= age):
            return {**result, "reason": f"missing_stale_or_noncausal_{label}"}
    if (auction["auction_time_ns"] != close_ns or auction["auction_type"] != "C"
            or auction["auction_status"] not in (0, 1) or auction["freeze_status"] != 0):
        return {**result, "reason": "invalid_or_frozen_auction"}
    prices = [quote["bid_px_00"], quote["ask_px_00"], auction["ind_match_price"]]
    sizes = [quote["bid_sz_00"], quote["ask_sz_00"], auction["paired_qty"]]
    if (not np.isfinite(prices + sizes).all() or min(prices + sizes) <= 0 or max(prices) >= 1e7
            or quote["bid_px_00"] >= quote["ask_px_00"] or int(quote["flags"]) & (4 | 8)):
        return {**result, "reason": "invalid_market_state"}
    bid, ask, indicative = prices
    qty = math.floor(min(10000 / (ask * 1.01), .1 * quote["bid_sz_00"], .01 * auction["paired_qty"]))
    result.update(quantity=qty, bid=bid, ask=ask, indicative=indicative,
                  discount_bps=(bid / indicative - 1) * 10000)
    if qty <= 0 or qty * indicative < 100:
        return {**result, "reason": "insufficient_causal_size"}
    # Solve the fixed price cap algebraically; prospective sale at current bid
    # must cover both commissions, sell levies, adverse allowance and 2bp margin.
    commission = 2 * max(1., qty * .0075)
    raw_limit = (bid * (1 - .00003 - .0001) - .0002 - commission / qty) / (1 + .0001 + .0002)
    limit = math.floor(raw_limit * 100 + 1e-10) / 100
    gain = qty * (bid - indicative)
    fees = commission + qty * (bid * .00003 + .0002)
    adverse = qty * (bid + indicative) * .0001
    result.update(limit=limit, hypothetical_gain=gain, hypothetical_fees=fees,
                  hypothetical_adverse=adverse, hypothetical_net=gain - fees - adverse,
                  minimum_margin=qty * indicative * .0002)
    if auction["side"] != "A" or auction["total_imbalance_qty"] <= 0:
        return {**result, "reason": "no_sell_imbalance"}
    if indicative >= limit - 1e-8:
        return {**result, "reason": "discount_below_cost_and_margin_gate"}
    return {**result, "eligible": True, "reason": "eligible_for_execution_study"}


def extract(targets, kind):
    times = targets.decision_ns.to_numpy(np.int64)
    selected, counts = {}, {}
    sources = [AUCTION] if kind == "auction" else [PREFIX, TAIL]
    fields = AUCTION_FIELDS if kind == "auction" else QUOTE_FIELDS
    for path in sources:
        rows, previous, stopped = 0, -1, False
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter("always")
            for chunk in db.DBNStore.from_file(str(path)).to_df(count=200000):
                frame = chunk.reset_index()
                clock = frame.ts_recv.dt.as_unit("ns").astype("int64").to_numpy()
                if not len(clock):
                    continue
                assert not (np.diff(clock) < 0).any() and clock[0] >= previous
                previous = int(clock[-1])
                cutoff = BOUNDARY if path == PREFIX else END
                stopped = bool(clock[-1] >= cutoff)
                frame = frame.loc[clock < cutoff]
                if path == TAIL:
                    frame = frame.loc[frame.ts_recv.dt.as_unit("ns").astype("int64").ge(BOUNDARY)]
                rows += len(frame)
                frame = frame.loc[frame.symbol.astype(str).eq("SPY")]
                if kind == "quote":
                    # Keep the latest complete event even when the quote is invalid.
                    frame = frame.loc[frame["flags"].astype(int) & 128 != 0]
                if len(frame):
                    axis = frame.ts_recv.dt.as_unit("ns").astype("int64").to_numpy()
                    event = frame.ts_event.dt.as_unit("ns").astype("int64").to_numpy()
                    positions = np.searchsorted(axis, times, side="left") - 1
                    for i in np.flatnonzero(positions >= 0):
                        pos = positions[i]
                        row = frame.iloc[pos]
                        record = {k: row[k].item() if hasattr(row[k], "item") else row[k] for k in fields if k != "auction_time"}
                        record.update(date=targets.iloc[i]["date"], decision_ns=int(times[i]),
                                      receive_ns=int(axis[pos]), event_ns=int(event[pos]), source=str(path.relative_to(ROOT)))
                        if kind == "auction":
                            record["auction_time_ns"] = int(pd.Timestamp(row["auction_time"]).value)
                        selected[record["date"]] = record
                if rows // 4000000 != (rows - len(chunk)) // 4000000:
                    print(f"{kind} {path.name}: {rows:,} rows scanned", flush=True)
                if stopped:
                    break
        assert stopped, "Must reach the logical segment boundary without consuming truncated EOF"
        counts[str(path.relative_to(ROOT))] = {"rows_scanned_before_boundary": rows,
                                              "warnings": sorted({str(w.message) for w in notices}), "stopped_before_2026_or_partial_tail": stopped}
    rows = []
    for row in targets.to_dict("records"):
        rows.append(selected.get(row["date"], {"date": row["date"], "decision_ns": row["decision_ns"],
                                              "receive_ns": -1, "event_ns": -1}))
    output = pd.DataFrame(rows)
    for field in ("decision_ns", "receive_ns", "event_ns", "auction_time_ns"):
        if field in output:
            output[field] = pd.array([r.get(field) for r in rows], dtype="Int64")
    output.to_parquet(OUT / f"{kind}_inputs.parquet", index=False)
    return rows, counts


def main():
    OUT.mkdir(exist_ok=True)
    spec_path = OUT / "screen_specification.json"
    if spec_path.exists():
        raise FileExistsError("Closing-auction screen already frozen")
    validation = json.loads((BASE / "validation_report.json").read_text())
    known = {f["path"].replace("\\", "/"): f["sha256"] for f in validation["files"]}
    # The subsequently acquired canonical tail is recorded separately.
    tail_manifest = json.loads((BASE / "tail_download_manifest.json").read_text())
    known.update({f["path"].replace("\\", "/"): f["sha256"] for f in tail_manifest["requests"]})
    source_hashes = {}
    for path in (AUCTION, PREFIX, TAIL):
        name = path.relative_to(ROOT).as_posix()
        sha = digest(path)
        assert sha == known[name]
        source_hashes[name] = sha
    quality = json.loads((ROOT / "research_scout/new_data_technical_audit_v34.json").read_text())
    excluded = sorted(set(quality["degraded_dates"]["ARCX.PILLAR"]) | set(quality["degraded_dates"]["EQUS.MINI"]))
    schedule = xc.get_calendar("XNYS").schedule.loc["2023-03-28":"2025-12-31"]
    targets = pd.DataFrame([{"date": day.date().isoformat(), "close_ns": int(row["close"].value),
                             "decision_ns": int(row["close"].value - 65000000000)}
                            for day, row in schedule.iterrows()
                            if row["close"].tz_convert("America/New_York").hour == 16 and day.date().isoformat() not in excluded])
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "stage": "predecision economic-trigger supply only",
            "dates": targets.date.tolist(), "symbol": "SPY", "decision_et": "15:58:55", "excluded_degraded_dates": excluded,
            "hypothesis": "Buy a predeclared discount in the closing auction with a price-protected LOC, then exit15/30s after confirmed auction fill. Institutional benchmark demand can displace the auction from continuous trading; reversion is only a hypothesis.",
            "novelty_scope": "Related closing-auction research family. V41/V42 tested or proposed several-minute pre-close hedging from market-imbalance growth; this instead supplies price-limited auction liquidity and proposes a seconds-long post-uncross exit. It is not an independent discovery or repaired V41/V42. Old flat-at16:00/cadence constraints are not current user requirements.",
            "signal": "Last SPY raw capture strictly before decision. Quote capture AND event age<=250ms; auction ages<=2s, auction_type C, scheduled16:00, status0/1, freeze0. Positive non-crossed complete quote, no bad flags; positive matched quantity and indicative price; sell imbalance A with positive total quantity. Retain invalid latest states, never search backward for a favorable valid quote.",
            "quantity": "Integer shares <=$10000/(ask*1.01), <=10% predecision bid size, <=1% predecision matched quantity, notional>=$100. No borrowing or fractional shares. Future fills never resize quantity.",
            "costs": "$.0075/share minimum$1/side; sale .30bp plus$.0002/share;1bp adverse allowance EACH side. Algebraic cent-rounded LOC cap must leave2bp of entry notional after all costs if sold at the predecision bid. Indicative price must be strictly below cap. Hypothetical current-bid proceeds are a signal, never a fill or profit.",
            "order_scope": "If this gate has events, freeze exact execution protocol before reading post-decision prices.250ms processing plus1s outbound base,3s stress arrives before15:59 freeze. No cancellation after entry.15/30s holds begin after auction-fill ACK; no overnight or multi-minute position. Historical rule admission, official auction price/quantity, priority and after-hours execution still require verification.",
            "limitations": "EQUS.MINI is anonymized trade-conditioned aggregate BBO, not SIP NBBO or a venue-specific executable exit. Quote sizes are source shares. All2023-25 history is exposed discovery. Calendar quality exclusions create a conditional sample. Future auction or exit prices not used in this screen; no profitability claim or p-value.",
            "data": "Already-local native Databento ARCX.PILLAR imbalance and EQUS.MINI TBBO. Canonical prefix through2024-10-02, tail from2024-10-03. Do not consume truncated EOF or select2026 observations. No paid API.",
            "source_sha256": source_hashes, "tail_download_manifest_sha256": digest(BASE / "tail_download_manifest.json"),
            "tail_manifest_present": bool(tail_manifest), "quality_sha256": digest(ROOT / "research_scout/new_data_technical_audit_v34.json"),
            "code_sha256": digest(Path(__file__)),
            "sources": ["https://www.nyse.com/trade/auctions", "https://www.nyse.com/publicdocs/nyse/markets/nyse-arca/rule-filings/filings/2025/SR-NYSEARCA-2025-67.pdf",
                        "https://databento.com/docs/schemas-and-data-formats/tbbo", "https://databento.com/docs/schemas-and-data-formats/imbalance"]}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    targets.to_parquet(OUT / "calendar.parquet", index=False)
    print(f"Frozen predecision closing-auction cost gate: {len(targets)} full-close dates", flush=True)
    auctions, auction_audit = extract(targets, "auction")
    quotes, quote_audit = extract(targets, "quote")
    rows = [{**t, **screen(a, q, t["decision_ns"], t["close_ns"])}
            for t, a, q in zip(targets.to_dict("records"), auctions, quotes, strict=True)]
    frame = pd.DataFrame(rows)
    frame.to_parquet(OUT / "screen.parquet", index=False)
    assert digest(Path(__file__)) == spec["code_sha256"]
    result = {"dates": len(frame), "eligible_dates": int(frame.eligible.sum()), "outcomes": frame.reason.value_counts().to_dict(),
              "by_year": {year: {"dates": len(g), "eligible_dates": int(g.eligible.sum())} for year, g in frame.groupby(frame.date.str[:4])},
              "eligible": frame.loc[frame.eligible].to_dict("records"), "auction_audit": auction_audit, "quote_audit": quote_audit,
              "source_panel_sha256": {name: digest(OUT / name) for name in ("calendar.parquet", "auction_inputs.parquet", "quote_inputs.parquet", "screen.parquet")},
              "profitability_tested": False, "reliable_edge_established": False}
    (OUT / "screen_results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("dates", "eligible_dates", "outcomes", "by_year")}), flush=True)


if __name__ == "__main__":
    main()
