"""Seeded synthetic program so PGM Lens can be tried without connecting real systems.

The story is deliberately varied: one milestone is slipping, a stale blocker sits at the
root of a deep chain, scope crept into the beta, one person is overloaded and a
critical-path item has no owner. All names are fictional.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import networkx as nx

from .models import (
    Dataset,
    Dependency,
    Event,
    EventType,
    Issue,
    Milestone,
    ProgramInfo,
    Project,
    Status,
)

PEOPLE = ["Aisha K.", "Ben R.", "Chen W.", "Dmitri S.", "Elena V.", "Farid M.", "Grace O."]
VERBS = [
    "Migrate", "Harden", "Add", "Refactor", "Instrument", "Document", "Load-test", "Backfill",
    "Simplify", "Cache", "Validate", "Retire", "Index", "Version",
]  # fmt: skip
NOUNS = {
    "BCK": [
        "auth tokens", "billing webhooks", "search indexer", "notification fan-out", "API gateway routes",
        "tenant onboarding", "audit log writer", "report exports", "permission checks", "import pipeline",
        "rate limiter", "session store", "feature flags", "job scheduler",
    ],
    "MOB": [
        "login screen", "offline sync", "push registration", "profile editor", "search results",
        "settings page", "deep links", "onboarding flow", "receipt viewer", "crash reporter",
        "biometric unlock", "dark mode", "image uploads", "release pipeline",
    ],
}  # fmt: skip
DEFAULT_AS_OF = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
# Days before "now" that each milestone started; planned work is created around then.
START_AGO = {"m0": 90, "m1": 50, "m2": 30, "m3": 20}


def generate_demo(as_of: datetime | None = None, seed: int = 42) -> Dataset:
    rng = random.Random(seed)
    now = (as_of or DEFAULT_AS_OF).astimezone(UTC)
    today = now.date()

    def ago(days: float) -> datetime:
        return now - timedelta(days=days)

    projects = [
        Project(id="bck", key="BCK", name="Backend", owner="Aisha K."),
        Project(id="mob", key="MOB", name="Mobile app", owner="Elena V."),
    ]
    milestones = [
        Milestone(
            id="m0",
            name="Foundations",
            start_date=today - timedelta(days=90),
            due_date=today - timedelta(days=21),
        ),
        Milestone(
            id="m1",
            name="Private beta",
            start_date=today - timedelta(days=50),
            due_date=today + timedelta(days=18),
        ),
        Milestone(
            id="m2",
            name="General availability",
            start_date=today - timedelta(days=30),
            due_date=today + timedelta(days=60),
        ),
        Milestone(
            id="m3",
            name="Mobile parity",
            start_date=today - timedelta(days=20),
            due_date=today + timedelta(days=90),
        ),
    ]

    issues: list[Issue] = []
    events: list[Event] = []
    used_titles: set[str] = set()
    counters = {"BCK": 0, "MOB": 0}
    auto = object()

    def title_for(project: str) -> str:
        for _ in range(100):
            title = f"{rng.choice(VERBS)} {rng.choice(NOUNS[project])}"
            if title not in used_titles:
                used_titles.add(title)
                return title
        return f"{rng.choice(VERBS)} {rng.choice(NOUNS[project])} ({counters[project]})"

    def add(
        project: str,
        milestone: str,
        status: Status,
        *,
        assignee: object = auto,
        created_ago: float | None = None,
        updated_ago: float | None = None,
        resolved_ago: float | None = None,
        estimate: float | None = None,
        title: str | None = None,
    ) -> Issue:
        counters[project] += 1
        key = f"{project}-{counters[project]}"
        who = rng.choice(PEOPLE) if assignee is auto else assignee
        if status is Status.DONE:
            resolved_ago = resolved_ago if resolved_ago is not None else rng.uniform(1, 30)
            updated_ago = resolved_ago
            if created_ago is None:  # planned work is created around the milestone start
                created_ago = max(resolved_ago + 1, START_AGO[milestone] - rng.uniform(0, 6))
        else:
            if updated_ago is None:
                updated_ago = rng.uniform(0, 6)
            if created_ago is None:
                created_ago = max(updated_ago + 1, START_AGO[milestone] - rng.uniform(0, 6))
        issue = Issue(
            id=key.lower(),
            project_id=project.lower(),
            key=key,
            title=title or title_for(project),
            status=status,
            assignee=who if isinstance(who, str) or who is None else None,
            estimate=estimate if estimate is not None else rng.choice([1, 2, 3, 5, 8]),
            created_at=ago(created_ago),
            updated_at=ago(updated_ago),
            resolved_at=ago(resolved_ago)
            if status is Status.DONE and resolved_ago is not None
            else None,
            milestone_id=milestone,
            url=f"https://tracker.example.com/browse/{key}",
        )
        issues.append(issue)
        if status is Status.DONE and issue.resolved_at:
            events.append(
                Event(issue_id=issue.id, type=EventType.STATUS_CHANGED, at=issue.resolved_at,
                      actor=issue.assignee, data={"from": "in_progress", "to": "done"})
            )  # fmt: skip
        return issue

    # Hand-placed storyline issues ------------------------------------------------------------
    stale = add("BCK", "m1", Status.IN_PROGRESS, assignee="Ben R.", estimate=5, updated_ago=24,
                created_ago=40, title="Replace legacy session store")  # fmt: skip
    x1 = add("BCK", "m1", Status.BLOCKED, assignee="Chen W.", estimate=5, updated_ago=3,
             title="Cut tenant onboarding over to new sessions")  # fmt: skip
    x2 = add("BCK", "m2", Status.TODO, assignee=None, estimate=8, updated_ago=6,
             title="Migrate billing webhooks to the new platform")  # fmt: skip
    x3 = add("BCK", "m2", Status.TODO, assignee="Dmitri S.", estimate=5, updated_ago=5,
             title="Retire the legacy API gateway routes")  # fmt: skip
    x4 = add("MOB", "m3", Status.TODO, assignee="Elena V.", estimate=8, updated_ago=4,
             title="Switch the mobile app to the new gateway")  # fmt: skip
    p2 = add(
        "BCK",
        "m1",
        Status.IN_PROGRESS,
        assignee="Ben R.",
        estimate=3,
        title="Ship search indexer v2",
    )
    b2 = add("MOB", "m1", Status.BLOCKED, assignee="Grace O.", estimate=3, updated_ago=2,
             title="Search results screen on indexer v2")  # fmt: skip
    quiet = add(
        "MOB", "m2", Status.IN_PROGRESS, assignee="Farid M.", updated_ago=13, created_ago=30
    )

    # Bulk issues -----------------------------------------------------------------------------
    for _ in range(14):
        add("BCK", "m0", Status.DONE, resolved_ago=rng.uniform(22, 55))
    for _ in range(6):
        add("MOB", "m0", Status.DONE, resolved_ago=rng.uniform(22, 55))
    for _ in range(9):
        add(rng.choice(["BCK", "BCK", "MOB"]), "m1", Status.DONE, resolved_ago=rng.uniform(1, 30))
    for _ in range(3):
        add("BCK", "m1", Status.IN_PROGRESS, assignee="Ben R.")  # Ben is overloaded
    add(rng.choice(["BCK", "MOB"]), "m1", Status.TODO)
    creep = [
        add(
            rng.choice(["BCK", "MOB"]),
            "m1",
            Status.TODO,
            created_ago=rng.uniform(1, 11),
            updated_ago=0.5,
        )
        for _ in range(5)
    ]
    for issue in creep:
        events.append(Event(issue_id=issue.id, type=EventType.SCOPE_ADDED,
                            at=issue.created_at, actor="Product", data={"milestone": "m1"}))  # fmt: skip
    for _ in range(3):
        add(rng.choice(["BCK", "MOB"]), "m2", Status.DONE, resolved_ago=rng.uniform(2, 20))
    for _ in range(2):
        add(rng.choice(["BCK", "MOB"]), "m2", Status.IN_PROGRESS)
    for n in range(10):
        late = n < 3  # a few items were added after planning
        add(
            rng.choice(["BCK", "BCK", "MOB"]),
            "m2",
            Status.TODO,
            created_ago=rng.uniform(2, 12) if late else None,
            updated_ago=1 if late else None,
        )
    add("MOB", "m3", Status.DONE, resolved_ago=4)
    for _ in range(2):
        add("MOB", "m3", Status.IN_PROGRESS)
    for n in range(9):
        late = n < 2
        add(
            "MOB",
            "m3",
            Status.TODO,
            created_ago=rng.uniform(2, 9) if late else None,
            updated_ago=1 if late else None,
        )

    # Dependencies (kept acyclic) -------------------------------------------------------------
    graph: nx.DiGraph = nx.DiGraph()
    dependencies: list[Dependency] = []

    def link(blocker: Issue, blocked: Issue) -> bool:
        if blocker.id == blocked.id or graph.has_edge(blocker.id, blocked.id):
            return False
        if (
            graph.has_node(blocker.id)
            and graph.has_node(blocked.id)
            and nx.has_path(graph, blocked.id, blocker.id)
        ):
            return False
        graph.add_edge(blocker.id, blocked.id)
        dependencies.append(Dependency(blocker_id=blocker.id, blocked_id=blocked.id))
        return True

    for a, b in [(stale, x1), (x1, x2), (x2, x3), (x3, x4), (p2, b2)]:
        link(a, b)
    open_bck = [
        i
        for i in issues
        if i.is_open and i.project_id == "bck" and i not in (stale, x1, x2, x3, p2)
    ]
    open_mob = [
        i for i in issues if i.is_open and i.project_id == "mob" and i not in (x4, b2, quiet)
    ]
    for blocker, blocked in zip(rng.sample(open_bck, 4), rng.sample(open_mob, 4), strict=True):
        link(blocker, blocked)  # unresolved cross-team dependencies
    open_issues = [i for i in issues if i.is_open]
    done_issues = [i for i in issues if not i.is_open]
    for _ in range(40):
        if len([d for d in dependencies]) >= 22:
            break
        link(rng.choice(open_issues), rng.choice(open_issues))
    for _ in range(5):
        link(rng.choice(done_issues), rng.choice(open_issues))

    return Dataset(
        program=ProgramInfo(
            id="atlas",
            name="Atlas Platform Migration",
            description="Synthetic demo: moving a monolith to a multi-tenant platform, with a mobile client.",
        ),
        as_of=now,
        projects=projects,
        milestones=milestones,
        issues=issues,
        dependencies=dependencies,
        events=events,
    )
