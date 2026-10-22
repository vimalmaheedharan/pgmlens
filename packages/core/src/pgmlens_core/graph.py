"""Dependency-graph analysis: critical path, blocked chains, cycles, coupling.

Edges point from blocker to blocked (work flows along the arrows). Everything here is
computed on the *open* subgraph, since finished work can no longer delay anything.
"""

from __future__ import annotations

from collections import Counter

import networkx as nx
from pydantic import BaseModel, Field

from .models import Dataset, Issue

DEFAULT_ESTIMATE = 1.0  # used when an issue has no estimate


def remaining_work(issue: Issue) -> float:
    """Remaining effort for an issue in estimate units (0 once done)."""
    if not issue.is_open:
        return 0.0
    return issue.estimate if issue.estimate is not None else DEFAULT_ESTIMATE


class CriticalPath(BaseModel):
    issue_ids: list[str] = Field(default_factory=list)
    length: float = 0.0


class BlockedIssue(BaseModel):
    issue_id: str
    depth: int = Field(description="Length of the longest chain of open blockers above this issue.")
    direct_blocker_ids: list[str]
    root_blocker_ids: list[str]


class RootBlocker(BaseModel):
    """An open issue that blocks others but is not itself waiting on anything."""

    issue_id: str
    downstream_count: int
    max_depth: int


class Coupling(BaseModel):
    blocker_project_id: str
    blocked_project_id: str
    edges: int
    unresolved: int


class GraphAnalysis(BaseModel):
    critical_path: CriticalPath = Field(default_factory=CriticalPath)
    milestone_paths: dict[str, CriticalPath] = Field(default_factory=dict)
    blocked: list[BlockedIssue] = Field(default_factory=list)
    root_blockers: list[RootBlocker] = Field(default_factory=list)
    cycles: list[list[str]] = Field(default_factory=list)
    coupling: list[Coupling] = Field(default_factory=list)

    @property
    def critical_issue_ids(self) -> set[str]:
        ids = set(self.critical_path.issue_ids)
        for path in self.milestone_paths.values():
            ids.update(path.issue_ids)
        return ids


def build_graph(ds: Dataset) -> nx.DiGraph:
    g: nx.DiGraph = nx.DiGraph()
    g.add_nodes_from(i.id for i in ds.issues)
    g.add_edges_from((d.blocker_id, d.blocked_id) for d in ds.dependencies)
    return g


def _open_subgraph(ds: Dataset, g: nx.DiGraph) -> nx.DiGraph:
    open_ids = [i.id for i in ds.issues if i.is_open]
    return g.subgraph(open_ids).copy()


def _break_cycles(g: nx.DiGraph) -> tuple[nx.DiGraph, list[list[str]]]:
    """Return an acyclic copy of ``g`` plus the cycles that had to be cut."""
    dag = g.copy()
    cycles: list[list[str]] = []
    while True:
        try:
            cycle = nx.find_cycle(dag)
        except nx.NetworkXNoCycle:
            break
        cycles.append([edge[0] for edge in cycle])
        dag.remove_edge(cycle[-1][0], cycle[-1][1])
    return dag, cycles


def _longest_path(dag: nx.DiGraph, weights: dict[str, float]) -> CriticalPath:
    if dag.number_of_nodes() == 0:
        return CriticalPath()
    dist: dict[str, float] = {}
    prev: dict[str, str | None] = {}
    for node in nx.topological_sort(dag):
        best = max(dag.predecessors(node), key=lambda p: (dist[p], p), default=None)
        prev[node] = best
        dist[node] = weights[node] + (dist[best] if best is not None else 0.0)
    end = max(dist, key=lambda n: (dist[n], n))
    path: list[str] = []
    cursor: str | None = end
    while cursor is not None:
        path.append(cursor)
        cursor = prev[cursor]
    path.reverse()
    return CriticalPath(issue_ids=path, length=round(dist[end], 2))


def _scoped(dag: nx.DiGraph, ds: Dataset, milestone_ids: set[str]) -> nx.DiGraph:
    """Open issues in the given milestones plus everything upstream that must finish first."""
    seeds = {i.id for i in ds.issues if i.is_open and i.milestone_id in milestone_ids}
    nodes = set(seeds)
    for seed in seeds:
        nodes.update(nx.ancestors(dag, seed))
    return dag.subgraph(nodes).copy()


def analyze_graph(ds: Dataset) -> GraphAnalysis:
    full = build_graph(ds)
    open_graph = _open_subgraph(ds, full)
    dag, cycles = _break_cycles(open_graph)
    weights = {i.id: remaining_work(i) for i in ds.issues}

    result = GraphAnalysis(cycles=cycles)
    result.critical_path = _longest_path(dag, weights)

    for milestone in ds.milestones:
        scoped = _scoped(dag, ds, {milestone.id})
        if scoped.number_of_nodes():
            result.milestone_paths[milestone.id] = _longest_path(scoped, weights)

    # Blocked chains: depth and root blockers via DP over the DAG.
    depth: dict[str, int] = {}
    roots: dict[str, set[str]] = {}
    for node in nx.topological_sort(dag):
        preds = list(dag.predecessors(node))
        if not preds:
            depth[node] = 0
            roots[node] = {node}
        else:
            depth[node] = 1 + max(depth[p] for p in preds)
            roots[node] = set().union(*(roots[p] for p in preds))
    for node in sorted(dag.nodes):
        if depth[node] >= 1:
            result.blocked.append(
                BlockedIssue(
                    issue_id=node,
                    depth=depth[node],
                    direct_blocker_ids=sorted(dag.predecessors(node)),
                    root_blocker_ids=sorted(roots[node]),
                )
            )
    for node in sorted(dag.nodes):
        if depth[node] == 0 and dag.out_degree(node) > 0:
            downstream = nx.descendants(dag, node)
            sub = dag.subgraph({node, *downstream})
            result.root_blockers.append(
                RootBlocker(
                    issue_id=node,
                    downstream_count=len(downstream),
                    max_depth=nx.dag_longest_path_length(sub),
                )
            )

    # Cross-project coupling over edges that still constrain open work.
    edges: Counter[tuple[str, str]] = Counter()
    unresolved: Counter[tuple[str, str]] = Counter()
    for dep in ds.dependencies:
        blocker = ds.issue_by_id[dep.blocker_id]
        blocked = ds.issue_by_id[dep.blocked_id]
        if not blocked.is_open or blocker.project_id == blocked.project_id:
            continue
        key = (blocker.project_id, blocked.project_id)
        edges[key] += 1
        if blocker.is_open:
            unresolved[key] += 1
    for (src, dst), count in sorted(edges.items()):
        result.coupling.append(
            Coupling(
                blocker_project_id=src,
                blocked_project_id=dst,
                edges=count,
                unresolved=unresolved[(src, dst)],
            )
        )
    return result
