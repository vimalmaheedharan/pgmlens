"""Turn stored datasets and analyses into UI-shaped responses."""

from __future__ import annotations

from pgmlens_core import Severity

from .schemas import (
    EdgeOut,
    GraphView,
    IssueOut,
    MilestoneOut,
    ProgramDetail,
    ProgramSummary,
    ProjectOut,
)
from .store import StoredProgram


def summarize(stored: StoredProgram) -> ProgramSummary:
    ds, analysis = stored.dataset, stored.analysis
    due_soonest = sorted(
        (
            f
            for f in analysis.forecasts
            if f.scope_id is not None and f.due_date is not None and f.remaining > 0
        ),
        key=lambda f: f.due_date,  # type: ignore[arg-type,return-value]
    )
    rank = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
    top = sorted(analysis.findings, key=lambda f: rank[f.severity])[:3]
    return ProgramSummary(
        id=ds.program.id,
        name=ds.program.name,
        description=ds.program.description,
        as_of=analysis.as_of,
        health=analysis.health,
        stats=analysis.stats,
        next_milestone=due_soonest[0] if due_soonest else None,
        top_risks=top,
    )


def detail(stored: StoredProgram) -> ProgramDetail:
    ds, analysis = stored.dataset, stored.analysis
    graph = analysis.graph
    critical_ids = graph.critical_issue_ids

    critical_edges: set[tuple[str, str]] = set()
    for path in [graph.critical_path, *graph.milestone_paths.values()]:
        critical_edges.update(zip(path.issue_ids, path.issue_ids[1:], strict=False))

    waiting = {b.issue_id for b in graph.blocked}
    issues = [
        IssueOut(
            id=i.id,
            key=i.key,
            title=i.title,
            status=i.status.value,
            assignee=i.assignee,
            project_id=i.project_id,
            milestone_id=i.milestone_id,
            estimate=i.estimate,
            url=i.url,
            days_since_update=max(0, (analysis.as_of - i.updated_at).days),
            critical=i.id in critical_ids,
            waiting=i.id in waiting,
        )
        for i in ds.issues
    ]

    # Show every dependency that still constrains open work.
    edges: list[EdgeOut] = []
    nodes: set[str] = set()
    for dep in ds.dependencies:
        blocker, blocked = ds.issue_by_id[dep.blocker_id], ds.issue_by_id[dep.blocked_id]
        if not blocked.is_open:
            continue
        nodes.update((dep.blocker_id, dep.blocked_id))
        edges.append(
            EdgeOut(
                source=dep.blocker_id,
                target=dep.blocked_id,
                critical=(dep.blocker_id, dep.blocked_id) in critical_edges,
                unresolved=blocker.is_open,
            )
        )
    nodes.update(graph.critical_path.issue_ids)

    milestones = []
    for m in sorted(ds.milestones, key=lambda m: (m.due_date is None, m.due_date)):
        own = ds.issues_in_milestone(m.id)
        milestones.append(
            MilestoneOut(
                id=m.id,
                name=m.name,
                due_date=m.due_date,
                open_issues=sum(1 for i in own if i.is_open),
                total_issues=len(own),
            )
        )
    return ProgramDetail(
        summary=summarize(stored),
        analysis=analysis,
        issues=issues,
        milestones=milestones,
        projects=[ProjectOut(id=p.id, key=p.key, name=p.name) for p in ds.projects],
        graph=GraphView(
            nodes=sorted(nodes), edges=edges, critical_path=graph.critical_path.issue_ids
        ),
    )
