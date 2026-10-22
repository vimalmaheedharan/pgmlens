"""GitHub connector (github.com and GitHub Enterprise Server).

Maps GitHub's model onto PGM Lens like this:

* pull requests are skipped (the issues endpoint returns them too)
* ``closed`` -> done; labels in ``blocked_labels`` -> blocked; labels in
  ``in_progress_labels`` -> in_progress; everything else -> todo
* milestones -> milestones (GitHub has no start date, so the milestone's creation date is used)
* estimate: a label such as ``size:3`` or ``points: 5`` (see ``estimate_label_pattern``)
* issue dependencies ("blocked by" / "blocking") -> dependencies. Where the API is unavailable
  (older Enterprise Server versions) a warning is recorded and dependencies are skipped.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Self

import httpx
from pgmlens_core import Dataset, Dependency, Issue, Milestone, ProgramInfo, Project, Status
from pydantic import BaseModel, Field, SecretStr

from .base import Connector, ConnectorError, HttpSession, utcnow


class GitHubConfig(BaseModel):
    base_url: str = "https://api.github.com"
    token: SecretStr
    repos: list[str] = Field(
        default_factory=list, description="Repositories as 'owner/name', e.g. 'acme/app'."
    )
    history_days: int = 90
    blocked_labels: list[str] = Field(default_factory=lambda: ["blocked", "status: blocked"])
    in_progress_labels: list[str] = Field(
        default_factory=lambda: ["in progress", "status: in progress", "in review"]
    )
    estimate_label_pattern: str = r"^(?:size|points?|estimate)\s*[:/ ]\s*(\d+(?:\.\d+)?)$"
    fetch_dependencies: bool = True
    per_page: int = Field(default=100, ge=1, le=100)
    max_issues: int = 5000
    program_id: str = "github"
    program_name: str = "GitHub program"


def _status(raw: dict[str, Any], cfg: GitHubConfig) -> Status:
    if raw.get("state") == "closed":
        return Status.DONE
    labels = _labels(raw)
    if {x.lower() for x in labels} & {x.lower() for x in cfg.blocked_labels}:
        return Status.BLOCKED
    if {x.lower() for x in labels} & {x.lower() for x in cfg.in_progress_labels}:
        return Status.IN_PROGRESS
    return Status.TODO


def _labels(raw: dict[str, Any]) -> list[str]:
    return [
        (x.get("name") if isinstance(x, dict) else str(x)) or "" for x in raw.get("labels") or []
    ]


def _estimate(raw: dict[str, Any], pattern: re.Pattern[str]) -> float | None:
    for label in _labels(raw):
        match = pattern.match(label.strip())
        if match:
            return float(match.group(1))
    return None


def _repo_of(raw: dict[str, Any], default: str) -> str:
    """'owner/name' for an issue payload (dependency payloads can come from other repos)."""
    url = raw.get("repository_url") or ""
    parts = url.rstrip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 and "/repos/" in url else default


def _issue_id(repo: str, number: int | str) -> str:
    return f"gh-{repo}#{number}"


class GitHubConnector(Connector):
    name = "github"

    def __init__(
        self,
        config: GitHubConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        session: HttpSession | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.api = config.base_url.rstrip("/")
        if session is not None:
            self.http = session
        else:
            headers = {
                "Authorization": f"Bearer {config.token.get_secret_value()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            self.http = HttpSession(httpx.Client(headers=headers, timeout=30, transport=transport))

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Self:
        return cls(GitHubConfig.model_validate(config))

    def _paged(self, url: str, params: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_url: str | None = url
        next_params: dict[str, Any] | None = {**params, "per_page": self.config.per_page}
        while next_url and len(items) < limit:
            response = self.http.get(next_url, params=next_params)
            assert response is not None
            items.extend(response.json())
            next_url = (response.links.get("next") or {}).get("url")
            next_params = None  # the next link already carries the query string
        return items[:limit]

    def fetch(self, *, as_of: datetime | None = None) -> Dataset:
        cfg = self.config
        if not cfg.repos:
            raise ConnectorError("Set repos (as 'owner/name') for the GitHub connector.")
        for repo in cfg.repos:
            # No dot-only segments: '..' would let a config value walk up the API path.
            if not re.fullmatch(r"(?!\.+/)[\w.-]+/(?!\.+$)[\w.-]+", repo):
                raise ConnectorError(f"Invalid repository {repo!r}; expected 'owner/name'.")
        as_of = as_of or utcnow()
        since = (as_of - timedelta(days=cfg.history_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

        raw: dict[str, dict[str, Any]] = {}
        repos_meta: dict[str, dict[str, Any]] = {}
        for repo in cfg.repos:
            repos_meta[repo] = self.http.get_json(f"{self.api}/repos/{repo}")
            # Open issues in full; closed ones only if touched inside the history window.
            for state, extra in (("open", {}), ("closed", {"since": since})):
                params = {"state": state, "sort": "created", "direction": "asc", **extra}
                for item in self._paged(f"{self.api}/repos/{repo}/issues", params, cfg.max_issues):
                    if "pull_request" in item:
                        continue
                    raw[_issue_id(repo, item["number"])] = {**item, "_repo": repo}
        if len(raw) >= cfg.max_issues:
            self.warnings.append(f"Stopped at max_issues={cfg.max_issues}; results are truncated.")

        links = self._dependencies(raw) if cfg.fetch_dependencies else []
        return map_issues(raw, repos_meta, links, cfg, as_of=as_of)

    def _dependencies(self, raw: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
        """Blocking relationships for open issues, as (blocker_id, blocked_id)."""
        edges: set[tuple[str, str]] = set()
        for issue_id, item in raw.items():
            if item.get("state") != "open":
                continue
            repo = item["_repo"]
            url = f"{self.api}/repos/{repo}/issues/{item['number']}/dependencies/blocked_by"
            data = self.http.get_json(url, tolerate=(403, 404))
            if data is None:
                self.warnings.append(
                    "Issue dependencies are unavailable (older GitHub Enterprise Server or missing "
                    "permission); dependencies were skipped."
                )
                return []
            for blocker in data:
                edges.add((_issue_id(_repo_of(blocker, repo), blocker["number"]), issue_id))
        return sorted(edges)


def map_issues(
    raw: dict[str, dict[str, Any]],
    repos_raw: dict[str, dict[str, Any]],
    links: list[tuple[str, str]],
    cfg: GitHubConfig,
    *,
    as_of: datetime,
) -> Dataset:
    """Pure mapping from GitHub's JSON to the normalized dataset (unit-tested without HTTP)."""
    pattern = re.compile(cfg.estimate_label_pattern, re.IGNORECASE)
    projects = {
        repo: Project(id=f"gh-{repo}", key=repo, name=meta.get("name") or repo.split("/")[-1])
        for repo, meta in repos_raw.items()
    }
    milestones: dict[str, Milestone] = {}
    issues: list[Issue] = []
    for issue_id, item in raw.items():
        repo = item["_repo"]
        ms = item.get("milestone")
        milestone_id = None
        if ms:
            milestone_id = f"gh-m-{repo}-{ms['number']}"
            milestones.setdefault(
                milestone_id,
                Milestone(
                    id=milestone_id,
                    name=ms["title"],
                    start_date=(ms.get("created_at") or "")[:10] or None,
                    due_date=(ms.get("due_on") or "")[:10] or None,
                ),
            )
        status = _status(item, cfg)
        assignees = item.get("assignees") or ([item["assignee"]] if item.get("assignee") else [])
        issues.append(
            Issue(
                id=issue_id,
                project_id=projects[repo].id,
                key=f"{repo}#{item['number']}",
                title=item["title"],
                status=status,
                assignee=assignees[0].get("login") if assignees else None,
                estimate=_estimate(item, pattern),
                created_at=item["created_at"],
                updated_at=item["updated_at"],
                resolved_at=item.get("closed_at") if status is Status.DONE else None,
                milestone_id=milestone_id,
                labels=_labels(item),
                url=item.get("html_url"),
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
