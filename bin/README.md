# bin

`view-concept`, a shell script that runs the `view-concept` command from this checkout with `uv run --project`, so the Claude Code plugin needs no separate install. Its environment is cached in `~/.cache/view-concept/`; without `uv` on the PATH it exits with code 127.
