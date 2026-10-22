"""Helpers for building tiny datasets in tests (importable via pytest ``pythonpath``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pgmlens_core import (
    Dataset,
    Dependency,
    Event,
    EventType,
    Issue,
    Milestone,
    ProgramInfo,
    Project,
    Status,
)

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


def ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def make_issue(
    key: str,
    status: Status | str = Status.TODO,
    *,
    project: str = "p1",
    milestone: str | None = "m1",
    assignee: str | None = "Ana",
    estimate: float | None = 1,
    created: float = 60,
    updated: float = 1,
    resolved: float | None = None,
) -> Issue:
    status = Status(status)
    return Issue(
        id=key.lower(),
        project_id=project,
        key=key,
        title=f"Work item {key}",
        status=status,
        assignee=assignee,
        estimate=estimate,
        created_at=ago(created),
        updated_at=ago(resolved if status is Status.DONE and resolved is not None else updated),
        resolved_at=ago(resolved) if status is Status.DONE and resolved is not None else None,
        milestone_id=milestone,
    )


def make_dataset(
    issues: list[Issue],
    deps: list[tuple[str, str]] | None = None,
    *,
    milestones: list[Milestone] | None = None,
    events: list[Event] | None = None,
    projects: list[Project] | None = None,
) -> Dataset:
    return Dataset(
        program=ProgramInfo(id="t", name="Test program"),
        as_of=NOW,
        projects=projects
        or [Project(id="p1", key="P1", name="One"), Project(id="p2", key="P2", name="Two")],
        milestones=milestones
        if milestones is not None
        else [Milestone(id="m1", name="Milestone 1", due_date=(NOW + timedelta(days=30)).date())],
        issues=issues,
        dependencies=[
            Dependency(blocker_id=a.lower(), blocked_id=b.lower()) for a, b in (deps or [])
        ],
        events=events or [],
    )


def scope_event(issue_key: str, days_ago: float) -> Event:
    return Event(issue_id=issue_key.lower(), type=EventType.SCOPE_ADDED, at=ago(days_ago))


def steady_history(per_week: int = 3, weeks: int = 8) -> list[Issue]:
    """Done issues finishing at a constant rate, for deterministic forecasts."""
    done = []
    for week in range(weeks):
        for n in range(per_week):
            done.append(
                make_issue(
                    f"D{week}-{n}", Status.DONE, milestone=None, created=80, resolved=week * 7 + 3.5
                )
            )
    return done
