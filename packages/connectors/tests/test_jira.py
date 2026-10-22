from datetime import UTC, datetime

import httpx
import pytest
from pgmlens_connectors import ConnectorError, JiraConfig, JiraConnector
from pgmlens_connectors.jira import default_jql, map_issues
from pgmlens_core import EventType, Status

AS_OF = datetime(2026, 10, 21, tzinfo=UTC)
CFG = JiraConfig(
    base_url="https://example.atlassian.net",
    api_token="s3cret",
    email="a@example.com",
    project_keys=["PLAT"],
)


def jira_issue(
    key="PLAT-1",
    *,
    category="new",
    status_name="To Do",
    points=3,
    links=(),
    version=None,
    labels=(),
    changelog=(),
):
    return {
        "key": key,
        "fields": {
            "summary": f"Summary {key}",
            "project": {"key": "PLAT", "name": "Platform"},
            "status": {"name": status_name, "statusCategory": {"key": category}},
            "assignee": {"displayName": "Ana"},
            "created": "2026-09-01T10:00:00.000+0000",
            "updated": "2026-10-15T10:00:00.000+0000",
            "resolutiondate": "2026-10-15T10:00:00.000+0000" if category == "done" else None,
            "fixVersions": [version] if version else [],
            "labels": list(labels),
            "issuelinks": list(links),
            "duedate": None,
            "customfield_10016": points,
        },
        "changelog": {"histories": list(changelog)},
    }


def test_status_mapping():
    raw = [
        jira_issue("PLAT-1", category="new"),
        jira_issue("PLAT-2", category="indeterminate", status_name="In Progress"),
        jira_issue("PLAT-3", category="done", status_name="Done"),
        jira_issue("PLAT-4", category="indeterminate", status_name="Blocked"),
        jira_issue("PLAT-5", category="new", labels=["Blocked"]),
    ]
    ds = map_issues(raw, CFG, "https://example.atlassian.net", as_of=AS_OF)
    assert [i.status for i in ds.issues] == [
        Status.TODO,
        Status.IN_PROGRESS,
        Status.DONE,
        Status.BLOCKED,
        Status.BLOCKED,
    ]
    done = ds.issue_by_id["jira-plat-3"]
    assert (
        done.resolved_at is not None and done.url == "https://example.atlassian.net/browse/PLAT-3"
    )


def test_story_points_assignee_and_versions():
    version = {"id": "10", "name": "1.0", "releaseDate": "2026-12-01"}
    ds = map_issues([jira_issue(points=5, version=version)], CFG, "https://x", as_of=AS_OF)
    issue = ds.issues[0]
    assert issue.estimate == 5 and issue.assignee == "Ana"
    milestone = ds.milestone_by_id["jira-v10"]
    assert milestone.name == "1.0" and str(milestone.due_date) == "2026-12-01"
    assert (
        str(milestone.start_date) == "2026-09-01"
    )  # earliest issue creation approximates the start


def test_blocking_links_become_deduplicated_dependencies():
    a = jira_issue(
        "PLAT-1", links=[{"type": {"name": "Blocks"}, "outwardIssue": {"key": "PLAT-2"}}]
    )
    b = jira_issue("PLAT-2", links=[{"type": {"name": "Blocks"}, "inwardIssue": {"key": "PLAT-1"}}])
    c = jira_issue("PLAT-3", links=[{"type": {"name": "Relates"}, "outwardIssue": {"key": "PLAT-1"}},
                                    {"type": {"name": "Blocks"}, "inwardIssue": {"key": "PLAT-99"}}])  # fmt: skip
    ds = map_issues([a, b, c], CFG, "https://x", as_of=AS_OF)
    assert [(d.blocker_id, d.blocked_id) for d in ds.dependencies] == [
        ("jira-plat-1", "jira-plat-2")
    ]


def test_changelog_becomes_events():
    history = [
        {"created": "2026-10-02T09:00:00.000+0000", "author": {"displayName": "Bo"},
         "items": [{"field": "status", "fromString": "To Do", "toString": "In Progress"},
                   {"field": "resolution", "fromString": None, "toString": "Done"}]},
        {"created": "2026-10-03T09:00:00.000+0000", "items": [{"field": "Story Points", "fromString": "3", "toString": "5"}]},
    ]  # fmt: skip
    ds = map_issues([jira_issue(changelog=history)], CFG, "https://x", as_of=AS_OF)
    assert [e.type for e in ds.events] == [EventType.STATUS_CHANGED, EventType.ESTIMATE_CHANGED]
    assert ds.events[0].actor == "Bo" and ds.events[0].data == {
        "from": "To Do",
        "to": "In Progress",
    }


def test_default_jql():
    assert 'project in ("PLAT")' in default_jql(CFG)
    assert default_jql(CFG.model_copy(update={"jql": "filter = 123"})) == "filter = 123"
    with pytest.raises(ConnectorError, match="project_keys"):
        default_jql(CFG.model_copy(update={"project_keys": []}))


def test_cloud_pagination_uses_next_page_token_and_basic_auth():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        token = request.url.params.get("nextPageToken")
        if token is None:
            return httpx.Response(
                200,
                json={"issues": [jira_issue("PLAT-1")], "nextPageToken": "abc", "isLast": False},
            )
        assert token == "abc"
        return httpx.Response(200, json={"issues": [jira_issue("PLAT-2")], "isLast": True})

    connector = JiraConnector(CFG, transport=httpx.MockTransport(handler))
    ds = connector.fetch(as_of=AS_OF)
    assert [i.key for i in ds.issues] == ["PLAT-1", "PLAT-2"]
    assert len(seen) == 2
    assert seen[0].url.path == "/rest/api/3/search/jql"
    assert seen[0].headers["authorization"].startswith("Basic ")
    assert "expand=changelog" in str(seen[0].url)


def test_server_flavor_uses_start_at_and_bearer_token():
    cfg = JiraConfig(
        base_url="https://jira.corp",
        api_token="pat",
        flavor="server",
        project_keys=["PLAT"],
        page_size=1,
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        start = int(request.url.params["startAt"])
        return httpx.Response(200, json={"issues": [jira_issue(f"PLAT-{start + 1}")], "total": 2})

    ds = JiraConnector(cfg, transport=httpx.MockTransport(handler)).fetch(as_of=AS_OF)
    assert len(ds.issues) == 2
    assert calls[0].url.path == "/rest/api/2/search"
    assert calls[0].headers["authorization"] == "Bearer pat"


def test_auth_errors_are_friendly_and_do_not_leak_the_token():
    transport = httpx.MockTransport(lambda r: httpx.Response(401, json={"message": "nope"}))
    with pytest.raises(ConnectorError) as exc:
        JiraConnector(CFG, transport=transport).fetch(as_of=AS_OF)
    assert "authentication failed" in str(exc.value)
    assert "s3cret" not in str(exc.value)


def test_max_issues_truncates_with_a_warning():
    cfg = CFG.model_copy(update={"max_issues": 1, "page_size": 2})
    transport = httpx.MockTransport(
        lambda r: httpx.Response(
            200, json={"issues": [jira_issue("PLAT-1"), jira_issue("PLAT-2")], "isLast": True}
        )
    )
    connector = JiraConnector(cfg, transport=transport)
    assert len(connector.fetch(as_of=AS_OF).issues) == 1
    assert any("truncated" in w for w in connector.warnings)


def test_from_config_accepts_plain_dicts_and_hides_secrets():
    connector = JiraConnector.from_config(
        {
            "base_url": "https://x.atlassian.net",
            "api_token": "hunter2-secret-value",
            "email": "a@b.c",
            "project_keys": ["A"],
        }
    )
    assert "hunter2-secret-value" not in repr(connector.config)
    assert connector.config.api_token.get_secret_value() == "hunter2-secret-value"
