"""API response models: the engines' output, shaped for a UI."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pgmlens_core import AnalysisResult, Finding, ForecastResult, ProgramHealth, Stats
from pgmlens_reporting import Briefing
from pydantic import BaseModel


class ProgramSummary(BaseModel):
    id: str
    name: str
    description: str
    as_of: datetime
    health: ProgramHealth
    stats: Stats
    next_milestone: ForecastResult | None
    top_risks: list[Finding]


class IssueOut(BaseModel):
    id: str
    key: str
    title: str
    status: Literal["todo", "in_progress", "blocked", "done"]
    assignee: str | None
    project_id: str
    milestone_id: str | None
    estimate: float | None
    url: str | None
    days_since_update: int
    critical: bool
    waiting: bool  # has at least one open blocker


class MilestoneOut(BaseModel):
    id: str
    name: str
    due_date: date | None
    open_issues: int
    total_issues: int


class ProjectOut(BaseModel):
    id: str
    key: str
    name: str


class EdgeOut(BaseModel):
    source: str
    target: str
    critical: bool
    unresolved: bool


class GraphView(BaseModel):
    nodes: list[str]
    edges: list[EdgeOut]
    critical_path: list[str]


class ProgramDetail(BaseModel):
    summary: ProgramSummary
    analysis: AnalysisResult
    issues: list[IssueOut]
    milestones: list[MilestoneOut]
    projects: list[ProjectOut]
    graph: GraphView


class BriefingOut(BaseModel):
    briefing: Briefing
    markdown: str


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    programs: int
