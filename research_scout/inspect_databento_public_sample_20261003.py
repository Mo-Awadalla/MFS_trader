"""Bounded, unauthenticated inspection of links published on Databento's site."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import requests
from requests.auth import AuthBase

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/databento_public_mbo_20261003"
URLS = {
    "mbo": "https://hist.databento.com/v0/dataset/sample/download/xnas.itch/mbo?sample_type=equities",
    "mbp1": "https://hist.databento.com/v0/dataset/sample/download/xnas.itch/mbp-1?sample_type=equities",
}


class PublicOnly(AuthBase):
    def __call__(self, request):
        request.headers.pop("Authorization", None)
        return request


def main():
    OUT.mkdir(exist_ok=True)
    sources = []
    for schema, url in URLS.items():
        path = OUT / (schema + ".prefix.csv")
        assert not path.exists()
        chunks, size, complete = [], 0, True
        with requests.get(url, auth=PublicOnly(), headers={"Range": "bytes=0-65535"},
                          stream=True, timeout=(10, 30), allow_redirects=False) as response:
            assert response.status_code in (200, 206), response.status_code
            assert response.headers.get("Content-Type", "").startswith("text/csv")
            headers = {k: v for k, v in response.headers.items() if k.lower() in (
                "content-type", "content-length", "content-range", "content-disposition", "etag", "last-modified")}
            for chunk in response.iter_content(8192):
                remaining = 65536 - size
                chunks.append(chunk[:remaining])
                size += len(chunk[:remaining])
                if size == 65536:
                    complete = False
                    break
        content = b"".join(chunks)
        path.write_bytes(content)
        record = {"schema": schema, "url": url, "bytes_received": len(content),
                  "status": response.status_code, "headers": headers,
                  "reached_response_eof": complete, "local_path": str(path),
                  "sha256": hashlib.sha256(content).hexdigest(),
                  "complete_text_lines": content.count(b"\n"), "first_lines": content.decode("utf-8").splitlines()[:6]}
        sources.append(record)
        print(json.dumps(record), flush=True)
    result = {"inspected_at_utc": datetime.now(UTC).isoformat(),
              "official_link_source": "https://databento.com/tick-data",
              "sources": sources, "authentication_used": False, "paid_calls": 0,
              "account_credit_queries": 0, "returns_calculated": False}
    (OUT / "public_sample_inspection.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
