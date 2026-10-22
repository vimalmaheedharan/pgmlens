from datetime import UTC, datetime

import httpx
import pytest
from pgmlens_connectors import ConnectorError, GitHubConfig, GitHubConnector
from pgmlens_connectors.github import map_issues
from pgmlens_core import Status

AS_OF = datetime(2026, 10, 21, tzinfo=UTC)
CFG = GitHubConfig(token="ghp-secret", repos=["acme/app"], program_name="Demo")
REPO = {"name": "app", "full_name": "acme/app"}


def gh_issue(n, *, state="open", labels=(), milestone=None, assignee="ana", repo="acme/app"):
    return {
        "number": n, "title": f"Issue {n}", "state": state,
        "labels": [{"name": name} for name in labels], "milestone": milestone,
        "assignees": [{"login": assignee}] if assignee else [],
        "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-10-10T10:00:00Z",
        "closed_at": "2026-10-10T10:00:00Z" if state == "closed" else None,
        "html_url": f"https://github.com/{repo}/issues/{n}",
        "repository_url": f"https://api.github.com/repos/{repo}",
    }  # fmt: skip


def raw_of(*issues):
    return {f"gh-acme/app#{i['number']}": {**i, "_repo": "acme/app"} for i in issues}


def test_status_estimate_and_milestone_mapping():
    ms = {
        "number": 3,
        "title": "v1",
        "created_at": "2026-09-01T00:00:00Z",
        "due_on": "2026-12-01T00:00:00Z",
    }
    raw = raw_of(
        gh_issue(1, labels=["Blocked", "size: 5"], milestone=ms),
        gh_issue(2, labels=["in progress"]),
        gh_issue(3, state="closed"),
        gh_issue(4, assignee=None, labels=["points:2.5"]),
    )
    ds = map_issues(raw, {"acme/app": REPO}, [], CFG, as_of=AS_OF)
    assert [i.status for i in ds.issues] == [
        Status.BLOCKED,
        Status.IN_PROGRESS,
        Status.DONE,
        Status.TODO,
    ]
    first = ds.issue_by_id["gh-acme/app#1"]
    assert first.estimate == 5 and first.key == "acme/app#1" and first.assignee == "ana"
    assert ds.issue_by_id["gh-acme/app#4"].estimate == 2.5
    assert ds.issue_by_id["gh-acme/app#4"].assignee is None
    milestone = ds.milestone_by_id["gh-m-acme/app-3"]
    assert str(milestone.start_date) == "2026-09-01" and str(milestone.due_date) == "2026-12-01"
    assert ds.issue_by_id["gh-acme/app#3"].resolved_at is not None


def test_dependencies_to_unknown_issues_are_dropped():
    raw = raw_of(gh_issue(1), gh_issue(2))
    links = [("gh-acme/app#1", "gh-acme/app#2"), ("gh-acme/app#1", "gh-other/x#9")]
    ds = map_issues(raw, {"acme/app": REPO}, links, CFG, as_of=AS_OF)
    assert [(d.blocker_id, d.blocked_id) for d in ds.dependencies] == [
        ("gh-acme/app#1", "gh-acme/app#2")
    ]


def make_handler(*, deps_status=200, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        path, params = request.url.path, request.url.params
        assert request.headers["authorization"] == "Bearer ghp-secret"
        if path == "/repos/acme/app":
            return httpx.Response(200, json=REPO)
        if path == "/repos/acme/app/issues":
            if params["state"] == "open":
                if params.get("page") != "2":
                    nxt = '<https://api.github.com/repos/acme/app/issues?state=open&page=2>; rel="next"'
                    pull = {**gh_issue(9), "pull_request": {"url": "x"}}
                    return httpx.Response(
                        200, json=[gh_issue(1), gh_issue(2), pull], headers={"Link": nxt}
                    )
                return httpx.Response(200, json=[gh_issue(3)])
            assert "since" in params
            return httpx.Response(200, json=[gh_issue(4, state="closed")])
        if path.endswith("/dependencies/blocked_by"):
            if deps_status != 200:
                return httpx.Response(deps_status, json={"message": "nope"})
            if path.endswith("/issues/2/dependencies/blocked_by"):
                return httpx.Response(200, json=[gh_issue(1)])
            if path.endswith("/issues/3/dependencies/blocked_by"):
                return httpx.Response(200, json=[gh_issue(2)])
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={})

    return handler


def test_full_fetch_paginates_skips_prs_and_reads_dependencies():
    calls = []
    connector = GitHubConnector(CFG, transport=httpx.MockTransport(make_handler(calls=calls)))
    ds = connector.fetch(as_of=AS_OF)
    assert sorted(i.key for i in ds.issues) == [
        "acme/app#1",
        "acme/app#2",
        "acme/app#3",
        "acme/app#4",
    ]
    assert sorted((d.blocker_id, d.blocked_id) for d in ds.dependencies) == [
        ("gh-acme/app#1", "gh-acme/app#2"),
        ("gh-acme/app#2", "gh-acme/app#3"),
    ]
    assert connector.warnings == []
    assert not any(c.url.path.endswith("/issues/4/dependencies/blocked_by") for c in calls)


def test_unavailable_dependencies_degrade_to_a_warning():
    connector = GitHubConnector(CFG, transport=httpx.MockTransport(make_handler(deps_status=404)))
    ds = connector.fetch(as_of=AS_OF)
    assert ds.dependencies == []
    assert any("dependencies are unavailable" in w for w in connector.warnings)


def test_requires_valid_repos_and_hides_the_token():
    with pytest.raises(ConnectorError, match="Set repos"):
        GitHubConnector(GitHubConfig(token="t")).fetch(as_of=AS_OF)
    with pytest.raises(ConnectorError, match="Invalid repository"):
        GitHubConnector(GitHubConfig(token="t", repos=["../etc"])).fetch(as_of=AS_OF)
    assert "ghp-secret" not in repr(CFG)


def test_registered_as_entry_point():
    from pgmlens_connectors import available_connectors

    assert "github" in available_connectors()
