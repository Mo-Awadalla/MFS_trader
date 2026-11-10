"""Cross-check first announced CPI summaries against saved official BLS extracts."""

import json
import re
from datetime import datetime

import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.prepare_cpi_hft_20260930 import OUT


def parse_release(text):
    text = re.sub(r"(?m)^L\d+(?:@P\d+)?:\s*", "", text)
    text = " ".join(text.split())
    start = text.find("Transmission of material")
    if start < 0:
        raise ValueError("No source embargo header")
    body = text[start:]
    header = body[:240]
    if not re.search(r"8:30 a\.m\. \((?:EST|EDT|ET)\)", header):
        raise ValueError("Release clock not confirmed")
    stamp = re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}", header)
    day = datetime.strptime(stamp.group(), "%B %d, %Y").date().isoformat()
    output = {"release_date": day, "clock_et": "08:30:00"}
    for key, prefix in [("headline_announced", r"\(CPI-U\)"),
                        ("core_announced", r"(?:The index for all items less food and energy|The all items less food and energy index)")]:
        found = re.search(prefix+r"\s+(?:(?:was|remained)\s+)?(?:also\s+)?(increased|rose|decreased|declined|fell|unchanged)\b\s*([0-9.]+)?", body, flags=re.I)
        if not found:
            raise ValueError("No unambiguous summary value: "+key)
        verb, value = found.groups()
        output[key] = 0.0 if verb.lower() == "unchanged" else float(value)*(-1 if verb.lower() in {"decreased", "declined", "fell"} else 1)
    return output


def main():
    panel = pd.read_parquet(OUT/"content_events.parquet")
    records = []
    for event in panel.to_dict("records"):
        path = OUT/"source_audit/bls_web"/f"{event['release_date']}.txt"
        record = {"date": event["release_date"], "url": event["bls_url"], "content_trigger": event["content_trigger"], "verified": False}
        pdf = path.with_name(path.stem+"_pdf.txt")
        if pdf.exists():
            record["html_attempt_sha256"] = digest(path)
            path = pdf
            record["url"] = event["bls_url"].replace(".htm", ".pdf")
        if path.exists():
            record["source_sha256"] = digest(path)
            try:
                actual = parse_release(path.read_text(encoding="utf8"))
                record.update(parsed=actual, verified=all(actual[k] == event[k] for k in ["release_date", "headline_announced", "core_announced"]))
            except Exception as e:
                record["reason"] = str(e)
        else:
            record["reason"] = "source_not_yet_saved"
        records.append(record)
    result = {"verified": all(r["verified"] for r in records), "releases": len(records),
              "verified_releases": sum(r["verified"] for r in records),
              "verified_trigger_releases": sum(r["verified"] and r["content_trigger"] for r in records),
              "records": records, "historical_receipt_time_verified": False}
    (OUT/"source_audit/bls_verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k: v for k, v in result.items() if k != "records"}))
    print(json.dumps([r for r in records if not r["verified"]], indent=2))


if __name__ == "__main__":
    main()
