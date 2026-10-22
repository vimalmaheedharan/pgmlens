# pgmlens-reporting

Executive briefings in which **the LLM explains and never invents**.

```python
from pgmlens_core import analyze
from pgmlens_reporting import build_briefing, render_markdown

briefing = build_briefing(analyze(dataset))  # deterministic, no LLM
briefing = build_briefing(
    analyze(dataset), model="gpt-4o-mini"
)  # any LiteLLM model, incl. ollama/...
print(render_markdown(briefing))
```

How the guardrail works:

1. The engines produce numbered **facts** (`F1`, `F2`, ...).
2. The LLM may only write claims that cite fact ids.
3. Every number and issue key in a claim must appear in the facts it cites.
4. A draft that fails is retried once with the reasons, then replaced by the deterministic
   briefing, with a visible warning.

Install the LLM extra with `pip install "pgmlens-reporting[llm]"`. Without it, briefings are
fully deterministic.
