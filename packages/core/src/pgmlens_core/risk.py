"""Declarative risk engine.

Rules live in YAML (see ``rules/default.yaml``). Each rule names a built-in *evaluator*
(``type``), a severity, human-facing copy and tunable ``params``. Evaluators are plain
Python functions registered with :func:`evaluator`; adding a new kind of check means
adding one function, and tuning thresholds never needs code.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .dates import short_date
from .forecast import ForecastResult
from .graph import GraphAnalysis
from .models import Dataset, Issue, Status


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}


class RuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    severity: Severity = Severity.MEDIUM
    enabled: bool = True
    title: str
    action: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    extends: Literal["default"] | None = None
    rules: list[RuleSpec] = Field(default_factory=list)


class Finding(BaseModel):
    id: str
    rule_id: str
    rule_type: str
    title: str
    severity: Severity
    message: str
    action: str
    issue_ids: list[str] = Field(default_factory=list)
    issue_keys: list[str] = Field(default_factory=list)
    milestone_ids: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


@dataclass
class Context:
    ds: Dataset
    as_of: datetime
    graph: GraphAnalysis
    forecasts: list[ForecastResult]

    def key(self, issue_id: str) -> str:
        return self.ds.issue_by_id[issue_id].key

    def age_days(self, issue: Issue) -> int:
        return max(0, (self.as_of - issue.updated_at).days)

    def milestone_name(self, milestone_id: str | None) -> str:
        if milestone_id is None:
            return "no milestone"
        return self.ds.milestone_by_id[milestone_id].name


@dataclass
class RawFinding:
    subject: str
    message: str
    issue_ids: list[str] = field(default_factory=list)
    milestone_ids: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    severity: Severity | None = None


Evaluator = Callable[[Context, dict[str, Any]], list[RawFinding]]
EVALUATORS: dict[str, Evaluator] = {}


def evaluator(name: str) -> Callable[[Evaluator], Evaluator]:
    def register(fn: Evaluator) -> Evaluator:
        EVALUATORS[name] = fn
        return fn

    return register


def _keys(ctx: Context, ids: list[str], limit: int = 5) -> str:
    shown = ", ".join(ctx.key(i) for i in ids[:limit])
    return shown + (f" and {len(ids) - limit} more" if len(ids) > limit else "")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


# --------------------------------------------------------------------------- evaluators


@evaluator("stale_blocker")
def _stale_blocker(ctx: Context, p: dict[str, Any]) -> list[RawFinding]:
    stale_days = int(p.get("stale_days", 10))
    held: dict[str, list[str]] = {}
    for dep in ctx.ds.dependencies:
        blocker, blocked = ctx.ds.issue_by_id[dep.blocker_id], ctx.ds.issue_by_id[dep.blocked_id]
        if blocker.is_open and blocked.is_open:
            held.setdefault(blocker.id, []).append(blocked.id)
    out = []
    for blocker_id, blocked_ids in sorted(held.items()):
        blocker = ctx.ds.issue_by_id[blocker_id]
        age = ctx.age_days(blocker)
        if age < stale_days:
            continue
        owner = f"owned by {blocker.assignee}" if blocker.assignee else "with no owner"
        out.append(
            RawFinding(
                subject=blocker.key,
                message=(
                    f'{blocker.key} "{blocker.title}" ({owner}) has not been updated for {age} days '
                    f"and is holding up {_plural(len(blocked_ids), 'open issue')}: "
                    f"{_keys(ctx, blocked_ids)}."
                ),
                issue_ids=[blocker_id, *blocked_ids],
                metrics={
                    "days_stale": age,
                    "blocked_count": len(blocked_ids),
                    "assignee": blocker.assignee,
                },
            )
        )
    return out


@evaluator("milestone_slip")
def _milestone_slip(ctx: Context, p: dict[str, Any]) -> list[RawFinding]:
    slack = int(p.get("p80_slip_days", 0))
    critical_below = float(p.get("critical_below", 0.2))
    today = ctx.as_of.date()
    out = []
    for fc in ctx.forecasts:
        if fc.scope_id is None or fc.due_date is None:
            continue
        milestone = ctx.ds.milestone_by_id[fc.scope_id]
        own_open = [i for i in ctx.ds.issues_in_milestone(milestone.id) if i.is_open]
        if not own_open:
            continue
        ids = [i.id for i in own_open]
        if fc.due_date < today:
            late = (today - fc.due_date).days
            out.append(
                RawFinding(
                    subject=milestone.id,
                    message=(
                        f"{milestone.name} was due {short_date(fc.due_date)} ({late} days ago) and still has "
                        f"{_plural(len(own_open), 'open issue')}."
                    ),
                    issue_ids=ids, milestone_ids=[milestone.id], severity=Severity.CRITICAL,
                    metrics={"days_overdue": late, "open_issues": len(own_open)},
                )
            )  # fmt: skip
        elif fc.status == "not_converging":
            out.append(
                RawFinding(
                    subject=milestone.id,
                    message=(
                        f"{milestone.name}: new work is arriving about as fast as it is finished, so no "
                        f"realistic finish date exists for the {short_date(fc.due_date)} deadline."
                    ),
                    issue_ids=ids, milestone_ids=[milestone.id], severity=Severity.CRITICAL,
                    metrics={"throughput": fc.mean_weekly_throughput, "scope_growth": fc.mean_weekly_scope_growth},
                )
            )  # fmt: skip
        elif fc.status == "ok" and fc.p80_date and (fc.p80_date - fc.due_date).days > slack:
            prob = fc.on_time_probability if fc.on_time_probability is not None else 0.0
            slip = (fc.p80_date - fc.due_date).days
            out.append(
                RawFinding(
                    subject=milestone.id,
                    message=(
                        f"{milestone.name} has a {prob:.0%} chance of landing by {short_date(fc.due_date)}. "
                        f"Most likely {short_date(fc.p50_date)}; 80% sure by {short_date(fc.p80_date)} "
                        f"({slip} days late). {_plural(fc.remaining, 'issue')} remain in scope at "
                        f"~{fc.mean_weekly_throughput:g} finished per week."
                    ),
                    issue_ids=ids, milestone_ids=[milestone.id],
                    severity=Severity.CRITICAL if prob < critical_below else None,
                    metrics={
                        "on_time_probability": prob, "p50": str(fc.p50_date), "p80": str(fc.p80_date),
                        "slip_days_p80": slip, "remaining": fc.remaining,
                    },
                )
            )  # fmt: skip
    return out


@evaluator("scope_creep")
def _scope_creep(ctx: Context, p: dict[str, Any]) -> list[RawFinding]:
    window = int(p.get("window_days", 14))
    threshold = float(p.get("threshold_pct", 0.15))
    min_added = int(p.get("min_added", 3))
    cutoff = ctx.as_of - timedelta(days=window)
    out = []
    for milestone in ctx.ds.milestones:
        issues = ctx.ds.issues_in_milestone(milestone.id)
        if not any(i.is_open for i in issues):
            continue
        in_ms = {i.id for i in issues}
        added = {i.id for i in issues if i.created_at >= cutoff}
        added |= {
            e.issue_id for e in ctx.ds.events
            if e.type == "scope_added" and e.at >= cutoff and e.issue_id in in_ms
        }  # fmt: skip
        share = len(added) / len(issues)
        if len(added) >= min_added and share >= threshold:
            ids = sorted(added)
            out.append(
                RawFinding(
                    subject=milestone.id,
                    message=(
                        f"{_plural(len(added), 'issue')} ({share:.0%} of {milestone.name}) were added in the "
                        f"last {window} days: {_keys(ctx, ids)}."
                    ),
                    issue_ids=ids, milestone_ids=[milestone.id],
                    metrics={"added": len(added), "share": round(share, 3), "window_days": window},
                )
            )  # fmt: skip
    return out


@evaluator("overloaded_owner")
def _overloaded_owner(ctx: Context, p: dict[str, Any]) -> list[RawFinding]:
    max_wip = int(p.get("max_in_progress", 4))
    max_open = int(p.get("max_open", 12))
    by_owner: dict[str, list[Issue]] = {}
    for issue in ctx.ds.issues:
        if issue.is_open and issue.assignee:
            by_owner.setdefault(issue.assignee, []).append(issue)
    out = []
    for owner, issues in sorted(by_owner.items()):
        wip = [i for i in issues if i.status is Status.IN_PROGRESS]
        if len(wip) > max_wip or len(issues) > max_open:
            out.append(
                RawFinding(
                    subject=owner,
                    message=(
                        f"{owner} has {len(wip)} items in progress and {len(issues)} open issues "
                        f"(limits: {max_wip} in progress, {max_open} open)."
                    ),
                    issue_ids=[i.id for i in wip] or [i.id for i in issues[:max_wip]],
                    metrics={"in_progress": len(wip), "open": len(issues), "assignee": owner},
                )
            )
    return out


@evaluator("silent_in_progress")
def _silent_in_progress(ctx: Context, p: dict[str, Any]) -> list[RawFinding]:
    stale_days = int(p.get("stale_days", 10))
    out = []
    for issue in ctx.ds.issues:
        if issue.status is Status.IN_PROGRESS and ctx.age_days(issue) >= stale_days:
            age = ctx.age_days(issue)
            who = issue.assignee or "nobody"
            out.append(
                RawFinding(
                    subject=issue.key,
                    message=f'{issue.key} "{issue.title}" has been in progress for {age} days with no update (assignee: {who}).',
                    issue_ids=[issue.id],
                    milestone_ids=[issue.milestone_id] if issue.milestone_id else [],
                    metrics={"days_silent": age, "assignee": issue.assignee},
                )
            )
    return out


@evaluator("unassigned_critical")
def _unassigned_critical(ctx: Context, p: dict[str, Any]) -> list[RawFinding]:
    out = []
    for issue_id in sorted(ctx.graph.critical_issue_ids):
        issue = ctx.ds.issue_by_id[issue_id]
        if issue.is_open and not issue.assignee:
            out.append(
                RawFinding(
                    subject=issue.key,
                    message=(
                        f'{issue.key} "{issue.title}" is on the critical path '
                        f"({ctx.milestone_name(issue.milestone_id)}) but has no owner."
                    ),
                    issue_ids=[issue.id],
                    milestone_ids=[issue.milestone_id] if issue.milestone_id else [],
                    metrics={"status": issue.status.value},
                )
            )
    return out


@evaluator("dependency_cycle")
def _dependency_cycle(ctx: Context, p: dict[str, Any]) -> list[RawFinding]:
    out = []
    for cycle in ctx.graph.cycles:
        keys = [ctx.key(i) for i in cycle]
        out.append(
            RawFinding(
                subject="-".join(sorted(keys)),
                message=f"Circular dependency: {' -> '.join([*keys, keys[0]])}. None of these can start.",
                issue_ids=list(cycle),
                metrics={"length": len(cycle)},
            )
        )
    return out


@evaluator("blocked_chain")
def _blocked_chain(ctx: Context, p: dict[str, Any]) -> list[RawFinding]:
    min_depth = int(p.get("min_depth", 3))
    out = []
    for root in ctx.graph.root_blockers:
        if root.max_depth < min_depth:
            continue
        downstream = sorted(
            b.issue_id for b in ctx.graph.blocked if root.issue_id in b.root_blocker_ids
        )
        issue = ctx.ds.issue_by_id[root.issue_id]
        out.append(
            RawFinding(
                subject=issue.key,
                message=(
                    f'{issue.key} "{issue.title}" sits at the root of a {root.max_depth}-step dependency '
                    f"chain that is holding up {_plural(root.downstream_count, 'issue')}."
                ),
                issue_ids=[issue.id, *downstream],
                metrics={"chain_depth": root.max_depth, "downstream": root.downstream_count},
            )
        )
    return out


@evaluator("cross_project_coupling")
def _cross_project_coupling(ctx: Context, p: dict[str, Any]) -> list[RawFinding]:
    min_unresolved = int(p.get("min_unresolved", 4))
    out = []
    for link in ctx.graph.coupling:
        if link.unresolved < min_unresolved:
            continue
        src = ctx.ds.project_by_id[link.blocker_project_id]
        dst = ctx.ds.project_by_id[link.blocked_project_id]
        ids: set[str] = set()
        for dep in ctx.ds.dependencies:
            a, b = ctx.ds.issue_by_id[dep.blocker_id], ctx.ds.issue_by_id[dep.blocked_id]
            if a.project_id == src.id and b.project_id == dst.id and a.is_open and b.is_open:
                ids.update((a.id, b.id))
        out.append(
            RawFinding(
                subject=f"{src.key}-{dst.key}",
                message=(
                    f"{dst.name} depends on {src.name} for {link.unresolved} unresolved items. "
                    "Heavy cross-team coupling makes dates fragile."
                ),
                issue_ids=sorted(ids),
                metrics={"unresolved": link.unresolved, "edges": link.edges},
            )
        )
    return out


# --------------------------------------------------------------------------- loading


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def default_rules_text() -> str:
    return resources.files("pgmlens_core").joinpath("rules/default.yaml").read_text("utf-8")


def parse_rules(text: str) -> RuleSet:
    ruleset = RuleSet.model_validate(yaml.safe_load(text) or {})
    if ruleset.extends == "default":
        base = RuleSet.model_validate(yaml.safe_load(default_rules_text()))
        merged = {r.id: r for r in base.rules}
        merged.update({r.id: r for r in ruleset.rules})
        ruleset = RuleSet(version=ruleset.version, rules=list(merged.values()))
    unknown = sorted({r.type for r in ruleset.rules} - set(EVALUATORS))
    if unknown:
        raise ValueError(f"Unknown rule type(s) {unknown}. Available: {sorted(EVALUATORS)}")
    ids = [r.id for r in ruleset.rules]
    if len(ids) != len(set(ids)):
        raise ValueError("Rule ids must be unique")
    return ruleset


def load_rules(path: str | Path | None = None) -> RuleSet:
    """Load the default rules, or a custom file (which may ``extends: default``)."""
    if path is None:
        return parse_rules(default_rules_text())
    return parse_rules(Path(path).read_text("utf-8"))


def evaluate_rules(ctx: Context, rules: RuleSet) -> list[Finding]:
    findings: list[Finding] = []
    for rule in rules.rules:
        if not rule.enabled:
            continue
        for raw in EVALUATORS[rule.type](ctx, rule.params):
            findings.append(
                Finding(
                    id=f"{rule.id}:{_slug(raw.subject)}",
                    rule_id=rule.id,
                    rule_type=rule.type,
                    title=rule.title,
                    severity=raw.severity or rule.severity,
                    message=raw.message,
                    action=rule.action,
                    issue_ids=raw.issue_ids,
                    issue_keys=[ctx.key(i) for i in raw.issue_ids],
                    milestone_ids=raw.milestone_ids,
                    metrics=raw.metrics,
                )
            )
    findings.sort(key=lambda f: (-SEVERITY_RANK[f.severity], -len(f.issue_ids), f.id))
    return findings
