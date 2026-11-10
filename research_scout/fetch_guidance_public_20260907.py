"""Bounded retrieval of public issuer releases; no keys, billing or orders."""

import argparse
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/new_information_tests_20260907"
ALLOWED = {
    "news.abbvie.com",
    "investors.abbvie.com",
    "investor.lilly.com",
    "www.amgen.com",
    "investors.amgen.com",
    "www.unitedhealthgroup.com",
    "investors.cvshealth.com",
}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.suppressed += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.suppressed = max(0, self.suppressed - 1)

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)

    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.manifest.read_text(encoding="utf-8"))
    if len(plan) > 100:
        raise ValueError("Bounded maximum is 100 explicitly listed public documents")
    folder = OUT / "public_documents"
    folder.mkdir(exist_ok=True)
    results = []
    for item in plan:
        url = item["url"]
        if urlparse(url).hostname not in ALLOWED or not url.startswith("https://"):
            raise ValueError("Only explicitly allowed public issuer domains")
        kind = item.get("format", "html")
        if kind not in {"html", "pdf"}:
            raise ValueError("Only HTML or PDF issuer documents")
        path = folder / f"{item['symbol']}_{item['date']}.{kind}"
        record = {**item, "retrieved_utc": datetime.now(UTC).isoformat()}
        try:
            if not path.exists():
                response = requests.get(url, timeout=20)
                record["status"] = response.status_code
                response.raise_for_status()
                expected = "application/pdf" if kind == "pdf" else "text/html"
                if expected not in response.headers.get("Content-Type", ""):
                    raise ValueError("Unexpected public release content type")
                if kind == "pdf":
                    path.write_bytes(response.content)
                else:
                    path.write_text(response.text, encoding="utf-8")
                time.sleep(0.2)
            if kind == "pdf":
                from pypdf import PdfReader

                plain = "\n".join(page.extract_text() for page in PdfReader(path).pages)
            else:
                parser_ = PlainText()
                parser_.feed(path.read_text(encoding="utf-8"))
                plain = parser_.text()
            textpath = path.with_suffix(".txt")
            textpath.write_text(plain, encoding="utf-8")
            record.update(
                {
                    "status": 200,
                    "path": str(path.relative_to(ROOT)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "characters": len(plain),
                }
            )
            snippets = [
                plain[max(0, match.start() - 80) : match.end() + 330]
                for match in re.finditer(r"guidance|outlook", plain, re.I)
            ]
            record["guidance_contexts"] = snippets[:25]
            print(item["symbol"], item["date"], "saved", len(plain), flush=True)
        except (requests.RequestException, ValueError) as exc:
            record["error"] = str(exc)
            print(item["symbol"], item["date"], "unavailable", type(exc).__name__, flush=True)
        results.append(record)
    target = OUT / (args.manifest.stem + "_retrieval.json")
    target.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
