"""Probabilistic delivery forecasts via Monte Carlo over historical throughput.

Method (deliberately simple and explainable):

1. Count issues completed in each of the last ``history_weeks`` weeks (program-wide, since
   the whole team shares capacity). Count issues *created* in the forecast scope in the
   same weeks (scope growth).
2. Simulate ``trials`` futures. In each simulated week, pick a random historical week and
   apply its (done, created) pair, so correlation between throughput and scope growth is
   preserved.
3. A trial finishes when cumulative net progress reaches the remaining scope. The weeks it
   took become dates; percentiles of the trials give P50/P80/P95.

Assumption: milestones are delivered in due-date order and share team throughput, so a
milestone's scope includes all open work due on or before it.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Literal

import numpy as np
from pydantic import BaseModel, computed_field

from .dates import short_date
from .models import Dataset, EventType, Issue

MAX_WEEKS = 104
MIN_HISTORY_DAYS = 21
SCOPE_GRACE_DAYS = 7  # issues created this soon after a milestone starts count as original scope

ForecastStatus = Literal["ok", "complete", "insufficient_data", "not_converging"]


class ForecastResult(BaseModel):
    scope_id: str | None
    scope_name: str
    status: ForecastStatus
    remaining: int
    weeks_of_history: int
    mean_weekly_throughput: float
    mean_weekly_scope_growth: float
    p50_date: date | None = None
    p80_date: date | None = None
    p95_date: date | None = None
    due_date: date | None = None
    on_time_probability: float | None = None
    note: str = ""

    @property
    def slip_days_p80(self) -> int | None:
        if self.p80_date is None or self.due_date is None:
            return None
        return (self.p80_date - self.due_date).days

    @property
    def slip_days_p50(self) -> int | None:
        if self.p50_date is None or self.due_date is None:
            return None
        return (self.p50_date - self.due_date).days

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summary(self) -> str:
        """One plain-language line for people who do not want to read percentiles."""
        if self.status == "complete":
            return "Nothing left to do"
        if self.status == "insufficient_data":
            return "Not enough history to forecast yet"
        if self.status == "not_converging":
            return "New work is arriving as fast as it is finished"
        if self.p50_date is None or self.p80_date is None:
            return "Finish date is highly uncertain and may slip a long way"
        if self.due_date is None:
            return f"Likely done around {short_date(self.p50_date)} (80% sure by {short_date(self.p80_date)})"
        slip = (self.p80_date - self.due_date).days
        if slip <= 0:
            return "On track"
        weeks = max(1, round(slip / 7))
        unit = "week" if weeks == 1 else "weeks"
        return f"Likely to slip about {weeks} {unit}"


def _bucket(stamps: list[datetime], as_of: datetime, weeks: int) -> list[int]:
    """Events per week for the last ``weeks`` weeks; index 0 is the most recent week."""
    counts = [0] * weeks
    for stamp in stamps:
        age_days = (as_of - stamp).total_seconds() / 86400
        if age_days < 0:
            continue
        week = int(age_days // 7)
        if week < weeks:
            counts[week] += 1
    return counts


def weekly_completions(ds: Dataset, as_of: datetime, weeks: int) -> list[int]:
    return _bucket([i.resolved_at for i in ds.issues if i.resolved_at is not None], as_of, weeks)


def scope_additions(ds: Dataset, scope_issues: list[Issue]) -> list[datetime]:
    """When work was added to scope after it was planned.

    An issue counts as an addition if it has an explicit ``scope_added`` event, or if it was
    created more than ``SCOPE_GRACE_DAYS`` after its milestone's start date. Issues from the
    initial planning burst are deliberately *not* counted as growth.
    """
    first_event: dict[str, datetime] = {}
    for event in ds.events:
        if event.type is EventType.SCOPE_ADDED:
            first_event[event.issue_id] = min(first_event.get(event.issue_id, event.at), event.at)
    stamps: list[datetime] = []
    for issue in scope_issues:
        if issue.id in first_event:
            stamps.append(first_event[issue.id])
            continue
        milestone = ds.milestone_by_id.get(issue.milestone_id) if issue.milestone_id else None
        if (
            milestone
            and milestone.start_date
            and issue.created_at.date() > milestone.start_date + timedelta(days=SCOPE_GRACE_DAYS)
        ):
            stamps.append(issue.created_at)
    return stamps


def _percentile(sorted_weeks: np.ndarray, q: float) -> float:
    index = max(0, math.ceil(q * len(sorted_weeks)) - 1)
    return float(sorted_weeks[index])


def _to_date(as_of: datetime, weeks: float) -> date | None:
    if not math.isfinite(weeks):
        return None
    return (as_of + timedelta(days=math.ceil(weeks * 7))).date()


def forecast_scope(
    ds: Dataset,
    scope_issues: list[Issue],
    *,
    scope_id: str | None,
    scope_name: str,
    due_date: date | None,
    as_of: datetime | None = None,
    history_weeks: int = 8,
    trials: int = 5000,
    seed: int = 7,
    include_scope_growth: bool = True,
) -> ForecastResult:
    """Forecast completion of the open issues in ``scope_issues``."""
    as_of = as_of or ds.as_of
    remaining = sum(1 for i in scope_issues if i.is_open)
    done_hist = weekly_completions(ds, as_of, history_weeks)
    created_hist = _bucket(scope_additions(ds, scope_issues), as_of, history_weeks)
    base = {
        "scope_id": scope_id,
        "scope_name": scope_name,
        "remaining": remaining,
        "weeks_of_history": history_weeks,
        "mean_weekly_throughput": round(float(np.mean(done_hist)), 2),
        "mean_weekly_scope_growth": round(float(np.mean(created_hist)), 2)
        if include_scope_growth
        else 0.0,
        "due_date": due_date,
    }

    if remaining == 0:
        return ForecastResult(
            **base, status="complete", p50_date=as_of.date(), p80_date=as_of.date(), p95_date=as_of.date(),
            on_time_probability=1.0,
        )  # fmt: skip

    earliest = min((i.created_at for i in ds.issues), default=as_of)
    history_days = (as_of - earliest).days
    if sum(done_hist) == 0 or history_days < MIN_HISTORY_DAYS:
        return ForecastResult(
            **base,
            status="insufficient_data",
            note=f"Need at least {MIN_HISTORY_DAYS} days of history and one completed issue.",
        )

    rng = np.random.default_rng(seed)
    done = np.asarray(done_hist, dtype=float)
    created = (
        np.asarray(created_hist, dtype=float) if include_scope_growth else np.zeros(history_weeks)
    )
    picks = rng.integers(0, history_weeks, size=(trials, MAX_WEEKS))
    net = done[picks] - created[picks]
    cumulative = np.cumsum(net, axis=1)
    reached = cumulative >= remaining
    finished = reached.any(axis=1)
    first = reached.argmax(axis=1)
    rows = np.arange(trials)
    previous = np.where(first > 0, cumulative[rows, np.maximum(first - 1, 0)], 0.0)
    step = np.where(net[rows, first] > 0, net[rows, first], 1.0)
    fraction = np.clip((remaining - previous) / step, 0.0, 1.0)
    weeks = np.where(finished, first + fraction, np.inf)
    ordered = np.sort(weeks)

    p50, p80, p95 = (_percentile(ordered, q) for q in (0.5, 0.8, 0.95))
    status: ForecastStatus = "ok" if math.isfinite(p50) else "not_converging"
    on_time: float | None = None
    if due_date is not None:
        days_left = (due_date - as_of.date()).days
        on_time = round(float(np.mean(weeks * 7 <= days_left)), 3)

    return ForecastResult(
        **base,
        status=status,
        p50_date=_to_date(as_of, p50),
        p80_date=_to_date(as_of, p80),
        p95_date=_to_date(as_of, p95),
        on_time_probability=on_time,
    )


def forecast_milestones(
    ds: Dataset, *, as_of: datetime | None = None, **kwargs: object
) -> list[ForecastResult]:
    """Forecast every milestone with open work, plus the whole program."""
    as_of = as_of or ds.as_of
    results: list[ForecastResult] = []
    dated = [m for m in ds.milestones if m.due_date is not None]
    for milestone in sorted(ds.milestones, key=lambda m: (m.due_date is None, m.due_date, m.id)):
        if not ds.issues_in_milestone(milestone.id):
            continue
        # Cumulative scope: this milestone plus everything due earlier.
        cutoff = milestone.due_date
        ids = {milestone.id}
        if cutoff is not None:
            ids |= {m.id for m in dated if m.due_date is not None and m.due_date <= cutoff}
        scope = [i for i in ds.issues if i.milestone_id in ids]
        if not any(i.is_open for i in ds.issues_in_milestone(milestone.id)):
            continue
        results.append(
            forecast_scope(
                ds, scope, scope_id=milestone.id, scope_name=milestone.name,
                due_date=milestone.due_date, as_of=as_of, **kwargs,  # type: ignore[arg-type]
            )
        )  # fmt: skip
    program_due = max((m.due_date for m in dated), default=None)
    results.append(
        forecast_scope(
            ds, list(ds.issues), scope_id=None, scope_name="Whole program",
            due_date=program_due, as_of=as_of, **kwargs,  # type: ignore[arg-type]
        )
    )  # fmt: skip
    return results
