"""PGM Lens reporting: briefings where every claim is tied to computed evidence."""

from .briefing import Briefing, BriefingDraft, Claim, Section, build_briefing, validate_draft
from .facts import Fact, build_facts
from .render import render_markdown

__all__ = [
    "Briefing",
    "BriefingDraft",
    "Claim",
    "Fact",
    "Section",
    "build_briefing",
    "build_facts",
    "render_markdown",
    "validate_draft",
]
