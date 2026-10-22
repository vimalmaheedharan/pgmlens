from datetime import UTC, datetime

import httpx
import pytest
from pgmlens_connectors import (
    Connector,
    ConnectorError,
    HttpSession,
    available_connectors,
    create_connector,
    merge_datasets,
)
from pgmlens_connectors.gitlab import GitLabConfig
from pgmlens_connectors.gitlab import map_issues as gl_map
from pgmlens_connectors.jira import JiraConfig
from pgmlens_connectors.jira import map_issues as jira_map
from pgmlens_core import ProgramInfo
from test_gitlab import PROJECT, gl_issue
from test_jira import jira_issue

AS_OF = datetime(2026, 10, 21, tzinfo=UTC)


def session(handler, sleeps=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpSession(client, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_registry_exposes_builtin_connectors():
    registry = available_connectors()
    assert {"jira", "gitlab"} <= set(registry)
    assert all(issubclass(cls, Connector) for cls in registry.values())


def test_create_connector_by_name_and_unknown_names():
    connector = create_connector("gitlab", {"token": "t", "project_ids": [1]})
    assert connector.name == "gitlab"
    with pytest.raises(ConnectorError, match="Unknown connector"):
        create_connector("nope", {})


def test_throttling_is_retried_with_retry_after():
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    assert session(handler, sleeps).get_json("https://x.test/a") == {"ok": True}
    assert sleeps == [4.0, 4.0]


def test_retries_are_bounded():
    s = session(lambda r: httpx.Response(503))
    with pytest.raises(ConnectorError, match="HTTP 503"):
        s.get("https://x.test/a")


def test_transport_failures_become_connector_errors():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(ConnectorError, match=r"Could not reach https://x\.test"):
        session(handler).get("https://x.test/a")


def test_tolerated_statuses_return_none():
    assert (
        session(lambda r: httpx.Response(403)).get_json("https://x.test/a", tolerate=(403,)) is None
    )


def test_merge_datasets_combines_sources_into_one_program():
    jira = jira_map(
        [jira_issue("PLAT-1")],
        JiraConfig(base_url="https://j", api_token="t"),
        "https://j",
        as_of=AS_OF,
    )
    gitlab = gl_map({"gl-7-1": gl_issue(1)}, {7: PROJECT}, [], GitLabConfig(token="t"), as_of=AS_OF)
    merged = merge_datasets(ProgramInfo(id="all", name="Everything"), jira, gitlab)
    assert {i.key for i in merged.issues} == {"PLAT-1", "acme/app#1"}
    assert {p.key for p in merged.projects} == {"PLAT", "acme/app"}
    assert merged.program.name == "Everything"
