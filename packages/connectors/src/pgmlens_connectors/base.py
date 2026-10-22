"""Connector interface, entry-point registry and a small retrying HTTP helper.

A connector turns one external system into a normalized :class:`pgmlens_core.Dataset`.
Third-party packages can add their own by declaring an entry point::

    [project.entry-points."pgmlens.connectors"]
    linear = "my_package.linear:LinearConnector"
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import entry_points
from typing import Any, ClassVar, Self

import httpx
from pgmlens_core import Dataset, ProgramInfo

ENTRY_POINT_GROUP = "pgmlens.connectors"
RETRYABLE = {429, 502, 503, 504}


class ConnectorError(RuntimeError):
    """A connector could not complete. Messages never contain credentials."""


class Connector(ABC):
    """Fetch data from one system and return it in the normalized model."""

    name: ClassVar[str]

    def __init__(self) -> None:
        # Non-fatal problems (a missing premium feature, a truncated changelog, ...).
        self.warnings: list[str] = []

    @classmethod
    @abstractmethod
    def from_config(cls, config: dict[str, Any]) -> Self:
        """Build a connector from a plain dict (for example parsed from YAML or JSON)."""

    @abstractmethod
    def fetch(self, *, as_of: datetime | None = None) -> Dataset:
        """Fetch the current state of the program."""


class HttpSession:
    """``httpx.Client`` wrapper with retries on throttling and friendly errors."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.retries = retries
        self._sleep = sleep

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        tolerate: tuple[int, ...] = (),
    ) -> httpx.Response | None:
        """GET with retries. Statuses in ``tolerate`` return ``None`` instead of raising."""
        for attempt in range(self.retries + 1):
            try:
                response = self.client.get(url, params=params)
            except httpx.TransportError as exc:
                if attempt == self.retries:
                    raise ConnectorError(
                        f"Could not reach {_origin(url)}: {type(exc).__name__}"
                    ) from exc
                self._sleep(min(2**attempt, 30))
                continue
            if response.status_code in RETRYABLE and attempt < self.retries:
                delay = response.headers.get("Retry-After", "")
                self._sleep(float(delay) if delay.isdigit() else min(2**attempt, 30))
                continue
            if response.status_code in tolerate:
                return None
            if response.status_code >= 400:
                raise ConnectorError(_describe_error(response))
            return response
        raise ConnectorError("unreachable")  # pragma: no cover

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.get(url, **kwargs)
        return None if response is None else response.json()


def _origin(url: str) -> str:
    parsed = httpx.URL(url)
    return f"{parsed.scheme}://{parsed.host}"


def _describe_error(response: httpx.Response) -> str:
    hints = {
        401: "authentication failed; check the token (and email, for Jira Cloud)",
        403: "access denied; the token lacks permission for this resource",
        404: "not found; check the base URL, project keys and ids",
        429: "rate limited; retries exhausted",
    }
    hint = hints.get(response.status_code, "request failed")
    return f"HTTP {response.status_code} from {response.request.url.path}: {hint}"


def available_connectors() -> dict[str, type[Connector]]:
    """Connectors registered under the ``pgmlens.connectors`` entry-point group."""
    return {ep.name: ep.load() for ep in entry_points(group=ENTRY_POINT_GROUP)}


def create_connector(name: str, config: dict[str, Any]) -> Connector:
    registry = available_connectors()
    if name not in registry:
        raise ConnectorError(f"Unknown connector {name!r}. Installed: {sorted(registry)}")
    return registry[name].from_config(config)


def utcnow() -> datetime:
    return datetime.now(UTC)


def merge_datasets(
    program: ProgramInfo, *datasets: Dataset, as_of: datetime | None = None
) -> Dataset:
    """Combine datasets from several sources (say Jira and GitLab) into one program."""
    seen: dict[str, set[str]] = {"projects": set(), "milestones": set()}
    projects, milestones = [], []
    for ds in datasets:
        for project in ds.projects:
            if project.id not in seen["projects"]:
                seen["projects"].add(project.id)
                projects.append(project)
        for milestone in ds.milestones:
            if milestone.id not in seen["milestones"]:
                seen["milestones"].add(milestone.id)
                milestones.append(milestone)
    return Dataset(
        program=program,
        as_of=as_of or max((d.as_of for d in datasets), default=utcnow()),
        projects=projects,
        milestones=milestones,
        issues=[i for d in datasets for i in d.issues],
        dependencies=[d for ds in datasets for d in ds.dependencies],
        events=[e for ds in datasets for e in ds.events],
    )
