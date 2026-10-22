# Contributing

1. `make setup` (needs [uv](https://docs.astral.sh/uv/) and Node 20+).
2. `make test` and `make lint` must pass.
3. Keep changes focused; add a test with every behavior change.

Good first areas: new risk rules (`packages/core/src/pgmlens_core/risk.py` + `rules/default.yaml`),
new connectors (subclass `Connector`, register under the `pgmlens.connectors` entry-point group).

Connectors must keep secrets in `SecretStr`, never log tokens, and have tests using `httpx.MockTransport`.

By contributing you agree your work is licensed under Apache-2.0.
