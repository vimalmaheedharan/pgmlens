# Writing a connector

Subclass `pgmlens_connectors.base.Connector`, return a `Dataset`, and register it:

```toml
[project.entry-points."pgmlens.connectors"]
myco = "mypkg.connector:MyConnector"
```

Use `HttpSession` for retries, keep credentials in `SecretStr`, and test with `httpx.MockTransport`.
