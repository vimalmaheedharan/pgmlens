# pgmlens-connectors

Pull delivery data from your tools into the normalized PGM Lens model.

| Connector | Status | Notes |
| --- | --- | --- |
| `jira` | MVP | Cloud (`/rest/api/3/search/jql`) and Data Center (`/rest/api/2/search`) |
| `github` | MVP | github.com and Enterprise Server; estimates from `size:`/`points:` labels; dependencies need the issue-dependencies API |
| `gitlab` | MVP | gitlab.com and self-managed; blocking links need a paid tier |

```python
from pgmlens_connectors import create_connector
from pgmlens_core import analyze

connector = create_connector(
    "jira",
    {
        "base_url": "https://your-domain.atlassian.net",
        "email": "you@example.com",
        "api_token": "...",  # use an environment variable, never commit tokens
        "project_keys": ["PLAT", "MOB"],
        "program_name": "Atlas",
    },
)
dataset = connector.fetch()
print(connector.warnings)
print(analyze(dataset).health.headline)
```

## Writing a connector

Subclass `Connector`, return a `Dataset`, and register it as an entry point so it is picked up
without any change to this repository:

```toml
[project.entry-points."pgmlens.connectors"]
linear = "pgmlens_linear:LinearConnector"
```

Keep the mapping from the vendor's JSON to `Dataset` in a pure function (see `map_issues` in
`jira.py`, `gitlab.py` and `github.py`) so it can be unit-tested from fixtures without network access.
