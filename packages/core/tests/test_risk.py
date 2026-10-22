from datetime import timedelta

import pytest
from factories import NOW, make_dataset, make_issue, scope_event, steady_history
from pgmlens_core import Milestone, Severity, Status, analyze
from pgmlens_core.risk import EVALUATORS, load_rules, parse_rules


def _rule_ids(result):
    return {f.rule_id for f in result.findings}


def _finding(result, rule_id):
    return next(f for f in result.findings if f.rule_id == rule_id)


def test_stale_blocker_is_flagged_with_the_work_it_holds_up():
    ds = make_dataset(
        [make_issue("A-1", Status.IN_PROGRESS, updated=25), make_issue("A-2"), make_issue("A-3")],
        [("A-1", "A-2"), ("A-1", "A-3")],
    )
    finding = _finding(analyze(ds), "stale-blocker")
    assert finding.id == "stale-blocker:a-1"
    assert finding.issue_keys == ["A-1", "A-2", "A-3"]
    assert finding.metrics["days_stale"] == 25
    assert finding.metrics["blocked_count"] == 2


def test_fresh_blockers_are_not_flagged():
    ds = make_dataset(
        [make_issue("A-1", Status.IN_PROGRESS, updated=2), make_issue("A-2")], [("A-1", "A-2")]
    )
    assert "stale-blocker" not in _rule_ids(analyze(ds))


def test_scope_creep_needs_enough_recent_additions():
    issues = [make_issue(f"S-{n}", created=3) for n in range(4)] + [
        make_issue(f"O-{n}", created=50) for n in range(10)
    ]
    ds = make_dataset(issues, events=[scope_event(f"S-{n}", 3) for n in range(4)])
    finding = _finding(analyze(ds), "scope-creep")
    assert finding.metrics["added"] == 4
    one_off = make_dataset(
        [make_issue("S-0", created=3), *[make_issue(f"O-{n}", created=50) for n in range(10)]]
    )
    assert "scope-creep" not in _rule_ids(analyze(one_off))


def test_overloaded_owner():
    issues = [make_issue(f"W-{n}", Status.IN_PROGRESS, assignee="Ben") for n in range(6)]
    result = analyze(make_dataset(issues))
    finding = _finding(result, "overloaded-owner")
    assert finding.metrics == {"in_progress": 6, "open": 6, "assignee": "Ben"}


def test_silent_in_progress_work():
    ds = make_dataset(
        [
            make_issue("Q-1", Status.IN_PROGRESS, updated=14),
            make_issue("Q-2", Status.IN_PROGRESS, updated=1),
        ]
    )
    finding = _finding(analyze(ds), "silent-in-progress")
    assert finding.issue_keys == ["Q-1"]


def test_unowned_critical_path_work():
    ds = make_dataset(
        [
            make_issue("A-1", estimate=5),
            make_issue("A-2", assignee=None, estimate=5),
            make_issue("A-3", estimate=1),
        ],
        [("A-1", "A-2")],
    )
    finding = _finding(analyze(ds), "unassigned-critical")
    assert finding.issue_keys == ["A-2"]


def test_dependency_cycle_is_a_finding():
    ds = make_dataset([make_issue("A-1"), make_issue("A-2")], [("A-1", "A-2"), ("A-2", "A-1")])
    finding = _finding(analyze(ds), "dependency-cycle")
    assert "Circular dependency" in finding.message


def test_deep_chains_are_flagged_at_their_root():
    ds = make_dataset(
        [make_issue(f"A-{n}") for n in range(1, 6)], [(f"A-{n}", f"A-{n + 1}") for n in range(1, 5)]
    )
    finding = _finding(analyze(ds), "blocked-chain")
    assert finding.issue_keys[0] == "A-1"
    assert finding.metrics["chain_depth"] == 4


def test_milestone_slip_escalates_to_critical_when_hopeless():
    due = (NOW + timedelta(days=7)).date()
    open_issues = [make_issue(f"O-{n}", milestone="m1") for n in range(12)]
    ds = make_dataset(
        [*steady_history(3), *open_issues],
        milestones=[Milestone(id="m1", name="Launch", due_date=due)],
    )
    finding = _finding(analyze(ds), "milestone-slip")
    assert finding.severity is Severity.CRITICAL
    assert finding.metrics["on_time_probability"] == 0.0


def test_overdue_milestone_with_open_work_is_critical():
    ds = make_dataset(
        [*steady_history(3), make_issue("O-1", milestone="m1")],
        milestones=[Milestone(id="m1", name="Late one", due_date=(NOW - timedelta(days=5)).date())],
    )
    finding = _finding(analyze(ds), "milestone-slip")
    assert finding.severity is Severity.CRITICAL
    assert "5 days ago" in finding.message


def test_a_healthy_program_reports_no_findings():
    ds = make_dataset(
        [*steady_history(3), *[make_issue(f"O-{n}", assignee=f"P{n}") for n in range(3)]],
        milestones=[Milestone(id="m1", name="Easy", due_date=(NOW + timedelta(days=60)).date())],
    )
    result = analyze(ds)
    assert result.findings == []
    assert result.health.status == "on_track"


def test_health_reflects_the_worst_finding():
    ds = make_dataset(
        [make_issue("A-1", Status.IN_PROGRESS, updated=25), make_issue("A-2")],
        [("A-1", "A-2")],
    )
    assert analyze(ds).health.status == "at_risk"  # high severity, nothing critical


def test_findings_are_sorted_most_severe_first():
    ds = make_dataset(
        [
            make_issue("Q-1", Status.IN_PROGRESS, updated=14),
            make_issue("A-1", Status.IN_PROGRESS, updated=25),
            make_issue("A-2"),
        ],
        [("A-1", "A-2")],
    )
    severities = [f.severity for f in analyze(ds).findings]
    assert severities == sorted(
        severities, key=lambda s: -["low", "medium", "high", "critical"].index(s.value)
    )


def test_every_builtin_rule_type_has_an_evaluator_and_a_default_rule():
    default_types = {r.type for r in load_rules().rules}
    assert default_types == set(EVALUATORS)


def test_custom_rules_extend_and_override_defaults():
    rules = parse_rules(
        """
extends: default
rules:
  - id: stale-blocker
    type: stale_blocker
    severity: critical
    title: Stale blocker
    params: { stale_days: 2 }
  - id: my-extra
    type: overloaded_owner
    title: Mine
    params: { max_in_progress: 1 }
"""
    )
    by_id = {r.id: r for r in rules.rules}
    assert by_id["stale-blocker"].severity is Severity.CRITICAL
    assert by_id["stale-blocker"].params == {"stale_days": 2}
    assert "my-extra" in by_id
    assert "milestone-slip" in by_id  # inherited


def test_disabled_rules_are_skipped():
    rules = parse_rules("rules:\n  - {id: x, type: dependency_cycle, title: X, enabled: false}\n")
    ds = make_dataset([make_issue("A-1"), make_issue("A-2")], [("A-1", "A-2"), ("A-2", "A-1")])
    assert analyze(ds, rules).findings == []


def test_unknown_rule_types_fail_with_a_helpful_message():
    with pytest.raises(ValueError, match="Unknown rule type"):
        parse_rules("rules:\n  - {id: x, type: nope, title: X}\n")


def test_duplicate_rule_ids_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        parse_rules(
            "rules:\n  - {id: x, type: dependency_cycle, title: X}\n  - {id: x, type: dependency_cycle, title: Y}\n"
        )
