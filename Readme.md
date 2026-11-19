# freshdags

A small CLI that helps prevent documentation drift — especially in codebases where agents change code faster than anyone re-reads the docs.

> **Status:** design and tests are in place; the commands are not implemented yet. Everything below describes the intended behaviour.

## How it works

You record which docs depend on which sources. freshdags keeps these dependencies as a graph (a DAG) in `freshdags.json` at the repository root.

The rule is simple: **a doc must be at least as new as each of its sources.** If a source changed after a doc was last brought up to date, the doc is flagged as a drift risk until someone resolves it.

Times come from git: a file's change time is the **author date** of the last commit that touched it. Author dates survive rebases, so rewriting a branch does not raise false flags. Because commits are the source of truth, a doc can be updated in a later commit of the same pull request.

- **Nodes** are file paths relative to the repository root, or external nodes written as `ext:<name>` (a wiki page, a third-party API) that have no file.
- **Edges** mean "doc depends on source". A doc can itself be a source for other docs.
- **Changes ripple, resolves do not.** A real change to a doc flags the docs that depend on it. Resolving a doc only states that it is still correct, so its dependents stay as they are.

### The flow

1. A source changes — by a commit, or by `freshdags flag` for changes git cannot see.
2. `freshdags check` reports every doc that is now older than one of its sources.
3. Someone reviews the doc, updates it if needed, and runs `freshdags resolve` (or, with `resolve: on-commit`, just commits the update).

### External nodes

freshdags cannot see changes outside the repository.

- **External doc** (e.g. a wiki page depending on repo code): a code change flags it; after updating the page, run `freshdags resolve ext:wiki-api`.
- **External source** (e.g. a vendor API): when it changes, run `freshdags flag ext:stripe-api` to flag the docs that depend on it.

## Commands

| Command | Purpose |
|---|---|
| `freshdags add DOC SOURCE...` | Record that DOC depends on each SOURCE. Creates `freshdags.json` if needed. Refuses missing files, self-dependencies and cycles. |
| `freshdags rm DOC SOURCE...` | Remove those dependencies. Nodes left without any dependency are removed. |
| `freshdags show [NODE]` | Print the graph, or one node's sources and dependents. |
| `freshdags check [REV] [--json]` | List every drifted doc. Without `REV`, uses the current `freshdags.json` and working tree; with `REV`, evaluates the graph as of that commit. |
| `freshdags resolve DOC...` | Mark docs as drift-free after reviewing them. |
| `freshdags resolve --from SOURCE` | Resolve every doc that drifted because of SOURCE — for minor changes that need no doc update. |
| `freshdags flag NODE [--note TEXT]` | Record that a source changed, flagging the docs that depend on it. |

**Exit codes:** `0` no drift, `1` drift found, `2` usage or graph-file error. This makes `freshdags check` usable as a CI gate.

## Settings

Settings live in `freshdags.json`:

| Setting | `manual` | `on-commit` | `on-change` |
|---|---|---|---|
| `flag` (default `on-commit`) | Only `freshdags flag` marks a source as changed. | A commit to a source flags its dependents. | Also an uncommitted save. |
| `resolve` (default `manual`) | Only `freshdags resolve` resolves a doc. | A commit to a doc resolves it. | Also an uncommitted save. |

In every mode, a doc counts as up to date from the commit that created it until it is first resolved. An external doc has no commits, so resolve it once after adding it.

`on-change` suits agents, which see drift before they commit. Uncommitted changes are timed by the file's modification time; files whose content matches `HEAD` are ignored. `check REV` always evaluates committed history only.

`resolve` defaults to `manual`, so every resolve is an explicit decision. With `on-commit` or `on-change`, any edit to a doc — even a typo fix — counts as resolving it.

A doc edit is a real change, so it also flags the docs that depend on it. Only the `resolve` command leaves dependents untouched.

## Output

`check` tells you what changed, where to look and how to clear the flag:

```
docs/api.md drifted: src/api.py changed since 3f2a91c
  review:  git diff 3f2a91c..HEAD -- src/api.py
  then:    update docs/api.md, or run: freshdags resolve docs/api.md
```

The diff starts at the commit where the doc was last up to date, so you only read what changed since. For external sources, the note from `freshdags flag --note` is shown instead.

`check --json` prints the same report in machine-readable form for agents and tooling.

## The graph file

`freshdags.json` is written by the tool and committed with your code. Keys are sorted so diffs stay small. Only the latest `resolved` and `flagged` record per node is kept; git holds the history.

```json
{
  "nodes": {
    "docs/api.md": {
      "depends_on": ["ext:stripe-api", "src/api/interface.py"],
      "resolved": { "at": "2026-11-19T10:00:00Z", "by": "Jane Doe", "commit": "3f2a91c..." }
    },
    "ext:stripe-api": {
      "external": true,
      "flagged": { "at": "2026-11-01T00:00:00Z", "by": "Jane Doe", "note": "API v2 released" }
    },
    "src/api/interface.py": {}
  },
  "settings": { "flag": "on-commit", "resolve": "manual" },
  "version": 1
}
```

## Recommended practice

Point documentation at interfaces and APIs, not implementation files. If docs depend on implementation details, every refactor flags them and the signal turns into noise.

## Known limitations

- `resolve` and `flag` record the current wall-clock time, while commits carry the author's machine time. Clock skew between machines can misorder events that happen within minutes of each other.
- In `on-change` mode, wall-clock modification times are compared with commit author dates, with the same skew caveat.

## Planned

- `--base REV` for `check`, to report only drift introduced by a pull request
- `show --format dot` for drawing the graph with Graphviz
- Directory and glob sources, so a per-directory README tracks new files automatically
- A ready-made snippet for `AGENTS.md` / `CLAUDE.md` and example hooks

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run freshdags --help
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
