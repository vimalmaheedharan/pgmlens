from datetime import UTC, datetime

import httpx
import pytest
from pgmlens_connectors import ConnectorError, GitLabConfig, GitLabConnector
from pgmlens_connectors.gitlab import map_issues
from pgmlens_core import Status

AS_OF = datetime(2026, 10, 21, tzinfo=UTC)
CFG = GitLabConfig(token="glpat-secret", project_ids=[7], program_name="Demo")


def gl_issue(iid, *, state="opened", labels=(), weight=None, milestone=None, assignee="Ana", pid=7):
    return {
        "id": 1000 + iid, "iid": iid, "project_id": pid, "title": f"Issue {iid}", "state": state,
        "labels": list(labels), "weight": weight, "milestone": milestone,
        "assignees": [{"name": assignee}] if assignee else [],
        "created_at": "2026-09-01T10:00:00.000Z", "updated_at": "2026-10-10T10:00:00.000Z",
        "closed_at": "2026-10-10T10:00:00.000Z" if state == "closed" else None,
        "web_url": f"https://gitlab.com/acme/app/-/issues/{iid}", "due_date": None,
        "time_stats": {"time_estimate": 0},
    }  # fmt: skip


PROJECT = {"id": 7, "name": "App", "path_with_namespace": "acme/app"}


def test_status_estimate_and_milestone_mapping():
    ms = {"id": 3, "title": "v1", "start_date": "2026-09-01", "due_date": "2026-12-01"}
    raw = {
        "gl-7-1": gl_issue(1, labels=["Blocked"], weight=5, milestone=ms),
        "gl-7-2": gl_issue(2, labels=["workflow::in dev"]),
        "gl-7-3": gl_issue(3, state="closed"),
        "gl-7-4": gl_issue(4, assignee=None),
    }
    ds = map_issues(raw, {7: PROJECT}, [], CFG, as_of=AS_OF)
    assert [i.status for i in ds.issues] == [
        Status.BLOCKED,
        Status.IN_PROGRESS,
        Status.DONE,
        Status.TODO,
    ]
    first = ds.issue_by_id["gl-7-1"]
    assert first.estimate == 5 and first.key == "acme/app#1" and first.milestone_id == "gl-m3"
    assert ds.issue_by_id["gl-7-4"].assignee is None
    assert str(ds.milestone_by_id["gl-m3"].start_date) == "2026-09-01"
    assert ds.issue_by_id["gl-7-3"].resolved_at is not None


def test_time_estimates_convert_to_working_days():
    item = gl_issue(1)
    item["time_stats"] = {"time_estimate": 28800 * 3}
    ds = map_issues({"gl-7-1": item}, {7: PROJECT}, [], CFG, as_of=AS_OF)
    assert ds.issues[0].estimate == 3


def test_links_to_unknown_issues_are_dropped():
    raw = {"gl-7-1": gl_issue(1), "gl-7-2": gl_issue(2)}
    ds = map_issues(
        raw, {7: PROJECT}, [("gl-7-1", "gl-7-2"), ("gl-7-1", "gl-9-9")], CFG, as_of=AS_OF
    )
    assert [(d.blocker_id, d.blocked_id) for d in ds.dependencies] == [("gl-7-1", "gl-7-2")]


def make_handler(*, links_status=200, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        path, params = request.url.path, request.url.params
        assert request.headers["private-token"] == "glpat-secret"
        if path == "/api/v4/projects/7":
            return httpx.Response(200, json=PROJECT)
        if path == "/api/v4/projects/7/issues":
            if params["state"] == "opened":
                if params["page"] == "1":
                    return httpx.Response(
                        200, json=[gl_issue(1), gl_issue(2)], headers={"x-next-page": "2"}
                    )
                return httpx.Response(200, json=[gl_issue(3)])
            assert "updated_after" in params
            return httpx.Response(200, json=[gl_issue(4, state="closed")])
        if path.endswith("/links"):
            if links_status != 200:
                return httpx.Response(links_status, json={"message": "403 Forbidden"})
            if path.endswith("/issues/1/links"):
                return httpx.Response(
                    200, json=[{"iid": 2, "project_id": 7, "link_type": "blocks"}]
                )
            if path.endswith("/issues/3/links"):
                return httpx.Response(
                    200, json=[{"iid": 2, "project_id": 7, "link_type": "is_blocked_by"}]
                )
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={})

    return handler


def test_full_fetch_paginates_and_reads_links():
    calls = []
    connector = GitLabConnector(CFG, transport=httpx.MockTransport(make_handler(calls=calls)))
    ds = connector.fetch(as_of=AS_OF)
    assert sorted(i.key for i in ds.issues) == [
        "acme/app#1",
        "acme/app#2",
        "acme/app#3",
        "acme/app#4",
    ]
    assert sorted((d.blocker_id, d.blocked_id) for d in ds.dependencies) == [
        ("gl-7-1", "gl-7-2"),
        ("gl-7-2", "gl-7-3"),
    ]
    assert connector.warnings == []
    assert not any(
        c.url.path.endswith("/issues/4/links") for c in calls
    )  # closed issues are not queried for links


def test_missing_premium_links_degrade_to_a_warning():
    connector = GitLabConnector(CFG, transport=httpx.MockTransport(make_handler(links_status=403)))
    ds = connector.fetch(as_of=AS_OF)
    assert ds.dependencies == []
    assert any("paid GitLab tier" in w for w in connector.warnings)


def test_group_mode_uses_the_group_endpoint():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/v4/groups/12/issues":
            return httpx.Response(
                200, json=[gl_issue(1)] if request.url.params["state"] == "opened" else []
            )
        return httpx.Response(200, json=PROJECT if request.url.path == "/api/v4/projects/7" else [])

    cfg = GitLabConfig(token="t", group_id=12)
    GitLabConnector(cfg, transport=httpx.MockTransport(handler)).fetch(as_of=AS_OF)
    assert "/api/v4/groups/12/issues" in paths


def test_requires_a_scope_and_surfaces_http_errors():
    with pytest.raises(ConnectorError, match="project_ids or group_id"):
        GitLabConnector(GitLabConfig(token="t")).fetch(as_of=AS_OF)
    transport = httpx.MockTransport(lambda r: httpx.Response(401, json={}))
    with pytest.raises(ConnectorError) as exc:
        GitLabConnector(CFG, transport=transport).fetch(as_of=AS_OF)
    assert "authentication failed" in str(exc.value) and "glpat-secret" not in str(exc.value)
