# Security

Please report vulnerabilities privately using GitHub's "Report a vulnerability" (Security tab) on this
repository. Do not open public issues for security problems.

Notes for operators:
- Set `PGMLENS_API_TOKEN` to protect write endpoints; put the service behind TLS.
- Connector credentials are only read by the CLI/your own jobs; the API never accepts them.
- LLM briefings send fact text (issue titles, names) to your configured model provider.
