# freshdags 🦡✨

A small CLI that helps prevent documentation drift — especially in codebases where agents change code faster than anyone re-reads the docs. It works just as well for keeping any file consistent with the specs and invariants it depends on.

> **Status:** early. All commands below work, but the file format may still change. Until v0.1.0 is on PyPI, install from GitHub (see below); the pre-commit and CI snippets need that release.

## Install

```sh
uv tool install freshdags   # or: pipx install freshdags
```

Until the first release on PyPI, install from GitHub instead: `uv tool install git+https://github.com/mkcode92/freshdags`.

## Quick start

Tell freshdags which docs depend on which files. They must be tracked by git; `git add` new files first:

```sh
freshdags add docs/api.md src/api/interface.py
freshdags add README.md docs/api.md
```

This creates `freshdags.json` in the repository root. Commit it with your code.

Later, someone changes `src/api/interface.py` and commits. Now:

```sh
$ freshdags check
docs/api.md drifted
  src/api/interface.py changed since 3f2a91c
    review: git diff 3f2a91c..HEAD -- src/api/interface.py
  then: update docs/api.md, or run: freshdags resolve docs/api.md

🦡 1 doc drifted. The badger is watching.
```

Read the diff, then either:

- **update the doc and commit it** — that clears the flag. Because the doc changed, `README.md` is flagged next, and you check it the same way; or
- **run `freshdags resolve docs/api.md`** if the doc is still correct. Nothing changed, so `README.md` stays fresh.

```sh
$ freshdags check
🦡✨ All 2 docs are fresh.
```

## Everyday use

**A change was minor and no doc needs updating.** Resolve every drifted doc at once:

```sh
freshdags resolve --all
```

**Something changed that git cannot see** — a vendor API, or a behaviour change that did not touch the file a doc depends on:

```sh
freshdags flag ext:stripe-api --note "API v2 released"
freshdags flag src/api/interface.py --note "timeouts now in seconds"
```

**See what depends on what:**

```sh
freshdags show                   # the whole graph
freshdags show src/api/interface.py   # its sources and dependents
```

**Stop drift before it is committed** with [pre-commit](https://pre-commit.com). Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/mkcode92/freshdags
    rev: v0.1.0
    hooks:
      - id: freshdags
```

The hook runs `freshdags check --uncommitted`: the changes you are committing count as a commit made now, so a source change without its doc update fails the commit. It also fails while older drift is still open.

**Check a pull request in CI**, for drift that was committed anyway. `check` exits with `1` when something drifted. It needs the git history, so fetch it fully:

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
- uses: astral-sh/setup-uv@v6
- run: uvx freshdags check
```

**Work with agents.** Run `freshdags configure --auto-flag on-change --auto-resolve on-change` (see [Settings](#settings)), so drift shows up as soon as a file is saved, before anything is committed. Agents can read `freshdags check --json`.

## What to track

**Point docs at interfaces, not implementations.** If a doc depends on implementation details, every refactor flags it and the signal turns into noise. Keep APIs and interfaces in their own files and make docs depend on those.

**Not only docs.** "Doc" and "source" are just roles. Any file can depend on any other, in any direction, as long as there are no cycles. That makes freshdags useful for invariant-based coding too, wherever one file must stay consistent with another:

- an implementation depends on the spec or invariant it must satisfy;
- a client depends on the server's API schema;
- tests depend on the interface they pin down;
- a migration or config depends on the model it mirrors.

**Things outside the repository** are written as `ext:<name>`. They are the only nodes without a tracked file:

- **External doc**, e.g. a wiki page that describes repo code: a code change flags it. After updating the page, run `freshdags resolve ext:wiki-api`. Resolve it once right after adding it, since it has no commits.
- **External source**, e.g. a vendor API: freshdags cannot see it change, so run `freshdags flag ext:stripe-api` when it does.

## Commands

| Command | Purpose |
|---|---|
| `freshdags add DOC SOURCE...` | Record that DOC depends on each SOURCE. Creates `freshdags.json` if needed. Refuses missing or untracked files, self-dependencies and cycles. |
| `freshdags rm DOC SOURCE...` | Remove those dependencies, and nodes no longer connected to anything. |
| `freshdags show [NODE]` | Print the graph, or one node's sources and dependents. |
| `freshdags check [REV] [--json] [--uncommitted]` | List every drifted doc. Without `REV`, uses the current `freshdags.json`, the history up to `HEAD` and, in `on-change` mode, uncommitted changes; with `REV`, evaluates the graph as of that commit. `--uncommitted` counts uncommitted changes as a commit made now, for pre-commit hooks. |
| `freshdags resolve DOC...` | Mark docs as drift-free after reviewing them. |
| `freshdags resolve --all` | Resolve every drifted doc, when the change needed no doc update. |
| `freshdags flag NODE [--note TEXT]` | Record that a source changed, flagging the docs that depend on it. |
| `freshdags configure [--auto-flag MODE] [--auto-resolve MODE]` | Show the settings, or change them. |

**Exit codes:** `0` no drift, `1` drift found, `2` usage or graph-file error.

**Verbosity:** by default, commands print only their results (the `check` report, `show`) and errors. The options go before the command, as in `freshdags -q check`. `-v` adds confirmations such as "docs/api.md depends on src/api.py"; `-vv` adds diagnostics like the git commands run. `-q` prints nothing but errors, for hooks and CI that only need the exit code. Confirmations and diagnostics go to stderr, so `--json` output stays clean.

## Settings

Settings live in `freshdags.json`. Show them with `freshdags configure`, change them with e.g. `freshdags configure --auto-flag on-change --auto-resolve on-change`. They decide what happens automatically; the `flag` and `resolve` commands work in every mode.

| Setting | `on-commit` (default) | `on-change` | `off` |
|---|---|---|---|
| `auto-flag` | A commit to a source flags its dependents. | Also an uncommitted save. | Only `freshdags flag` marks a source as changed. |
| `auto-resolve` | A commit to a doc resolves it. | Also an uncommitted save. | Only `freshdags resolve` resolves a doc. |

- **`on-change`** suits agents, which see drift before they commit. Uncommitted changes are timed by the file's modification time; files whose content matches `HEAD` are ignored. `check REV` always uses committed history only.
- **`auto-resolve: on-commit` / `on-change`** means updating a doc resolves it, with no extra step. The trade-off: any edit, even a typo fix, clears the flag. The edit shows up in review next to the source change.
- **`auto-resolve: off`** makes every resolve an explicit, recorded decision.

## How it works

freshdags keeps your dependencies as a graph (a DAG) in `freshdags.json`. The rule is: **a doc must be at least as new as each of its sources.** If a source changed after the doc was last up to date, the doc is flagged until someone resolves it.

- **Times come from git:** a file's change time is the **author date** of the last commit that touched it. Author dates survive rebases, so rewriting a branch does not raise false flags. Because commits are the source of truth, a doc can be updated in a later commit of the same pull request.
- **A doc is up to date** from the commit that created it, from its last commit or save (as `auto-resolve` allows), or from its last `resolve` — whichever is latest. The `git diff` hint in `check` starts at that commit.
- **Changes ripple, resolves do not.** A real change to a doc flags the docs that depend on it. Resolving a doc only states that it is still correct, so its dependents stay as they are.

### The graph file

`freshdags.json` is written by the tool; you should not need to edit it by hand. Keys are sorted so diffs stay small. A source appears only in `depends_on` lists, unless it carries a `flagged` record. Only the latest `resolved` and `flagged` record per node is kept; git holds the history.

```json
{
  "nodes": {
    "docs/api.md": {
      "depends_on": ["ext:stripe-api", "src/api/interface.py"],
      "resolved": { "at": "2026-11-19T10:00:00Z", "by": "Jane Doe", "commit": "3f2a91c..." }
    },
    "ext:stripe-api": {
      "flagged": { "at": "2026-11-01T00:00:00Z", "by": "Jane Doe", "note": "API v2 released" }
    }
  },
  "settings": { "auto-flag": "on-commit", "auto-resolve": "on-commit" },
  "version": 1
}
```

**Format versions.** `version` changes only when the format changes in a breaking way. A newer freshdags reads older files and upgrades them; the next command that writes the file saves the new format, which shows up as a normal diff. An older freshdags refuses a newer file and asks you to upgrade.

## Known limitations

- `resolve` and `flag` record the current wall-clock time, while commits carry the author's machine time. Clock skew between machines can misorder events that happen within minutes of each other.
- In `on-change` mode, file modification times are compared with commit author dates, with the same caveat.

## Planned

- `--base REV` for `check`, to report only drift introduced by a pull request
- `show --format dot` for drawing the graph with Graphviz
- Directory and glob sources, so a per-directory README tracks new files automatically
- A ready-made snippet for `AGENTS.md` / `CLAUDE.md`

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pre-commit install   # freshdags checks its own docs before each commit
uv run freshdags --help
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

**Releasing:** bump `version` in `pyproject.toml`, commit, and push a tag like `v0.1.0`. The publish workflow checks that the tag matches the version, builds, and uploads to PyPI.

## License

[MIT](LICENSE)
