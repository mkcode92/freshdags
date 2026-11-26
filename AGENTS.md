# Working on freshdags

freshdags is a CLI that flags docs that may have drifted from the files they describe. `Readme.md` is its user documentation; keep it exact.

## Keeping docs fresh

`freshdags.json` records which docs describe which files (https://github.com/mkcode92/freshdags).

- When `freshdags check` or the pre-commit hook reports drift, read each doc against its
  `git diff` and fix what the change made wrong. Run commands to see their output; do not guess.
- Resolve only a doc you read and found still correct: `freshdags resolve DOC --note "why"`.
  Never resolve just to make a check, hook or CI pass.
- When a doc starts describing another file: `freshdags add DOC SOURCE`.
- Never edit `freshdags.json` by hand or commit with `--no-verify`.

Here, run freshdags from the working copy: `uv run freshdags check`. Settings are `on-change`, so saving a file is enough to flag or resolve.

## Development

```sh
uv sync
uv run pre-commit install   # runs `freshdags check --uncommitted` before each commit
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

- `src/freshdags/api.py` defines every command as a method of `FreshdagsApi`; `core.py` implements it, `cli.py` only parses arguments and calls it, `render.py` formats results. The HTML page is `src/freshdags/templates/graph.html`.
- Tests call `FreshdagsApi` directly on a throwaway git repository (`tests/support.py`, `GitRepo`) and read `freshdags.json` as plain JSON. Pin wall-clock times with the `time_machine` fixture and commit dates with `GitRepo.commit(date=...)`.
- A change to the `freshdags.json` format bumps `GRAPH_VERSION` in `models.py` and adds an upgrade to `UPGRADES`; older files must keep working.
- Examples in `Readme.md` show real output: generate them, do not write them by hand.
- Every file in `src/freshdags/` ships in the wheel and sdist, tracked by git or not. Keep notes and drafts outside it.
