"""PGM Lens core: normalized model plus pure graph, risk and forecast engines."""

from .analysis import AnalysisResult, ProgramHealth, Stats, analyze
from .forecast import ForecastResult
from .graph import GraphAnalysis, analyze_graph
from .models import (
    SCHEMA_VERSION,
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
from .risk import Finding, RuleSet, Severity, load_rules

__version__ = "0.1.0"

__all__ = [
    "SCHEMA_VERSION",
    "AnalysisResult",
    "Dataset",
    "Dependency",
    "Event",
    "EventType",
    "Finding",
    "ForecastResult",
    "GraphAnalysis",
    "Issue",
    "Milestone",
    "ProgramHealth",
    "ProgramInfo",
    "Project",
    "RuleSet",
    "Severity",
    "Stats",
    "Status",
    "analyze",
    "analyze_graph",
    "load_rules",
]
