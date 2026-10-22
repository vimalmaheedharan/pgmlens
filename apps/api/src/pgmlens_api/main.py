"""PGM Lens API.

Run it: ``uvicorn pgmlens_api.main:app``. With no configuration it serves the built-in
synthetic demo program, so the dashboard works the moment it starts.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pgmlens_connectors import available_connectors
from pgmlens_core import AnalysisResult, Dataset, RuleSet, __version__, analyze, load_rules
from pgmlens_core.demo import generate_demo
from pgmlens_reporting import build_briefing, render_markdown

from .schemas import BriefingOut, Health, ProgramDetail, ProgramSummary
from .settings import Settings
from .store import ProgramExistsError, ProgramStore, StoredProgram
from .telemetry import setup_telemetry
from .views import detail, summarize

log = logging.getLogger("pgmlens.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    rules = load_rules(settings.rules_path)
    store = ProgramStore(rules, persist_dir=settings.data_dir)

    if settings.data_dir and settings.data_dir.is_dir():
        for problem in store.load_directory(settings.data_dir):
            log.warning("Skipped dataset %s", problem)
    if settings.demo:
        store.add(generate_demo(as_of=datetime.now(UTC)), replace=True)

    app = FastAPI(
        title="PGM Lens API",
        version=__version__,
        description="Program intelligence: health, forecasts, risks and dependency analysis.",
    )
    app.state.store = store
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    setup_telemetry(app)

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        """Mutating endpoints need a bearer token when PGMLENS_API_TOKEN is set."""
        if settings.api_token is None:
            return
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not secrets.compare_digest(supplied.encode(), settings.api_token.encode()):
            raise HTTPException(
                401, "Missing or invalid bearer token", headers={"WWW-Authenticate": "Bearer"}
            )

    def find(program_id: str) -> StoredProgram:
        stored = store.get(program_id)
        if stored is None:
            raise HTTPException(404, f"No program with id {program_id!r}")
        return stored

    @app.get("/api/health", response_model=Health, tags=["meta"])
    def health() -> Health:
        return Health(status="ok", version=__version__, programs=len(store.list()))

    @app.get("/api/programs", response_model=list[ProgramSummary], tags=["programs"])
    def list_programs() -> list[ProgramSummary]:
        return [summarize(s) for s in store.list()]

    @app.get("/api/programs/{program_id}", response_model=ProgramDetail, tags=["programs"])
    def get_program(program_id: str) -> ProgramDetail:
        return detail(find(program_id))

    @app.post(
        "/api/programs",
        response_model=ProgramSummary,
        status_code=201,
        dependencies=[Depends(require_token)],
        tags=["programs"],
    )
    def register_program(dataset: Dataset, replace: bool = False) -> ProgramSummary:
        try:
            stored = store.add(dataset, replace=replace, persist=True)
        except ProgramExistsError:
            raise HTTPException(
                409, f"Program {dataset.program.id!r} already exists; pass ?replace=true"
            ) from None
        return summarize(stored)

    @app.delete(
        "/api/programs/{program_id}",
        status_code=204,
        dependencies=[Depends(require_token)],
        tags=["programs"],
    )
    def delete_program(program_id: str) -> Response:
        if not store.delete(program_id):
            raise HTTPException(404, f"No program with id {program_id!r}")
        return Response(status_code=204)

    @app.get("/api/programs/{program_id}/briefing", response_model=BriefingOut, tags=["programs"])
    def get_briefing(
        program_id: str,
        llm: Annotated[
            bool, Query(description="Phrase the briefing with the configured LLM.")
        ] = False,
    ) -> BriefingOut:
        stored = find(program_id)
        model = settings.llm_model if llm else None
        briefing = build_briefing(stored.analysis, stored.dataset, model=model)
        if llm and not settings.llm_model:
            briefing.warnings.append(
                "No LLM is configured (PGMLENS_LLM_MODEL); showing the deterministic briefing."
            )
        return BriefingOut(briefing=briefing, markdown=render_markdown(briefing))

    @app.post("/api/analyze", response_model=AnalysisResult, tags=["analysis"])
    def analyze_dataset(dataset: Dataset) -> AnalysisResult:
        """Stateless analysis: nothing is stored."""
        return analyze(dataset, store.rules)

    @app.get("/api/rules", response_model=RuleSet, tags=["analysis"])
    def get_rules() -> RuleSet:
        return store.rules

    @app.get("/api/connectors", tags=["meta"])
    def list_connectors() -> list[dict[str, Any]]:
        return [
            {"name": name, "class": cls.__name__}
            for name, cls in sorted(available_connectors().items())
        ]

    if settings.web_dir and settings.web_dir.is_dir():
        # Mounted last so it never shadows /api. The dashboard uses hash routing.
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")

    return app


app = create_app()
