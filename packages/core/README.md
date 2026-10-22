# pgmlens-core

The pure heart of PGM Lens. It takes a normalized `Dataset` in and returns findings,
forecasts and graph analysis out. **No network, no database, no clock** (time is passed in),
which makes it trivial to test, embed and run from a CLI.

```bash
pgmlens analyze examples/demo-dataset.json
pgmlens analyze data.json --format json --rules my-rules.yaml
pgmlens demo --out demo.json
pgmlens schema > dataset.schema.json
```

Modules:

| Module | Responsibility |
| --- | --- |
| `models` | Versioned, validated schema: Project, Milestone, Issue, Dependency, Event, Dataset |
| `graph` | Dependency graph, critical path, blocked chains, cycles, cross-project coupling |
| `forecast` | Monte Carlo forecast from historical throughput, with scope growth |
| `risk` | Declarative YAML rules evaluated by built-in evaluators |
| `analysis` | `analyze(dataset)` facade that ties it all together |
| `demo` | Seeded synthetic program for trying the tool without real data |
