"""Record the guidance feasibility stop without loading any price data."""

import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/new_information_tests_20260907"


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inventory = {}
    for file in sorted(OUT.glob("*_sources_retrieval.json")):
        for row in json.loads(file.read_text(encoding="utf-8")):
            if "path" in row and "error" not in row:
                path = ROOT / row["path"]
                assert sha(path) == row["sha256"]
                inventory[(row["symbol"], row["date"])] = {
                    k: row[k] for k in ["symbol", "date", "url", "path", "sha256", "retrieved_utc"]
                }
                inventory[(row["symbol"], row["date"])]["bytes"] = path.stat().st_size
    save(
        "public_document_inventory.json",
        sorted(inventory.values(), key=lambda r: (r["symbol"], r["date"])),
    )
    metadata = pd.read_parquet(ROOT / "data/parquet/sec_filings/sec_filing_events.parquet")
    metadata = metadata[metadata.symbol.isin(["ABBV", "AMGN", "CVS", "LLY", "UNH"])]
    data = [
        ("ABBV", "2021-02-03", "12.32", "12.52", None),
        ("ABBV", "2021-04-30", "12.37", "12.57", "2021-02-03"),
        ("AMGN", "2021-02-02", "16.00", "17.00", None),
        ("AMGN", "2021-04-27", "16.00", "17.00", "2021-02-02"),
        ("CVS", "2021-02-16", "7.39", "7.55", None),
        ("CVS", "2021-05-04", "7.56", "7.68", "2021-02-16"),
        ("LLY", "2021-01-29", "7.75", "8.40", "2020-12-15"),
        ("LLY", "2021-04-27", "7.80", "8.00", "2021-01-29"),
        ("UNH", "2021-01-20", "17.75", "18.25", "2020-12-01"),
        ("UNH", "2021-04-15", "18.10", "18.60", "2021-01-20"),
    ]
    pilot = []
    for symbol, day, low, high, previous in data:
        source = inventory[(symbol, day)]
        text = re.sub(
            r"\s+", " ", (ROOT / source["path"]).with_suffix(".txt").read_text(encoding="utf-8")
        )
        match = re.search(
            r"\$?\s*" + re.escape(low) + r"\s*(?:to|[-–—])\s*\$?\s*" + re.escape(high), text
        )
        assert match, (symbol, day, low, high)
        events = metadata[
            (metadata.symbol == symbol)
            & (metadata.filing_date.dt.strftime("%Y-%m-%d") == day)
            & metadata["items"].str.contains("2.02", regex=False)
        ]
        assert len(events) == 1
        event = events.iloc[0]
        pilot.append(
            {
                "symbol": symbol,
                "publication_date": day,
                "fiscal_year": 2021,
                "currency": "USD",
                "units": "per diluted share",
                "basis": "issuer adjusted/non-GAAP annual EPS as defined in the original release",
                "low": low,
                "high": high,
                "source": source,
                "accession": event.accession_number,
                "conservative_filing_availability": event.acceptance_datetime.isoformat(),
                "observed_previous_range_source": inventory[(symbol, previous)]
                if previous
                else None,
                "source_excerpt": text[max(0, match.start() - 160) : match.end() + 190],
                "numeric_source_checked": True,
                "complete_intervening_history_certified": False,
            }
        )
    save(
        "V97_pilot_extraction.json",
        {
            "records": pilot,
            "readable_documents": len(pilot),
            "range_facts_are_not_a_frozen_trade_list": True,
            "strategy_outcomes_evaluated": False,
            "CVS_original_pdf_guidance_page_visually_checked": True,
        },
    )
    scope = json.loads((OUT / "V97_metadata_scope.json").read_text())
    pages = []
    for batch in json.loads((OUT / "sec_primary_web_archive.json").read_text(encoding="utf-8")):
        for page in re.split(r"\n-{30,}\n", batch["result"]):
            match = re.search(r'Source: open\(\{"ref_id":"([^"]+)"', page)
            count = re.search(r"Total lines: (\d+)", page)
            if not match or not count:
                continue
            url = match[1]
            acc = url.split("/")[-2]
            record = next(r for r in scope if r["accession_number"].replace("-", "") == acc)
            pages.append(
                {
                    "symbol": record["symbol"],
                    "date": record["filing_date"][:10],
                    "accession": record["accession_number"],
                    "items": record["items"],
                    "url": url,
                    "primary_content_returned": int(count[1]) > 1,
                    "returned_total_lines": int(count[1]),
                }
            )
    gaps = {
        ("UNH", "2021-03-08"),
        ("UNH", "2021-05-07"),
        ("CVS", "2022-06-09"),
        ("CVS", "2022-09-13"),
        ("UNH", "2022-05-06"),
        ("UNH", "2022-09-09"),
        ("UNH", "2023-05-05"),
        ("UNH", "2023-05-30"),
        ("CVS", "2023-05-31"),
        ("CVS", "2023-09-11"),
    }
    unresolved = [r for r in pages if (r["symbol"], r["date"]) in gaps]
    assert len(unresolved) == len(gaps) and all(
        not r["primary_content_returned"] for r in unresolved
    )
    available = sum(r["primary_content_returned"] for r in pages)
    coverage = {
        "cached_8K_metadata_records_in_expanded_scope": len(scope),
        "item_2_02_or_7_01_primary_pages_attempted": len(pages),
        "primary_content_returned": available,
        "primary_content_not_returned": len(pages) - available,
        "count_caveat": "Several unavailable earnings-primary pages were covered by issuer releases or indexed exhibits. The 52 unavailable primary pages are not 52 missing guidance events. These retrieval counts do not certify completeness of all public guidance channels.",
        "representative_unresolved_disclosures": unresolved,
        "attempt_log": "Issuer HTML/PDF archives, indexed SEC filing/exhibit pages, targeted issuer/SEC search and two indexed complete-submission alternatives; direct transparent SEC HTTP request returned 403 and was not retried with disguises. No identified SEC contact user-agent is configured.",
        "pages": pages,
    }
    save("V97_coverage_audit.json", coverage)
    verdict = {
        "hypothesis": "V97",
        "status": "aborted_data_feasibility_before_outcomes",
        "rule": "Upward change in same-fiscal-year adjusted annual EPS midpoint relative to the most recent verified public forecast on the same accounting basis",
        "pilot_documents_readable": len(pilot),
        "public_issuer_documents_saved": len(inventory),
        "reason": "Readable quarterly releases do not establish an unbroken history of the most recent public forecast. An unreadable 2021-03-08 UNH disclosure falls between the two UNH pilot releases; broader intervening disclosures are also unresolved. Do not assume those documents leave guidance unchanged.",
        "additional_semantic_evidence": "Lilly's 2021-11-02 public announcement estimated about $0.25 additional 2021 EPS, while its 2021-12-15 comparison table still prints the older quarterly forecast as prior. A quarterly-table-only comparison can misclassify new information. Non-GAAP policy changes were also found in 2022 and 2023.",
        "strategy_outcomes_evaluated": False,
        "signal_list_frozen": False,
        "net_ending_cash": None,
        "trade_days": None,
        "later_outcomes_evaluated": False,
        "rescue_variants": 0,
        "profitability": "unknown",
        "paid_data_purchases": 0,
        "documents_preserved_for_distinct_future_research": True,
    }
    assert not (OUT / "V97_evaluation.json").exists()
    save("V97_verdict.json", verdict)
    print(
        json.dumps(
            {
                "V97": verdict,
                "coverage": {
                    k: v
                    for k, v in coverage.items()
                    if k not in {"pages", "representative_unresolved_disclosures"}
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
