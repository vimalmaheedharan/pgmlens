import json
from types import SimpleNamespace

import pytest
from pgmlens_core import analyze
from pgmlens_core.demo import generate_demo
from pgmlens_reporting import (
    BriefingDraft,
    Claim,
    Section,
    build_briefing,
    build_facts,
    render_markdown,
    validate_draft,
)


@pytest.fixture(scope="module")
def result():
    return analyze(generate_demo())


@pytest.fixture(scope="module")
def facts(result):
    return build_facts(result)


def reply(payload) -> SimpleNamespace:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def scripted(*replies):
    """A fake LiteLLM completion that returns the given replies in order."""
    calls = []
    queue = list(replies)

    def completion(**kwargs):
        calls.append(kwargs)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return reply(item)

    completion.calls = calls
    return completion


def grounded_draft(facts) -> dict:
    status = next(f for f in facts if f.kind == "status")
    return {
        "headline": "Program is off track",
        "sections": [
            {"title": "Where we stand", "claims": [{"text": status.text, "fact_ids": [status.id]}]}
        ],
    }


def test_facts_are_numbered_and_cover_status_forecasts_and_risks(facts):
    assert [f.id for f in facts] == [f"F{n}" for n in range(1, len(facts) + 1)]
    kinds = {f.kind for f in facts}
    assert {"status", "stats", "risk-summary", "forecast", "risk"} <= kinds
    risk = next(f for f in facts if f.kind == "risk")
    assert risk.finding_id and risk.evidence and risk.action


def test_deterministic_briefing_is_fully_grounded(result, facts):
    briefing = build_briefing(result)
    assert briefing.source == "deterministic" and briefing.warnings == []
    assert validate_draft(briefing, facts) == []
    assert all(claim.fact_ids for section in briefing.sections for claim in section.claims)


def test_markdown_shows_evidence(result):
    text = render_markdown(build_briefing(result))
    assert text.startswith("# Atlas Platform Migration: executive briefing")
    assert "## Evidence" in text and "[F1]" in text
    assert "deterministic" in text


def test_a_grounded_llm_draft_is_accepted(result, facts):
    completion = scripted(grounded_draft(facts))
    briefing = build_briefing(result, model="any-model", completion=completion)
    assert briefing.source == "llm" and briefing.warnings == []
    assert len(completion.calls) == 1
    assert "Facts:" in completion.calls[0]["messages"][1]["content"]


def test_code_fenced_json_is_accepted(result, facts):
    fenced = "```json\n" + json.dumps(grounded_draft(facts)) + "\n```"
    briefing = build_briefing(result, model="m", completion=scripted(fenced))
    assert briefing.source == "llm"


def test_invented_numbers_are_rejected_then_retried(result, facts):
    bad = grounded_draft(facts)
    bad["sections"][0]["claims"][0]["text"] += " We expect 97 more issues to arrive."
    completion = scripted(bad, grounded_draft(facts))
    briefing = build_briefing(result, model="m", completion=completion)
    assert briefing.source == "llm"
    assert len(completion.calls) == 2
    assert "rejected" in completion.calls[1]["messages"][1]["content"]
    assert "97" in completion.calls[1]["messages"][1]["content"]


def test_persistently_ungrounded_drafts_fall_back_with_a_warning(result, facts):
    bad = grounded_draft(facts)
    bad["headline"] = "We will ship 42 days early"  # figures are not allowed in headlines
    briefing = build_briefing(result, model="m", completion=scripted(bad, bad))
    assert briefing.source == "deterministic"
    assert any("not grounded" in w for w in briefing.warnings)
    assert "Note:" in render_markdown(briefing)


def test_unknown_fact_ids_and_invented_issue_keys_are_caught(facts):
    draft = BriefingDraft(
        headline="Status",
        sections=[
            Section(title="A", claims=[Claim(text="Something", fact_ids=["F999"])]),
            Section(title="B", claims=[Claim(text="ZZZ-7 is late", fact_ids=["F1"])]),
        ],
    )
    problems = validate_draft(draft, facts)
    assert any("unknown fact ids" in p for p in problems)
    assert any("ZZZ-7" in p for p in problems)


def test_number_formatting_differences_are_tolerated():
    from pgmlens_reporting.facts import Fact

    fact = Fact(id="F1", kind="forecast", text="Beta: most likely Nov 08.")
    ok = BriefingDraft(
        headline="x",
        sections=[Section(title="t", claims=[Claim(text="Due Nov 8", fact_ids=["F1"])])],
    )
    assert validate_draft(ok, [fact]) == []


def test_malformed_output_and_api_failures_never_break_the_briefing(result):
    junk = build_briefing(
        result, model="m", completion=scripted("not json at all", "{still: not json")
    )
    assert junk.source == "deterministic" and junk.warnings
    down = build_briefing(result, model="m", completion=scripted(ConnectionError("down")))
    assert down.source == "deterministic"
    assert any("LLM call failed" in w for w in down.warnings)


def test_empty_drafts_are_rejected(facts):
    assert "no claims" in " ".join(validate_draft(BriefingDraft(headline="x", sections=[]), facts))
