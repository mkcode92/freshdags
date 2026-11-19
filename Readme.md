# freshdags

A small CLI that helps prevent documentation drift — especially in codebases where agents change code faster than anyone re-reads the docs.

> Status: early setup. The commands below describe the planned design.

## Idea

freshdags keeps a dependency graph (a DAG) between documents and the things they describe:

- **Nodes** are usually file paths in the directory in scope, each with a timestamp. External sources (an upstream API spec, a vendor doc) can be declared as named nodes without a file.
- **Edges** say "this doc depends on that source".
- Given a git commit or PR, freshdags checks that every dependent is newer than what it depends on. If a source changed after its doc, the doc is flagged as a drift risk. A user or agent clears the flag after checking the doc.

## Planned commands

- add and remove dependency edges
- display the current structure
- check a commit or PR for drift risk

## Recommended practice

Point documentation at interfaces and APIs, not implementation files. If docs depend on implementation details, every refactor flags them and the signal turns into noise.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run freshdags --help
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
