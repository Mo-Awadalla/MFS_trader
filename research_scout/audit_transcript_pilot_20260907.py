"""Returns-blind, cross-sector source audit for a new language-information lead.

This does not specify or evaluate a trading rule. It verifies the inputs needed
before choosing an algorithm, avoiding another premature strategy backtest.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout" / "edge_discovery_20260907"
PILOT = ["AAPL", "AMT", "CAT", "CVX", "JNJ", "JPM", "LIN", "MSFT", "NEE", "PG", "WMT", "XOM"]
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(name: str, value) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


class TranscriptParser(HTMLParser):
    """Keep the transcript's paragraphs/headings, excluding the surrounding page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.article_depth = 0
        self.skip_depth = 0
        self.tag = None
        self.parts = []
        self.bold_prefix = []
        self.capture_bold = False
        self.blocks = []
        self.json_script = False
        self.json_parts = []
        self.metadata = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.json_script = True
            self.json_parts = []
        if not self.article_depth:
            if attrs.get("id") == "article-body-transcript":
                self.article_depth = 1
            return
        if tag not in VOID:
            self.article_depth += 1
        if tag in {"script", "style"}:
            self.skip_depth += 1
        if tag in {"p", "h1", "h2", "h3"}:
            self.tag = tag
            self.parts = []
            self.bold_prefix = []
            self.capture_bold = False
        if tag == "strong" and self.tag == "p" and not "".join(self.parts).strip():
            self.capture_bold = True

    def handle_endtag(self, tag):
        if tag == "script" and self.json_script:
            self.json_script = False
            try:
                self.metadata.append(json.loads("".join(self.json_parts)))
            except json.JSONDecodeError:
                self.metadata.append({"parse_error": True})
        if not self.article_depth or tag in VOID:
            return
        if tag == "strong":
            self.capture_bold = False
        if tag == self.tag:
            text = " ".join("".join(self.parts).split())
            if text:
                self.blocks.append(
                    {
                        "tag": tag,
                        "text": text,
                        "bold_prefix": " ".join("".join(self.bold_prefix).split()),
                    }
                )
            self.tag, self.parts = None, []
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
        self.article_depth -= 1

    def handle_data(self, data):
        if self.json_script:
            self.json_parts.append(data)
        if self.article_depth and self.tag and not self.skip_depth:
            self.parts.append(data)
            if self.capture_bold:
                self.bold_prefix.append(data)


def article_metadata(items):
    found = []
    for item in items:
        if isinstance(item, list):
            found.extend(article_metadata(item))
        elif isinstance(item, dict):
            if item.get("@type") in {"NewsArticle", "Article"}:
                found.append(item)
            found.extend(article_metadata(item.get("@graph", [])))
    return found


def extract_page(html: str) -> dict:
    parser = TranscriptParser()
    parser.feed(html)
    metadata = article_metadata(parser.metadata)
    problems = []
    if len(metadata) != 1:
        problems.append("article_metadata_not_unique")
    meta = metadata[0] if len(metadata) == 1 else {}
    sections = {"prepared": [], "qa": [], "participants": []}
    state = None
    header_count = dict.fromkeys(sections, 0)
    for block in parser.blocks:
        lower = block["text"].lower().rstrip(":")
        if block["tag"].startswith("h"):
            if lower == "prepared remarks":
                state = "prepared"
            elif lower in {"questions and answers", "questions & answers"}:
                state = "qa"
            elif lower == "call participants":
                state = "participants"
            else:
                state = None
            if state:
                header_count[state] += 1
        elif state:
            sections[state].append(block)
    for key in sections:
        if header_count[key] != 1:
            problems.append(f"{key}_heading_not_unique")
    published = meta.get("datePublished")
    modified = meta.get("dateModified")
    parsed_times = []
    for key, value in [("published", published), ("modified", modified)]:
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                problems.append(f"{key}_timezone_missing")
            parsed_times.append(timestamp)
        except (AttributeError, TypeError, ValueError):
            problems.append(f"{key}_invalid")
    available = (
        max(parsed_times).isoformat()
        if len(parsed_times) == 2 and all(t.tzinfo is not None for t in parsed_times)
        else None
    )
    # Stop at the first non-speaker paragraph. The later disclosure is not a speaker.
    participants = []
    for block in sections["participants"]:
        paragraph = block["text"]
        if " -- " not in paragraph:
            break
        name, role = paragraph.split(" -- ", 1)
        participants.append({"name": name, "role": role, "analyst": "analyst" in role.lower()})
    role_by_name = {p["name"]: p for p in participants}
    management_sections = {"prepared": [], "qa": []}
    unknown_speakers = []
    qa_questions = []
    qa_before_first_question = []
    for key in management_sections:
        active = None
        active_is_management = False
        active_is_analyst = False
        current_question = None
        for block in sections[key]:
            paragraph = block["text"]
            name = paragraph.split(" -- ", 1)[0]
            bold_name = block["bold_prefix"]
            is_header = bool(bold_name) and (
                paragraph == bold_name or paragraph.startswith(bold_name + " -- ")
            )
            if is_header:
                active = name
                active_is_management = False
                active_is_analyst = False
                role = paragraph.split(" -- ", 1)[1] if " -- " in paragraph else ""
                if name.lower() == "operator":
                    pass
                elif "analyst" in role.lower():
                    active_is_analyst = True
                elif name in role_by_name:
                    active_is_management = not role_by_name[name]["analyst"]
                    active_is_analyst = role_by_name[name]["analyst"]
                elif re.search(
                    r"\b(chief|officer|president|director|relations|ceo|cfo|coo|chairman)\b",
                    role,
                    re.I,
                ):
                    active_is_management = True
                elif paragraph.startswith("Duration:"):
                    pass
                else:
                    unknown_speakers.append(paragraph)
                if key == "qa" and active_is_analyst:
                    current_question = len(qa_questions)
                    qa_questions.append({"analyst": name, "paragraphs": []})
            elif key == "qa" and active_is_analyst:
                qa_questions[current_question]["paragraphs"].append(paragraph)
            elif active_is_management and not paragraph.startswith("Duration:"):
                if key == "qa" and current_question is None:
                    qa_before_first_question.append({"speaker": active, "text": paragraph})
                else:
                    management_sections[key].append(
                        {
                            "speaker": active,
                            "text": paragraph,
                            "preceding_question": current_question,
                        }
                    )
    counts = {
        key: sum(len(re.findall(r"[A-Za-z]+", p["text"])) for p in paragraphs)
        for key, paragraphs in management_sections.items()
    }
    for key, count in counts.items():
        if count < 500:
            problems.append(f"{key}_management_text_below_500_words")
    if not any(p["analyst"] for p in participants):
        problems.append("analyst_roles_unidentified")
    if unknown_speakers:
        problems.append("unresolved_speaker_headers")
    return {
        "headline": meta.get("headline"),
        "published": published,
        "modified": modified,
        "conservative_page_available_at": available,
        "availability_basis": "Publisher's current timezone-aware published/modified metadata, not an independently archived first version or the call start time.",
        "participants": participants,
        "management_word_counts": counts,
        "management_sections": management_sections,
        "qa_questions": qa_questions,
        "qa_before_first_question_words": sum(
            len(re.findall(r"[A-Za-z]+", p["text"])) for p in qa_before_first_question
        ),
        "section_heading_counts": header_count,
        "block_count": len(parser.blocks),
        "unknown_speakers": unknown_speakers,
        "problems": problems,
    }


def freeze() -> None:
    OUT.mkdir(exist_ok=True)
    path = OUT / "discovery_protocol.json"
    if path.exists():
        return
    cached = [ROOT / "data/parquet/equity/alpaca_sip" / f"{s}_1d.parquet" for s in PILOT]
    protocol = {
        "created_at": datetime.now(UTC).isoformat(),
        "purpose": "Evidence-led discovery and public-text data feasibility, not a backtest or a validated trading edge.",
        "candidate": "Slow incorporation of information in management's answers to analysts, incremental to prepared remarks and the stock's response before entry.",
        "pilot_selection": "Earliest transcript URL in January-March 2021 for each fixed company; fixed without reading any candidate stock return or sentiment score.",
        "symbols": PILOT,
        "sectors_represented": "Technology, real estate, industrials, energy, health care, financials, materials, utilities and consumer staples; deliberately broad source-format pilot, not representative market-universe sampling.",
        "data_requirements": [
            "Timezone-aware publisher publication and modification times",
            "Separate prepared remarks and Q&A",
            "Separate management answers from analyst questions",
            "Exclude surrounding advertisements, recommendations and later stock performance",
            "Match local prices by identifier and exchange session before a future test",
            "Call start alone is not transcript availability",
        ],
        "stop": "If source fields cannot support these checks, report the source failure; never create a backtest by guessing clocks or treating missing text as neutral sentiment.",
        "scope": "At most three monthly sitemaps and one transcript per fixed pilot company, plus the two already-inspected 2023 MSFT format examples. No model training, return analysis, position or account change.",
        "already_exposed": [
            "The two July/January 2023 MSFT pages were inspected to locate timestamp and section fields",
            "2021-2025 equity history has been used by older repository experiments",
            "Published studies and their reported results informed discovery; they are not our confirmation",
        ],
        "local_price_file_hashes": {
            str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in cached if p.exists()
        },
        "missing_local_daily_price_files": [
            str(p.relative_to(ROOT)) for p in cached if not p.exists()
        ],
    }
    with path.open("x", encoding="utf-8") as handle:
        json.dump(protocol, handle, indent=2)


def fetch(url: str, name: str, session: requests.Session, logs: list) -> bytes | None:
    if not url.startswith("https://www.fool.com/"):
        raise ValueError("Only the explicit public publisher is allowed")
    directory = OUT / "pilot_raw"
    directory.mkdir(exist_ok=True)
    path = directory / f"{name}.gz"
    if path.exists():
        return gzip.decompress(path.read_bytes())
    record = {"url": url, "retrieved_at": datetime.now(UTC).isoformat()}
    try:
        response = session.get(url, timeout=25)
        record.update(
            status=response.status_code, bytes=len(response.content), final_url=response.url
        )
        if response.status_code != 200 or len(response.content) > 5_000_000:
            return None
        data = response.content
        path.write_bytes(gzip.compress(data, mtime=0))
        record.update(path=str(path.relative_to(ROOT)), sha256=sha(data))
        return data
    except requests.RequestException as exc:
        record["error"] = type(exc).__name__
        return None
    finally:
        logs.append(record)
        save("pilot_retrieval.json", logs)
        print(
            json.dumps({"url": url, "status": record.get("status", record.get("error"))}),
            flush=True,
        )
        time.sleep(0.5)


def collect() -> None:
    freeze()
    logs_path = OUT / "pilot_retrieval.json"
    logs = json.loads(logs_path.read_text(encoding="utf-8")) if logs_path.exists() else []
    with requests.Session() as session:
        session.headers["User-Agent"] = "mfs-trader public research feasibility/1.0"
        urls = set()
        for month in range(1, 4):
            if month == 1:
                data = (OUT / "source_probe/fool_sitemap_202101.txt").read_bytes()
            else:
                data = fetch(
                    f"https://www.fool.com/sitemap/2021/{month:02d}",
                    f"sitemap_2021{month:02d}",
                    session,
                    logs,
                )
            if data is None:
                raise ValueError("Missing pilot sitemap")
            tree = ET.fromstring(data)
            urls.update(
                e.text
                for e in tree.iter()
                if e.tag.endswith("loc") and e.text and "/earnings/call-transcripts/2021/" in e.text
            )
        selected = []
        for symbol in PILOT:
            pattern = re.compile(rf"-{symbol.lower()}-")
            possible = sorted(url for url in urls if pattern.search(url.rsplit("/", 2)[-2]))
            selected.append(
                {
                    "symbol": symbol,
                    "url": possible[0] if possible else None,
                    "candidate_urls": len(possible),
                }
            )
        save("pilot_manifest.json", selected)
        for row in selected:
            if row["url"]:
                fetch(row["url"], row["symbol"], session, logs)


def audit() -> None:
    manifest = json.loads((OUT / "pilot_manifest.json").read_text(encoding="utf-8"))
    summary = []
    parsed_dir = OUT / "pilot_parsed"
    parsed_dir.mkdir(exist_ok=True)
    for row in manifest:
        path = OUT / "pilot_raw" / f"{row['symbol']}.gz"
        if not path.exists():
            summary.append({**row, "problems": ["missing_source_document"]})
            continue
        data = gzip.decompress(path.read_bytes())
        result = extract_page(data.decode("utf-8"))
        result.update(symbol=row["symbol"], url=row["url"], raw_sha256=sha(data))
        (parsed_dir / f"{row['symbol']}.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        summary.append(
            {
                k: v
                for k, v in result.items()
                if k not in {"management_sections", "participants", "qa_questions"}
            }
        )
    save(
        "pilot_audit.json",
        {
            "selection": "Frozen cross-sector source pilot; no stock returns or sentiment ranks read",
            "documents": summary,
        },
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["freeze", "collect", "audit"])
    globals()[parser.parse_args().mode]()
