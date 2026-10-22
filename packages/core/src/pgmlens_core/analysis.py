"""The ``analyze`` facade: dataset in, health + forecasts + graph + findings out."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .forecast import ForecastResult, forecast_milestones
from .graph import GraphAnalysis, analyze_graph
from .models import Dataset, ProgramInfo, Status
from .risk import SEVERITY_RANK, Context, Finding, RuleSet, Severity, evaluate_rules, load_rules

HealthStatus = Literal["on_track", "at_risk", "off_track"]

_LABELS: dict[HealthStatus, str] = {
    "on_track": "On track",
    "at_risk": "At risk",
    "off_track": "Off track",
}


class Stats(BaseModel):
    total: int
    open: int
    done: int
    todo: int
    in_progress: int
    blocked: int
    unassigned_open: int


class ProgramHealth(BaseModel):
    status: HealthStatus
    label: str
    headline: str
    reasons: list[str]
    severity_counts: dict[str, int]


class AnalysisResult(BaseModel):
    program: ProgramInfo
    as_of: datetime
    health: ProgramHealth
    stats: Stats
    forecasts: list[ForecastResult]
    graph: GraphAnalysis
    findings: list[Finding]


def _stats(ds: Dataset) -> Stats:
    count = {s: sum(1 for i in ds.issues if i.status is s) for s in Status}
    return Stats(
        total=len(ds.issues),
        open=len(ds.issues) - count[Status.DONE],
        done=count[Status.DONE],
        todo=count[Status.TODO],
        in_progress=count[Status.IN_PROGRESS],
        blocked=count[Status.BLOCKED],
        unassigned_open=sum(1 for i in ds.issues if i.is_open and not i.assignee),
    )


def _health(findings: list[Finding]) -> ProgramHealth:
    counts = {s.value: 0 for s in Severity}
    for finding in findings:
        counts[finding.severity.value] += 1
    if counts["critical"] > 0:
        status: HealthStatus = "off_track"
    elif counts["high"] > 0 or counts["medium"] >= 3:
        status = "at_risk"
    else:
        status = "on_track"
    ranked = sorted(findings, key=lambda f: -SEVERITY_RANK[f.severity])
    if ranked:
        headline = f"{_LABELS[status]}: {ranked[0].title.lower()}"
    else:
        headline = f"{_LABELS[status]}: no significant risks detected"
    return ProgramHealth(
        status=status,
        label=_LABELS[status],
        headline=headline,
        reasons=[f.message for f in ranked[:3]],
        severity_counts=counts,
    )


def analyze(
    ds: Dataset,
    rules: RuleSet | None = None,
    *,
    as_of: datetime | None = None,
    trials: int = 5000,
    seed: int = 7,
) -> AnalysisResult:
    """Run every engine over ``ds``. Pure and deterministic for a given ``seed``."""
    as_of = as_of or ds.as_of
    graph = analyze_graph(ds)
    forecasts = forecast_milestones(ds, as_of=as_of, trials=trials, seed=seed)
    ctx = Context(ds=ds, as_of=as_of, graph=graph, forecasts=forecasts)
    findings = evaluate_rules(ctx, rules or load_rules())
    return AnalysisResult(
        program=ds.program,
        as_of=as_of,
        health=_health(findings),
        stats=_stats(ds),
        forecasts=forecasts,
        graph=graph,
        findings=findings,
    )
