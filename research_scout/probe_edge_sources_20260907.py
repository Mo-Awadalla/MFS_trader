"""Bounded public-source discovery; deliberately imports no market-price reader."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout" / "edge_discovery_20260907"
URLS = {
    "fool_msft_20230725": "https://www.fool.com/earnings/call-transcripts/2023/07/25/microsoft-msft-q4-2023-earnings-call-transcript/",
    "fool_msft_20230124": "https://www.fool.com/earnings/call-transcripts/2023/01/24/microsoft-msft-q2-2023-earnings-call-transcript/",
    "fool_sitemap_202101": "https://www.fool.com/sitemap/2021/01",
    "kurry_dataset_card": "https://huggingface.co/datasets/kurry/sp500_earnings_transcripts/raw/main/README.md",
    "kurry_dataset_api": "https://huggingface.co/api/datasets/kurry/sp500_earnings_transcripts",
    "fast_numbers_readme": "https://raw.githubusercontent.com/piqueyd/Fast-Numbers-Slow-Language/main/README.md",
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    raw = OUT / "source_probe"
    raw.mkdir(exist_ok=True)
    results = []
    with requests.Session() as session:
        session.headers["User-Agent"] = "mfs-trader public research feasibility/1.0"
        for name, url in URLS.items():
            path = raw / f"{name}.txt"
            if path.exists():
                print(json.dumps({"name": name, "status": "already_cached"}), flush=True)
                continue
            record = {
                "name": name,
                "url": url,
                "retrieved_at": datetime.now(UTC).isoformat(),
            }
            try:
                response = session.get(url, timeout=25)
                record.update(
                    status=response.status_code,
                    content_type=response.headers.get("Content-Type"),
                    bytes=len(response.content),
                    final_url=response.url,
                )
                if response.status_code == 200 and len(response.content) <= 5_000_000:
                    path.write_bytes(response.content)
                    record.update(
                        path=str(path.relative_to(ROOT)),
                        sha256=hashlib.sha256(response.content).hexdigest(),
                    )
            except requests.RequestException as exc:
                record.update(error=type(exc).__name__)
            results.append(record)
            print(json.dumps(record), flush=True)
    log = OUT / "source_probe_retrieval.json"
    if log.exists():
        results = json.loads(log.read_text(encoding="utf-8")) + results
    log.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
