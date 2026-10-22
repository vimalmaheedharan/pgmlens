from datetime import timedelta

from factories import NOW, make_dataset, make_issue
from pgmlens_core import Milestone, Status, analyze_graph


def test_critical_path_follows_the_heaviest_chain():
    ds = make_dataset(
        [
            make_issue("A-1", estimate=3),
            make_issue("A-2", estimate=5),
            make_issue("A-3", estimate=2),
            make_issue("A-4", estimate=1),
        ],
        [("A-1", "A-2"), ("A-2", "A-3"), ("A-4", "A-3")],
    )
    path = analyze_graph(ds).critical_path
    assert path.issue_ids == ["a-1", "a-2", "a-3"]
    assert path.length == 10


def test_finished_work_does_not_count_toward_the_critical_path():
    ds = make_dataset(
        [
            make_issue("A-1", Status.DONE, estimate=8, resolved=3),
            make_issue("A-2", estimate=2),
            make_issue("A-3", estimate=1),
        ],
        [("A-1", "A-2"), ("A-2", "A-3")],
    )
    path = analyze_graph(ds).critical_path
    assert path.issue_ids == ["a-2", "a-3"]
    assert path.length == 3


def test_missing_estimates_count_as_one_unit():
    ds = make_dataset(
        [make_issue("A-1", estimate=None), make_issue("A-2", estimate=None)], [("A-1", "A-2")]
    )
    assert analyze_graph(ds).critical_path.length == 2


def test_blocked_chain_depth_and_root_blockers():
    ds = make_dataset(
        [make_issue(f"A-{n}") for n in range(1, 5)],
        [("A-1", "A-2"), ("A-2", "A-3"), ("A-3", "A-4")],
    )
    result = analyze_graph(ds)
    depth = {b.issue_id: b.depth for b in result.blocked}
    assert depth == {"a-2": 1, "a-3": 2, "a-4": 3}
    assert all(b.root_blocker_ids == ["a-1"] for b in result.blocked)
    root = result.root_blockers[0]
    assert (root.issue_id, root.downstream_count, root.max_depth) == ("a-1", 3, 3)


def test_resolved_blockers_do_not_block():
    ds = make_dataset(
        [make_issue("A-1", Status.DONE, resolved=2), make_issue("A-2")], [("A-1", "A-2")]
    )
    assert analyze_graph(ds).blocked == []


def test_cycles_are_reported_not_fatal():
    ds = make_dataset(
        [make_issue("A-1"), make_issue("A-2"), make_issue("A-3")],
        [("A-1", "A-2"), ("A-2", "A-3"), ("A-3", "A-1")],
    )
    result = analyze_graph(ds)
    assert len(result.cycles) == 1
    assert set(result.cycles[0]) == {"a-1", "a-2", "a-3"}
    assert result.critical_path.issue_ids  # still produces a path on the cycle-broken graph


def test_milestone_scoped_paths_include_upstream_work():
    ds = make_dataset(
        [
            make_issue("A-1", milestone="m1", estimate=4),
            make_issue("A-2", milestone="m2", estimate=3),
            make_issue("A-3", milestone="m2", estimate=1),
        ],
        [("A-1", "A-2")],
        milestones=[
            Milestone(id="m1", name="One", due_date=(NOW + timedelta(days=10)).date()),
            Milestone(id="m2", name="Two", due_date=(NOW + timedelta(days=20)).date()),
        ],
    )
    result = analyze_graph(ds)
    assert result.milestone_paths["m2"].issue_ids == ["a-1", "a-2"]
    assert result.milestone_paths["m1"].issue_ids == ["a-1"]


def test_cross_project_coupling_counts_unresolved_edges():
    ds = make_dataset(
        [
            make_issue("A-1", project="p1"),
            make_issue("A-2", project="p1"),
            make_issue("B-1", project="p2"),
            make_issue("B-2", project="p2"),
        ],
        [("A-1", "B-1"), ("A-2", "B-2"), ("A-1", "A-2")],
    )
    (link,) = analyze_graph(ds).coupling
    assert (link.blocker_project_id, link.blocked_project_id) == ("p1", "p2")
    assert (link.edges, link.unresolved) == (2, 2)


def test_empty_dataset_is_fine():
    result = analyze_graph(make_dataset([]))
    assert result.critical_path.issue_ids == []
    assert result.blocked == []
