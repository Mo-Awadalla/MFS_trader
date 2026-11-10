"""Reject unresolved management attribution instead of treating non-analysts as executives.

The legacy pilot extractor is preserved. This additional admission gate was
required by a source-only audit before fitting or inspecting candidate returns.
"""

import re

from research_scout.audit_transcript_pilot_20260907 import (
    TranscriptParser,
)
from research_scout.audit_transcript_pilot_20260907 import (
    extract_page as legacy_extract_page,
)


def explicit_management_role(role):
    # Multiple separators commonly encode outside institution + job title.
    # Uncertain labels are rejected, never inferred from a person's name.
    if " -- " in role or re.search(
        r"analyst|equity research|reporter|journalist|media|editor|shareholder|partner|analst|analsyt|analsyst|\banalys\b|anbalyst|analtsr|ana;lyst",
        role,
        re.I,
    ):
        return False
    return bool(
        re.search(
            r"\b(chief|officer|president|chairman|chairwoman|chairperson|chair|ceo|cfo|coo|cto|cio|evp|svp|vp|treasurer|controller|general counsel|investor relations|co-founder|founder|head of (sales|domestic businesses|international businesses|communications|finance|operations|strategy|marketing))\b",
            role,
            re.I,
        )
    )


def extract_page(html):
    parsed = legacy_extract_page(html)
    speakers = {p["speaker"] for rows in parsed["management_sections"].values() for p in rows}
    roles = {p["name"]: p["role"] for p in parsed["participants"]}
    missing = speakers - set(roles)
    if missing:
        parser = TranscriptParser()
        parser.feed(html)
        for block in parser.blocks:
            bold = block["bold_prefix"]
            if bold in missing and block["text"].startswith(bold + " -- "):
                roles[bold] = block["text"].split(" -- ", 1)[1]
    bad = [
        {"speaker": speaker, "role": roles.get(speaker)}
        for speaker in sorted(speakers)
        if not explicit_management_role(roles.get(speaker, ""))
    ]
    parsed["management_attribution_unresolved"] = bad
    if bad:
        parsed["problems"].append("management_attribution_not_explicit")
    return parsed
