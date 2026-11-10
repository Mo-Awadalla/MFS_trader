"""Guard against information leakage and speaker contamination in public text."""

import json

from research_scout.audit_transcript_pilot_20260907 import extract_page


def page(extra_qa="", published="2021-01-04T20:00:00Z", modified="2021-01-05T01:00:00Z"):
    metadata = json.dumps(
        {"@type": "NewsArticle", "datePublished": published, "dateModified": modified}
    )
    speech = "Demand improved. " * 260
    return f"""
    <script type="application/ld+json">{metadata}</script>
    <p>FUTURE_PRICE_OUTSIDE_TRANSCRIPT</p>
    <div id="article-body-transcript">
      <p>LIVE_PRICE_INTRODUCTION</p>
      <h2>Prepared Remarks:</h2>
      <p><strong>Alex Exec</strong> -- <em>Chief Executive Officer</em></p>
      <p>{speech}</p>
      <h2>Questions and Answers:</h2>
      <p><strong>Alex Exec</strong> -- Chief Executive Officer</p>
      <p>PRE_QUESTION_PRESENTATION</p>
      <p><strong>Robin Analyst</strong> -- Research Bank -- Analyst</p>
      <p>ANALYST_QUESTION_ONLY</p>
      <p><strong>Alex Exec</strong> -- Chief Executive Officer</p>
      <p>We -- we expect demand to improve. {speech}</p>
      {extra_qa}
      <h2>Call participants:</h2>
      <p><strong>Alex Exec</strong> -- Chief Executive Officer</p>
      <p><strong>Robin Analyst</strong> -- Research Bank -- Analyst</p>
    </div>
    <p>FUTURE_ADVERTISEMENT</p>
    """


def test_restricts_content_to_management_after_an_analyst_question():
    result = extract_page(page())
    assert not result["problems"]
    answers = " ".join(p["text"] for p in result["management_sections"]["qa"])
    assert "We -- we expect demand to improve." in answers
    for forbidden in [
        "FUTURE_",
        "LIVE_PRICE",
        "ANALYST_QUESTION_ONLY",
        "PRE_QUESTION_PRESENTATION",
    ]:
        assert forbidden not in answers
    assert result["qa_questions"][0]["paragraphs"] == ["ANALYST_QUESTION_ONLY"]
    assert result["management_sections"]["qa"][0]["preceding_question"] == 0


def test_unknown_speaker_does_not_inherit_executive_identity():
    result = extract_page(page("<p><strong>Unknown speaker</strong></p><p>UNIDENTIFIED_WORDS</p>"))
    assert "unresolved_speaker_headers" in result["problems"]
    assert all("UNIDENTIFIED_WORDS" not in p["text"] for p in result["management_sections"]["qa"])


def test_uses_latest_version_time_and_rejects_naive_metadata():
    result = extract_page(page())
    assert result["conservative_page_available_at"] == "2021-01-05T01:00:00+00:00"
    naive = extract_page(page(published="2021-01-04T20:00:00"))
    assert "published_timezone_missing" in naive["problems"]
    assert naive["conservative_page_available_at"] is None


def test_explicit_analyst_role_handles_participant_name_variants():
    extra = """
      <p><strong>Robin M. Analyst</strong> -- Research Bank -- Analyst</p>
      <p>RENAMED_ANALYST_QUESTION</p>
      <p><strong>Alex Exec</strong> -- Chief Executive Officer</p>
      <p>DIRECT_MANAGEMENT_ANSWER</p>
    """
    result = extract_page(page(extra))
    assert not result["problems"]
    answers = result["management_sections"]["qa"]
    assert answers[-1]["text"] == "DIRECT_MANAGEMENT_ANSWER"
    assert answers[-1]["preceding_question"] == 1
    assert all("RENAMED_ANALYST_QUESTION" not in p["text"] for p in answers)
