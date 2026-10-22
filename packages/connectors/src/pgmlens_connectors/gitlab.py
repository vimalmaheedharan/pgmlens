"""GitLab connector (gitlab.com and self-managed).

Maps GitLab's model onto PGM Lens like this:

* ``closed`` -> done; labels in ``blocked_labels`` -> blocked; labels in
  ``in_progress_labels`` -> in_progress; everything else -> todo
* project milestones (or group milestones) -> milestones, including ``start_date``
* issue ``weight`` (or time estimate, in 8-hour days) -> estimate
* issue links of type ``blocks`` / ``is_blocked_by`` -> dependencies
  (this GitLab feature requires a paid tier; a warning is recorded when it is unavailable)

GitLab's resource events are not fetched: they cost one request per issue, so status changes
come from ``created_at`` / ``closed_at`` instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Self

import httpx
from pgmlens_core import Dataset, Dependency, Issue, Milestone, ProgramInfo, Project, Status
from pydantic import BaseModel, Field, SecretStr

from .base import Connector, ConnectorError, HttpSession, utcnow


class GitLabConfig(BaseModel):
    base_url: str = "https://gitlab.com"
    token: SecretStr
    project_ids: list[int | str] = Field(
        default_factory=list,
        description="Numeric ids or URL-encoded paths, e.g. 'group%2Fproject'.",
    )
    group_id: int | str | None = Field(
        default=None, description="Fetch every project's issues in a group."
    )
    history_days: int = 90
    blocked_labels: list[str] = Field(
        default_factory=lambda: ["blocked", "status::blocked", "workflow::blocked"]
    )
    in_progress_labels: list[str] = Field(
        default_factory=lambda: [
            "doing", "in progress", "status::in progress", "workflow::in dev", "workflow::in review", "in review",
        ]
    )  # fmt: skip
    fetch_links: bool = True
    per_page: int = Field(default=100, ge=1, le=100)
    max_issues: int = 5000
    program_id: str = "gitlab"
    program_name: str = "GitLab program"


def _status(raw: dict[str, Any], cfg: GitLabConfig) -> Status:
    if raw.get("state") == "closed":
        return Status.DONE
    labels = {str(label).lower() for label in raw.get("labels") or []}
    if labels & {x.lower() for x in cfg.blocked_labels}:
        return Status.BLOCKED
    if labels & {x.lower() for x in cfg.in_progress_labels}:
        return Status.IN_PROGRESS
    return Status.TODO


def _estimate(raw: dict[str, Any]) -> float | None:
    if raw.get("weight") is not None:
        return float(raw["weight"])
    seconds = (raw.get("time_stats") or {}).get("time_estimate") or 0
    return round(seconds / 28800, 2) if seconds else None  # 8-hour working day


def _issue_id(project_id: int | str, iid: int | str) -> str:
    return f"gl-{project_id}-{iid}"


class GitLabConnector(Connector):
    name = "gitlab"

    def __init__(
        self,
        config: GitLabConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        session: HttpSession | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        if session is not None:
            self.http = session
        else:
            headers = {
                "PRIVATE-TOKEN": config.token.get_secret_value(),
                "Accept": "application/json",
            }
            self.http = HttpSession(httpx.Client(headers=headers, timeout=30, transport=transport))
        self.api = f"{self.base_url}/api/v4"

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Self:
        return cls(GitLabConfig.model_validate(config))

    # ---- fetching -------------------------------------------------------------------------

    def _paged(self, url: str, params: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page: str | None = "1"
        while page and len(items) < limit:
            response = self.http.get(
                url, params={**params, "page": page, "per_page": self.config.per_page}
            )
            assert response is not None
            items.extend(response.json())
            page = response.headers.get("x-next-page") or None
        return items[:limit]

    def _issue_sources(self) -> list[str]:
        cfg = self.config
        if cfg.group_id is not None:
            return [f"{self.api}/groups/{cfg.group_id}/issues"]
        if not cfg.project_ids:
            raise ConnectorError("Set project_ids or group_id for the GitLab connector.")
        return [f"{self.api}/projects/{pid}/issues" for pid in cfg.project_ids]

    def fetch(self, *, as_of: datetime | None = None) -> Dataset:
        cfg = self.config
        as_of = as_of or utcnow()
        since = (as_of - timedelta(days=cfg.history_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw: dict[str, dict[str, Any]] = {}
        for url in self._issue_sources():
            base = {"scope": "all", "order_by": "created_at", "sort": "asc"}
            for params in (
                {**base, "state": "opened"},
                {**base, "state": "closed", "updated_after": since},
            ):
                for item in self._paged(url, params, cfg.max_issues):
                    raw[_issue_id(item["project_id"], item["iid"])] = item
        if len(raw) >= cfg.max_issues:
            self.warnings.append(f"Stopped at max_issues={cfg.max_issues}; results are truncated.")

        project_names: dict[int, dict[str, Any]] = {}
        for project_id in sorted({item["project_id"] for item in raw.values()}):
            project_names[project_id] = self.http.get_json(f"{self.api}/projects/{project_id}")

        links = self._links(raw) if cfg.fetch_links else []
        return map_issues(raw, project_names, links, cfg, as_of=as_of)

    def _links(self, raw: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
        """Blocking relationships for open issues, as (blocker_id, blocked_id)."""
        edges: set[tuple[str, str]] = set()
        for issue_id, item in raw.items():
            if item.get("state") != "opened":
                continue
            data = self.http.get_json(
                f"{self.api}/projects/{item['project_id']}/issues/{item['iid']}/links",
                tolerate=(403, 404),
            )
            if data is None:
                self.warnings.append(
                    "Issue links are unavailable (they need a paid GitLab tier); dependencies were skipped."
                )
                return []
            for link in data:
                other = _issue_id(link["project_id"], link["iid"])
                if link.get("link_type") == "blocks":
                    edges.add((issue_id, other))
                elif link.get("link_type") == "is_blocked_by":
                    edges.add((other, issue_id))
        return sorted(edges)


def map_issues(
    raw: dict[str, dict[str, Any]],
    projects_raw: dict[int, dict[str, Any]],
    links: list[tuple[str, str]],
    cfg: GitLabConfig,
    *,
    as_of: datetime,
) -> Dataset:
    """Pure mapping from GitLab's JSON to the normalized dataset (unit-tested without HTTP)."""
    projects = {
        pid: Project(
            id=f"gl-{pid}",
            key=p.get("path_with_namespace") or str(pid),
            name=p.get("name") or str(pid),
        )
        for pid, p in projects_raw.items()
    }
    milestones: dict[str, Milestone] = {}
    issues: list[Issue] = []
    for issue_id, item in raw.items():
        project = projects[item["project_id"]]
        ms = item.get("milestone")
        milestone_id = None
        if ms:
            milestone_id = f"gl-m{ms['id']}"
            milestones.setdefault(
                milestone_id,
                Milestone(
                    id=milestone_id,
                    name=ms["title"],
                    start_date=ms.get("start_date"),
                    due_date=ms.get("due_date"),
                ),
            )
        status = _status(item, cfg)
        assignees = item.get("assignees") or ([item["assignee"]] if item.get("assignee") else [])
        issues.append(
            Issue(
                id=issue_id,
                project_id=project.id,
                key=f"{project.key}#{item['iid']}",
                title=item["title"],
                status=status,
                assignee=assignees[0].get("name") if assignees else None,
                estimate=_estimate(item),
                created_at=item["created_at"],
                updated_at=item["updated_at"],
                resolved_at=item.get("closed_at") if status is Status.DONE else None,
                milestone_id=milestone_id,
                labels=[str(label) for label in item.get("labels") or []],
                url=item.get("web_url"),
                due_date=item.get("due_date"),
            )
        )
    known = {i.id for i in issues}
    return Dataset(
        program=ProgramInfo(id=cfg.program_id, name=cfg.program_name),
        as_of=as_of,
        projects=list(projects.values()),
        milestones=list(milestones.values()),
        issues=issues,
        dependencies=[
            Dependency(blocker_id=a, blocked_id=b) for a, b in links if a in known and b in known
        ],
    )
