"""Executive briefings: deterministic by default, LLM-phrased when asked, always evidence-checked.

The rule is simple: the LLM *explains*, it never *invents*. It receives a numbered list of
facts computed by the engines and may only write claims that cite those fact ids. Every
number and issue key in a claim must appear in the facts it cites. A draft that breaks
either rule is rejected (one retry with the reason), then replaced by the deterministic
briefing, with a warning explaining why.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date
from typing import Any, Literal

from pgmlens_core import AnalysisResult, Dataset
from pydantic import BaseModel, Field, ValidationError

from .facts import Fact, build_facts

Completion = Callable[..., Any]


class Claim(BaseModel):
    text: str
    fact_ids: list[str] = Field(min_length=1)


class Section(BaseModel):
    title: str
    claims: list[Claim]


class BriefingDraft(BaseModel):
    """The shape an LLM must return."""

    headline: str
    sections: list[Section]


class Briefing(BriefingDraft):
    program: str
    as_of: date
    source: Literal["deterministic", "llm"]
    facts: list[Fact]
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- deterministic


def deterministic_draft(result: AnalysisResult, facts: list[Fact]) -> BriefingDraft:
    by_kind: dict[str, list[Fact]] = {}
    for fact in facts:
        by_kind.setdefault(fact.kind, []).append(fact)

    def claims(kind: str) -> list[Claim]:
        return [Claim(text=f.text, fact_ids=[f.id]) for f in by_kind.get(kind, [])]

    stand = claims("status") + claims("stats") + claims("risk-summary")
    attention = [Claim(text=f.text, fact_ids=[f.id]) for f in by_kind.get("risk", [])[:5]]
    steps: list[Claim] = []
    seen: set[str] = set()
    for fact in by_kind.get("risk", []):
        if fact.action and fact.action not in seen:
            seen.add(fact.action)
            steps.append(Claim(text=fact.action, fact_ids=[fact.id]))
    sections = [
        Section(title="Where we stand", claims=stand),
        Section(title="Delivery forecast", claims=claims("forecast")),
    ]
    if attention:
        sections.append(Section(title="What needs attention", claims=attention))
    if steps:
        sections.append(Section(title="Recommended next steps", claims=steps[:5]))
    return BriefingDraft(headline=result.health.headline, sections=sections)


# --------------------------------------------------------------------------- validation

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_KEY = re.compile(r"[A-Za-z][\w./-]*[#-]\d+")


def _numbers(text: str) -> set[str]:
    out = set()
    for token in _NUMBER.findall(text):
        out.add(token.lstrip("0") or "0")
    return out


def validate_draft(draft: BriefingDraft, facts: list[Fact]) -> list[str]:
    """Return a list of problems; empty means every claim is grounded."""
    by_id = {f.id: f for f in facts}
    problems: list[str] = []

    def check(text: str, corpus: str, where: str) -> None:
        for number in sorted(_numbers(text) - _numbers(corpus)):
            problems.append(f"{where}: the number {number!r} is not in the cited facts")
        for key in sorted(set(_KEY.findall(text))):
            if key not in corpus:
                problems.append(f"{where}: {key!r} is not in the cited facts")

    check(
        draft.headline, "", "headline"
    )  # headlines are qualitative: figures belong in cited claims
    for section in draft.sections:
        for n, claim in enumerate(section.claims, 1):
            where = f"{section.title} #{n}"
            unknown = [i for i in claim.fact_ids if i not in by_id]
            if unknown:
                problems.append(f"{where}: unknown fact ids {unknown}")
                continue
            check(claim.text, " ".join(by_id[i].corpus for i in claim.fact_ids), where)
    if not any(section.claims for section in draft.sections):
        problems.append("the briefing contains no claims")
    return problems


# --------------------------------------------------------------------------- LLM path

SYSTEM_PROMPT = """You write concise executive briefings about software delivery programs.

Rules you must follow:
1. Use ONLY the numbered facts provided. Never add numbers, dates, names or issue keys that are not in them.
2. Every claim must list the ids of the facts it relies on in "fact_ids".
3. Copy numbers, dates and issue keys exactly as written in the facts (do not round or reformat).
4. The headline must contain no digits and no issue keys; put figures in cited claims.
5. Write for a busy executive: plain language, no jargon, lead with what matters most.
6. Return only JSON: {"headline": str, "sections": [{"title": str, "claims": [{"text": str, "fact_ids": [str]}]}]}.
Suggested sections: Where we stand, Delivery forecast, What needs attention, Recommended next steps."""


def _extract_json(content: str) -> Any:
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def _default_completion(**kwargs: Any) -> Any:
    try:
        import litellm
    except ImportError as exc:
        raise RuntimeError("Install pgmlens-reporting[llm] to use an LLM.") from exc
    return litellm.completion(**kwargs)


def _ask_llm(
    model: str, facts: list[Fact], completion: Completion, feedback: str | None
) -> BriefingDraft:
    payload = [{"id": f.id, "fact": f.text, "suggested_action": f.action or None} for f in facts]
    user = "Facts:\n" + json.dumps(payload, indent=2)
    if feedback:
        user += (
            f"\n\nYour previous draft was rejected:\n{feedback}\nFix these problems and try again."
        )
    response = completion(
        model=model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    return BriefingDraft.model_validate(_extract_json(content))


def build_briefing(
    result: AnalysisResult,
    ds: Dataset | None = None,
    *,
    model: str | None = None,
    completion: Completion | None = None,
    max_findings: int = 8,
) -> Briefing:
    """Build a briefing. With ``model`` set, an LLM phrases it; otherwise it is templated."""
    facts = build_facts(result, max_findings=max_findings)
    warnings: list[str] = []
    draft: BriefingDraft | None = None
    source: Literal["deterministic", "llm"] = "deterministic"

    if model:
        call = completion or _default_completion
        feedback: str | None = None
        for _attempt in range(2):
            try:
                candidate = _ask_llm(model, facts, call, feedback)
            except (
                json.JSONDecodeError,
                ValidationError,
                AttributeError,
                IndexError,
                KeyError,
            ) as exc:
                feedback = f"The response was not valid briefing JSON ({type(exc).__name__})."
                continue
            except (
                Exception
            ) as exc:  # network, auth, quota: do not hide, but do not fail the briefing
                warnings.append(
                    f"LLM call failed ({type(exc).__name__}); used the deterministic briefing."
                )
                break
            problems = validate_draft(candidate, facts)
            if not problems:
                draft, source = candidate, "llm"
                break
            feedback = "\n".join(f"- {p}" for p in problems[:8])
        if draft is None and not warnings:
            warnings.append(
                "The LLM draft was rejected because it was not grounded in the facts "
                f"({feedback.splitlines()[0] if feedback else 'unknown reason'}); used the deterministic briefing."
            )

    if draft is None:
        draft = deterministic_draft(result, facts)
    return Briefing(
        program=result.program.name,
        as_of=result.as_of.date(),
        source=source,
        facts=facts,
        warnings=warnings,
        headline=draft.headline,
        sections=draft.sections,
    )
