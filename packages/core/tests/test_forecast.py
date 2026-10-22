from datetime import timedelta

from factories import NOW, make_dataset, make_issue, scope_event, steady_history
from pgmlens_core.forecast import (
    forecast_milestones,
    forecast_scope,
    scope_additions,
    weekly_completions,
)
from pgmlens_core.models import Milestone


def _forecast(ds, scope, due_days=None, **kwargs):
    due = (NOW + timedelta(days=due_days)).date() if due_days is not None else None
    return forecast_scope(
        ds, scope, scope_id="m1", scope_name="Milestone 1", due_date=due, **kwargs
    )


def test_constant_throughput_gives_an_exact_answer():
    open_issues = [make_issue(f"O-{n}") for n in range(9)]
    ds = make_dataset([*steady_history(3), *open_issues])
    fc = _forecast(ds, open_issues, due_days=21, include_scope_growth=False)
    assert fc.status == "ok"
    assert fc.mean_weekly_throughput == 3
    assert fc.p50_date == (NOW + timedelta(days=21)).date()
    assert fc.p95_date == fc.p50_date
    assert fc.on_time_probability == 1.0
    assert fc.summary == "On track"


def test_a_tighter_deadline_is_missed_with_certainty():
    open_issues = [make_issue(f"O-{n}") for n in range(9)]
    ds = make_dataset([*steady_history(3), *open_issues])
    fc = _forecast(ds, open_issues, due_days=14, include_scope_growth=False)
    assert fc.on_time_probability == 0.0
    assert fc.slip_days_p80 == 7
    assert fc.summary == "Likely to slip about 1 week"


def test_nothing_left_means_complete():
    ds = make_dataset(steady_history(3))
    fc = _forecast(ds, [], due_days=5)
    assert fc.status == "complete"
    assert fc.on_time_probability == 1.0


def test_no_history_is_reported_not_guessed():
    open_issues = [make_issue(f"O-{n}", created=5) for n in range(4)]
    ds = make_dataset(open_issues)
    fc = _forecast(ds, open_issues, due_days=30)
    assert fc.status == "insufficient_data"
    assert fc.p50_date is None
    assert "Not enough history" in fc.summary


def test_scope_growth_that_matches_throughput_never_converges():
    open_issues = [make_issue(f"O-{n}", created=2) for n in range(8)]
    added, events = [], []
    for week in range(8):
        for n in range(3):  # three new items per week, matching the three finished per week
            issue = make_issue(f"N-{week}-{n}", created=week * 7 + 3.5)
            added.append(issue)
            events.append(scope_event(issue.key, days_ago=week * 7 + 3.5))
    ds = make_dataset([*steady_history(3), *open_issues, *added], events=events)
    fc = _forecast(ds, [*open_issues, *added], due_days=30)
    assert fc.status == "not_converging"
    assert fc.p50_date is None
    assert "arriving as fast" in fc.summary


def test_planned_work_is_not_counted_as_growth():
    start = (NOW - timedelta(days=60)).date()
    milestone = Milestone(
        id="m1", name="M", start_date=start, due_date=(NOW + timedelta(days=30)).date()
    )
    planned = [
        make_issue(f"P-{n}", created=58) for n in range(6)
    ]  # created inside the grace window
    late = make_issue("L-1", created=10)  # created long after start
    ds = make_dataset([*planned, late], milestones=[milestone])
    stamps = scope_additions(ds, [*planned, late])
    assert len(stamps) == 1


def test_weekly_completions_buckets_by_age():
    ds = make_dataset(steady_history(2, weeks=4))
    assert weekly_completions(ds, NOW, 4) == [2, 2, 2, 2]


def test_forecasts_are_deterministic_for_a_seed():
    open_issues = [make_issue(f"O-{n}") for n in range(15)]
    ds = make_dataset([*steady_history(3), *open_issues])
    a = _forecast(ds, open_issues, due_days=30, seed=1)
    b = _forecast(ds, open_issues, due_days=30, seed=1)
    assert a == b


def test_milestones_forecast_cumulatively_in_due_date_order():
    early = Milestone(id="m1", name="Early", due_date=(NOW + timedelta(days=14)).date())
    late = Milestone(id="m2", name="Late", due_date=(NOW + timedelta(days=60)).date())
    issues = [
        *steady_history(3),
        *[make_issue(f"E-{n}", milestone="m1") for n in range(3)],
        *[make_issue(f"L-{n}", milestone="m2") for n in range(6)],
    ]
    ds = make_dataset(issues, milestones=[early, late])
    results = {r.scope_id: r for r in forecast_milestones(ds, include_scope_growth=False)}
    assert results["m1"].remaining == 3
    assert results["m2"].remaining == 9  # late milestone includes the early milestone's open work
    assert results[None].scope_name == "Whole program"
