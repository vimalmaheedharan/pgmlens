"""Jira connector (Cloud and Data Center / Server).

Maps Jira's model onto PGM Lens like this:

* status category ``new``/``indeterminate``/``done`` -> todo / in_progress / done;
  statuses or labels matching ``blocked_markers`` -> blocked
* ``fixVersions`` -> milestones (due date = release date)
* "Blocks" issue links -> dependencies
* changelog entries -> events (status, assignee, fix version, estimate changes)

Jira has no notion of when a version "started", so a milestone's ``start_date`` is
approximated by the creation date of its earliest issue; the forecast engine uses that to
tell planned work from work added later.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Literal, Self

import httpx
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
from pydantic import BaseModel, Field, SecretStr

from .base import Connector, ConnectorError, HttpSession, utcnow


class JiraConfig(BaseModel):
    base_url: str = Field(description="e.g. https://your-domain.atlassian.net")
    api_token: SecretStr
    email: str | None = Field(
        default=None,
        description="Set for Jira Cloud (basic auth). Omit for a Data Center bearer PAT.",
    )
    flavor: Literal["cloud", "server"] = "cloud"
    project_keys: list[str] = Field(default_factory=list)
    jql: str | None = Field(default=None, description="Overrides the generated query entirely.")
    history_days: int = Field(default=90, description="How far back to look for resolved issues.")
    story_points_field: str = "customfield_10016"
    blocked_markers: list[str] = Field(default_factory=lambda: ["blocked", "on hold", "impediment"])
    blocking_link_types: list[str] = Field(default_factory=lambda: ["Blocks"])
    page_size: int = Field(default=100, ge=1, le=100)
    max_issues: int = 5000
    program_id: str = "jira"
    program_name: str = "Jira program"


def default_jql(cfg: JiraConfig) -> str:
    if cfg.jql:
        return cfg.jql
    if not cfg.project_keys:
        raise ConnectorError("Set project_keys or jql for the Jira connector.")
    keys = ", ".join(f'"{k}"' for k in cfg.project_keys)
    return (
        f"project in ({keys}) AND (resolution = Unresolved OR resolved >= -{cfg.history_days}d) "
        "ORDER BY created ASC"
    )


def _status(fields: dict[str, Any], cfg: JiraConfig) -> Status:
    category = ((fields.get("status") or {}).get("statusCategory") or {}).get("key", "new")
    if category == "done":
        return Status.DONE
    name = ((fields.get("status") or {}).get("name") or "").lower()
    labels = [str(label).lower() for label in fields.get("labels") or []]
    if any(marker in name or marker in labels for marker in cfg.blocked_markers):
        return Status.BLOCKED
    return Status.IN_PROGRESS if category == "indeterminate" else Status.TODO


def _milestone(fields: dict[str, Any]) -> dict[str, Any] | None:
    versions = fields.get("fixVersions") or []
    if not versions:
        return None
    dated = [v for v in versions if v.get("releaseDate")]
    return min(dated, key=lambda v: v["releaseDate"]) if dated else versions[0]


def _events(raw: dict[str, Any], issue_id: str) -> list[Event]:
    mapping = {
        "status": EventType.STATUS_CHANGED,
        "assignee": EventType.ASSIGNED,
        "Fix Version": EventType.MILESTONE_CHANGED,
        "Story Points": EventType.ESTIMATE_CHANGED,
        "Story point estimate": EventType.ESTIMATE_CHANGED,
    }
    events: list[Event] = []
    for history in (raw.get("changelog") or {}).get("histories", []):
        for item in history.get("items", []):
            kind = mapping.get(item.get("field", ""))
            if kind is None:
                continue
            events.append(
                Event(
                    issue_id=issue_id,
                    type=kind,
                    at=history["created"],
                    actor=(history.get("author") or {}).get("displayName"),
                    data={"from": item.get("fromString"), "to": item.get("toString")},
                )
            )
    return events


class JiraConnector(Connector):
    name = "jira"

    def __init__(
        self,
        config: JiraConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        session: HttpSession | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        base = config.base_url.rstrip("/")
        token = config.api_token.get_secret_value()
        if session is not None:
            self.http = session
        else:
            auth = httpx.BasicAuth(config.email, token) if config.email else None
            headers = {"Accept": "application/json"}
            if not config.email:
                headers["Authorization"] = f"Bearer {token}"
            self.http = HttpSession(
                httpx.Client(
                    base_url=base, auth=auth, headers=headers, timeout=30, transport=transport
                )
            )
        self.base_url = base

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Self:
        return cls(JiraConfig.model_validate(config))

    # ---- fetching -------------------------------------------------------------------------

    def _search(self) -> list[dict[str, Any]]:
        cfg = self.config
        fields = [
            "summary", "status", "assignee", "created", "updated", "resolutiondate", "fixVersions",
            "labels", "issuelinks", "duedate", "project", cfg.story_points_field,
        ]  # fmt: skip
        params: dict[str, Any] = {
            "jql": default_jql(cfg),
            "fields": ",".join(fields),
            "expand": "changelog",
            "maxResults": cfg.page_size,
        }
        issues: list[dict[str, Any]] = []
        token: str | None = None
        start = 0
        while len(issues) < cfg.max_issues:
            if cfg.flavor == "cloud":
                path = "/rest/api/3/search/jql"
                if token:
                    params["nextPageToken"] = token
            else:
                path = "/rest/api/2/search"
                params["startAt"] = start
            page = self.http.get_json(f"{self.base_url}{path}", params=params)
            batch = page.get("issues", [])
            issues.extend(batch)
            if cfg.flavor == "cloud":
                token = page.get("nextPageToken")
                if page.get("isLast", True) or not token or not batch:
                    break
            else:
                start += len(batch)
                if not batch or start >= page.get("total", 0):
                    break
        if len(issues) >= cfg.max_issues:
            self.warnings.append(f"Stopped at max_issues={cfg.max_issues}; results are truncated.")
        return issues[: cfg.max_issues]

    def fetch(self, *, as_of: datetime | None = None) -> Dataset:
        raw_issues = self._search()
        return map_issues(raw_issues, self.config, self.base_url, as_of=as_of or utcnow())


def map_issues(
    raw_issues: list[dict[str, Any]], cfg: JiraConfig, base_url: str, *, as_of: datetime
) -> Dataset:
    """Pure mapping from Jira's JSON to the normalized dataset (unit-tested without HTTP)."""
    projects: dict[str, Project] = {}
    milestones: dict[str, Milestone] = {}
    issues: list[Issue] = []
    events: list[Event] = []
    edges: set[tuple[str, str]] = set()
    created_by_milestone: dict[str, list[datetime]] = defaultdict(list)

    def issue_id(key: str) -> str:
        return f"jira-{key.lower()}"

    for raw in raw_issues:
        key = raw["key"]
        f = raw["fields"]
        proj = f["project"]
        projects.setdefault(
            proj["key"],
            Project(id=proj["key"].lower(), key=proj["key"], name=proj.get("name") or proj["key"]),
        )
        version = _milestone(f)
        milestone_id = None
        if version:
            milestone_id = f"jira-v{version['id']}"
            milestones.setdefault(
                milestone_id,
                Milestone(
                    id=milestone_id, name=version["name"], due_date=version.get("releaseDate")
                ),
            )
        points = f.get(cfg.story_points_field)
        status = _status(f, cfg)
        issue = Issue(
            id=issue_id(key),
            project_id=proj["key"].lower(),
            key=key,
            title=f.get("summary") or key,
            status=status,
            assignee=(f.get("assignee") or {}).get("displayName"),
            estimate=float(points) if isinstance(points, int | float) else None,
            created_at=f["created"],
            updated_at=f["updated"],
            resolved_at=f.get("resolutiondate") if status is Status.DONE else None,
            milestone_id=milestone_id,
            labels=[str(label) for label in f.get("labels") or []],
            url=f"{base_url}/browse/{key}",
            due_date=f.get("duedate"),
        )
        issues.append(issue)
        if milestone_id:
            created_by_milestone[milestone_id].append(issue.created_at)
        events.extend(_events(raw, issue.id))
        for link in f.get("issuelinks") or []:
            if (link.get("type") or {}).get("name") not in cfg.blocking_link_types:
                continue
            if "outwardIssue" in link:  # this issue blocks the other one
                edges.add((issue_id(key), issue_id(link["outwardIssue"]["key"])))
            elif "inwardIssue" in link:  # the other issue blocks this one
                edges.add((issue_id(link["inwardIssue"]["key"]), issue_id(key)))

    for milestone_id, stamps in created_by_milestone.items():
        milestones[milestone_id].start_date = min(stamps).date()

    known = {i.id for i in issues}
    return Dataset(
        program=ProgramInfo(id=cfg.program_id, name=cfg.program_name),
        as_of=as_of,
        projects=list(projects.values()),
        milestones=list(milestones.values()),
        issues=issues,
        dependencies=[
            Dependency(blocker_id=a, blocked_id=b)
            for a, b in sorted(edges)
            if a in known and b in known
        ],
        events=events,
    )


__all__ = ["JiraConfig", "JiraConnector", "default_jql", "map_issues"]
