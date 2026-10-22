"""Deterministic facts: the only things a briefing is allowed to say."""

from __future__ import annotations

from pgmlens_core import AnalysisResult, Severity
from pgmlens_core.dates import short_date
from pydantic import BaseModel, Field


class Fact(BaseModel):
    id: str = Field(description="Stable handle such as F3. Claims cite facts by id.")
    kind: str
    text: str
    action: str = ""
    evidence: list[str] = Field(default_factory=list, description="Issue keys behind this fact.")
    finding_id: str | None = None

    @property
    def corpus(self) -> str:
        """Everything a claim citing this fact may legitimately mention."""
        return " ".join([self.text, self.action, *self.evidence])


def build_facts(result: AnalysisResult, *, max_findings: int = 8) -> list[Fact]:
    facts: list[Fact] = []

    def add(kind: str, text: str, **kwargs: object) -> None:
        facts.append(Fact(id=f"F{len(facts) + 1}", kind=kind, text=text, **kwargs))  # type: ignore[arg-type]

    s, h = result.stats, result.health
    add("status", f"Overall program status: {h.label}.")
    add(
        "stats",
        f"{s.open} issues are open and {s.done} are done; {s.blocked} are blocked, "
        f"{s.in_progress} are in progress and {s.unassigned_open} open issues have no owner.",
    )
    counts = h.severity_counts
    add(
        "risk-summary",
        f"{counts['critical']} critical, {counts['high']} high, {counts['medium']} medium and "
        f"{counts['low']} low risks were detected.",
    )

    for fc in result.forecasts:
        if fc.status == "ok" and fc.p50_date and fc.p80_date:
            due = f"due {short_date(fc.due_date)}; " if fc.due_date else ""
            prob = (
                f"{fc.on_time_probability:.0%} chance of finishing on time; "
                if fc.on_time_probability is not None
                else ""
            )
            text = (
                f"{fc.scope_name}: {due}{prob}most likely {short_date(fc.p50_date)}; "
                f"80% confident by {short_date(fc.p80_date)}; {fc.remaining} issues remain in scope."
            )
        else:
            text = f"{fc.scope_name}: {fc.summary}."
        add("forecast", text)

    notable = [
        f
        for f in result.findings
        if f.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)
    ]
    for finding in notable[:max_findings]:
        add(
            "risk",
            f"[{finding.severity.value}] {finding.title}: {finding.message}",
            action=finding.action,
            evidence=finding.issue_keys,
            finding_id=finding.id,
        )
    return facts
