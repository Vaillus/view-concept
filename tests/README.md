# tests

The pytest suite, one file per module of [`src/view_concept/`](../src/view_concept/README.md) that has tests (`test_api.py` for `server.py`), plus `test_params.py` for the session's `params.json`, read and written across `store.py`, `server.py` and `context.py`; no test drives a browser or a real agent.

## Files

`conftest.py` gives the `session` fixture, a session with two sections and one lexicon term in a temporary folder, and points the files of `launch.py` and `push.py` at the test's folder, so no test writes to `~/.view-concept`.

## Usage

```bash
uv run pytest
```
