# Working on freshdags

freshdags is a CLI that flags docs that may have drifted from the files they describe. `Readme.md` is its user documentation; keep it exact.

## Keeping docs fresh

This repository records which docs depend on which files in `freshdags.json`
(see https://github.com/mkcode92/freshdags).

- After changing files, run `freshdags check`. It lists every doc that may have
  drifted, with a `git diff` command for each changed source.
- For each drifted doc: run that `git diff`, read the doc, and fix every statement,
  example and command output the change made wrong. Run commands to see their
  output; do not guess it.
- Run `freshdags resolve DOC` only after reading the doc and finding it still
  correct. Never resolve just to make the check pass.
- When a doc starts describing another file, record it: `freshdags add DOC SOURCE`.
- Never edit `freshdags.json` by hand, and never skip the pre-commit hook
  (`git commit --no-verify`).
- A passing `freshdags check` means every doc was updated or reviewed after its
  sources changed, not that it is correct. Its content is your responsibility.

In this repository, run freshdags from the working copy: `uv run freshdags check`.
Settings are `on-change`, so saving a file is enough to flag or resolve.

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
