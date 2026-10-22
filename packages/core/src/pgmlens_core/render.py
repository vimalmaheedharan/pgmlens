"""Plain-text rendering of an analysis, for the CLI and logs."""

from __future__ import annotations

from .analysis import AnalysisResult
from .dates import short_date
from .models import Dataset

_MARK = {"critical": "!!!", "high": "!! ", "medium": "!  ", "low": ".  "}


def _wrap(text: str, width: int = 96, indent: str = "      ") -> str:
    lines: list[str] = []
    line = ""
    for word in text.split():
        if line and len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return f"\n{indent}".join(lines)


def render_text(result: AnalysisResult, ds: Dataset | None = None) -> str:
    out: list[str] = []
    h = result.health
    s = result.stats
    out.append(f"{result.program.name}  |  as of {result.as_of:%Y-%m-%d}")
    out.append("=" * 72)
    out.append(h.headline.upper())
    out.append(
        f"{s.open} open / {s.done} done  ({s.in_progress} in progress, {s.blocked} blocked, "
        f"{s.unassigned_open} unassigned)"
    )
    out.append("")
    out.append("FORECAST")
    for fc in result.forecasts:
        due = f"due {short_date(fc.due_date)}" if fc.due_date else "no due date"
        prob = (
            f"{fc.on_time_probability:.0%} on time" if fc.on_time_probability is not None else "n/a"
        )
        out.append(f"  {fc.scope_name:<24} {due:<13} {prob:<12} {fc.summary}")
    out.append("")
    out.append(f"RISKS ({len(result.findings)})")
    if not result.findings:
        out.append("  None detected.")
    for f in result.findings:
        out.append(f"  [{_MARK[f.severity.value]}] {f.title}")
        out.append(f"      {_wrap(f.message)}")
        if f.action:
            out.append(f"      -> {_wrap(f.action)}")
    path = result.graph.critical_path
    if ds is not None and path.issue_ids:
        keys = " -> ".join(ds.issue_by_id[i].key for i in path.issue_ids)
        out.append("")
        out.append(f"CRITICAL PATH ({path.length:g} points): {keys}")
    return "\n".join(out)
