"""Normalized program data model.

This schema is the contract between connectors (which produce it) and engines
(which consume it). It is versioned via ``SCHEMA_VERSION``; breaking changes bump it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from functools import cached_property
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1"


def _to_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC and normalize everything to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


UTCDateTime = Annotated[datetime, AfterValidator(_to_utc)]


class Status(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class EventType(StrEnum):
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    SCOPE_ADDED = "scope_added"
    ESTIMATE_CHANGED = "estimate_changed"
    MILESTONE_CHANGED = "milestone_changed"
    COMMENT = "comment"


class _Model(BaseModel):
    # Typos in hand-written datasets should fail loudly rather than be silently dropped.
    model_config = ConfigDict(extra="forbid")


class ProgramInfo(_Model):
    id: str
    name: str
    description: str = ""


class Project(_Model):
    id: str
    key: str
    name: str
    owner: str | None = None


class Milestone(_Model):
    id: str
    name: str
    due_date: date | None = None
    start_date: date | None = None
    project_id: str | None = Field(
        default=None,
        description="Set when the milestone belongs to one project; null if program-wide.",
    )


class Issue(_Model):
    id: str
    project_id: str
    key: str = Field(description="Human-facing key, e.g. PLAT-123.")
    title: str
    status: Status
    assignee: str | None = None
    estimate: float | None = Field(
        default=None, ge=0, description="Story points or similar; optional."
    )
    created_at: UTCDateTime
    updated_at: UTCDateTime
    resolved_at: UTCDateTime | None = None
    milestone_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    url: str | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def _fill_resolved(self) -> Issue:
        if self.status is Status.DONE and self.resolved_at is None:
            self.resolved_at = self.updated_at
        if self.updated_at < self.created_at:
            raise ValueError(f"{self.key}: updated_at is earlier than created_at")
        return self

    @property
    def is_open(self) -> bool:
        return self.status is not Status.DONE


class Dependency(_Model):
    """``blocker_id`` must finish before ``blocked_id`` can."""

    blocker_id: str
    blocked_id: str


class Event(_Model):
    id: str | None = None
    issue_id: str
    type: EventType
    at: UTCDateTime
    actor: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class Dataset(_Model):
    schema_version: str = SCHEMA_VERSION
    program: ProgramInfo
    as_of: UTCDateTime
    projects: list[Project] = Field(default_factory=list)
    milestones: list[Milestone] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_integrity(self) -> Dataset:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version {self.schema_version!r}; this build reads {SCHEMA_VERSION!r}."
            )
        for label, ids in (
            ("project", [p.id for p in self.projects]),
            ("milestone", [m.id for m in self.milestones]),
            ("issue", [i.id for i in self.issues]),
        ):
            dupes = {x for x in ids if ids.count(x) > 1}
            if dupes:
                raise ValueError(f"Duplicate {label} ids: {sorted(dupes)}")

        project_ids = {p.id for p in self.projects}
        milestone_ids = {m.id for m in self.milestones}
        issue_ids = {i.id for i in self.issues}
        for issue in self.issues:
            if issue.project_id not in project_ids:
                raise ValueError(f"{issue.key}: unknown project_id {issue.project_id!r}")
            if issue.milestone_id is not None and issue.milestone_id not in milestone_ids:
                raise ValueError(f"{issue.key}: unknown milestone_id {issue.milestone_id!r}")
        for dep in self.dependencies:
            if dep.blocker_id not in issue_ids or dep.blocked_id not in issue_ids:
                raise ValueError(
                    f"Dependency references unknown issue: {dep.blocker_id} -> {dep.blocked_id}"
                )
            if dep.blocker_id == dep.blocked_id:
                raise ValueError(f"Issue {dep.blocker_id} cannot block itself")
        for event in self.events:
            if event.issue_id not in issue_ids:
                raise ValueError(f"Event references unknown issue {event.issue_id!r}")
        return self

    # Datasets are treated as immutable after validation, so caching lookups is safe.
    @cached_property
    def issue_by_id(self) -> dict[str, Issue]:
        return {i.id: i for i in self.issues}

    @cached_property
    def milestone_by_id(self) -> dict[str, Milestone]:
        return {m.id: m for m in self.milestones}

    @cached_property
    def project_by_id(self) -> dict[str, Project]:
        return {p.id: p for p in self.projects}

    def issues_in_milestone(self, milestone_id: str) -> list[Issue]:
        return [i for i in self.issues if i.milestone_id == milestone_id]
