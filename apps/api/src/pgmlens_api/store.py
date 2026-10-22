"""In-memory program store with optional JSON persistence.

Datasets are analyzed once on registration. A database-backed store (Postgres, with scheduled
connector syncs) is the next milestone; this interface is what it will implement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from pgmlens_core import AnalysisResult, Dataset, RuleSet, analyze

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class StoredProgram:
    dataset: Dataset
    analysis: AnalysisResult


class ProgramExistsError(Exception):
    pass


class ProgramStore:
    def __init__(self, rules: RuleSet, persist_dir: Path | None = None) -> None:
        self._rules = rules
        self._persist_dir = persist_dir
        self._items: dict[str, StoredProgram] = {}
        self._lock = RLock()

    @property
    def rules(self) -> RuleSet:
        return self._rules

    def add(
        self, dataset: Dataset, *, replace: bool = False, persist: bool = False
    ) -> StoredProgram:
        program_id = dataset.program.id
        with self._lock:
            if program_id in self._items and not replace:
                raise ProgramExistsError(program_id)
            stored = StoredProgram(dataset=dataset, analysis=analyze(dataset, self._rules))
            self._items[program_id] = stored
        if persist and self._persist_dir is not None:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            (self._persist_dir / f"{_SAFE.sub('_', program_id)}.json").write_text(
                dataset.model_dump_json(indent=2), encoding="utf-8"
            )
        return stored

    def get(self, program_id: str) -> StoredProgram | None:
        with self._lock:
            return self._items.get(program_id)

    def list(self) -> list[StoredProgram]:
        with self._lock:
            return sorted(self._items.values(), key=lambda s: s.dataset.program.name.lower())

    def delete(self, program_id: str) -> bool:
        with self._lock:
            removed = self._items.pop(program_id, None) is not None
        if removed and self._persist_dir is not None:
            (self._persist_dir / f"{_SAFE.sub('_', program_id)}.json").unlink(missing_ok=True)
        return removed

    def load_directory(self, directory: Path) -> list[str]:
        """Load every ``*.json`` dataset in a directory; return problems instead of raising."""
        problems: list[str] = []
        for path in sorted(directory.glob("*.json")):
            try:
                self.add(Dataset.model_validate_json(path.read_text("utf-8")), replace=True)
            except Exception as exc:
                problems.append(f"{path.name}: {type(exc).__name__}")
        return problems
