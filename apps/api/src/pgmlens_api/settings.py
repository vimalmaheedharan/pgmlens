"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path | None = None
    demo: bool = True
    rules_path: Path | None = None
    llm_model: str | None = None
    api_token: str | None = None
    web_dir: Path | None = None
    cors_origins: tuple[str, ...] = field(default_factory=lambda: ("http://localhost:5173",))

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env

        def path(name: str) -> Path | None:
            return Path(env[name]) if env.get(name) else None

        data_dir = path("PGMLENS_DATA_DIR")
        has_data = data_dir is not None and data_dir.is_dir() and any(data_dir.glob("*.json"))
        demo_default = "0" if has_data else "1"
        return cls(
            data_dir=data_dir,
            demo=env.get("PGMLENS_DEMO", demo_default).lower() in {"1", "true", "yes"},
            rules_path=path("PGMLENS_RULES"),
            llm_model=env.get("PGMLENS_LLM_MODEL") or None,
            api_token=env.get("PGMLENS_API_TOKEN") or None,
            web_dir=path("PGMLENS_WEB_DIR"),
            cors_origins=tuple(
                o.strip()
                for o in env.get("PGMLENS_CORS_ORIGINS", "http://localhost:5173").split(",")
                if o.strip()
            ),
        )
