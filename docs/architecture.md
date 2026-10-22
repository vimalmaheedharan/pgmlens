# Architecture

Connectors → normalized `Dataset` → `analyze()` → API → dashboard.

- **Model** (`pgmlens_core.models`): Pydantic v2, schema-versioned, validated for referential integrity.
- **Graph** (`graph.py`): NetworkX over open issues; critical path, root blockers, cycles, cross-project coupling.
- **Forecast** (`forecast.py`): Monte Carlo resampling of the last 8 weeks of (done, added) pairs, seeded for reproducibility.
- **Risk** (`risk.py` + YAML rules): evaluators registered by `type`; health is off_track / at_risk / on_track.
- **Reporting**: deterministic facts F1…Fn; LLM claims must cite facts and are verified before use.
