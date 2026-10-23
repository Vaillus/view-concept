# tests

The pytest suite, one file per module of [`src/view_concept/`](../src/view_concept/README.md) that has tests (`test_api.py` for `server.py`); no test drives a browser or a real agent.

```bash
uv run pytest
```

`conftest.py` gives the `session` fixture, a session with two sections and one lexicon term in a temporary folder, and points the pending launches and the push subscriptions at the test's folder, so no test writes to `~/.view-concept`.
