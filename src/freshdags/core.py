"""The implementation of FreshdagsApi."""

import getpass
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from pydantic import ValidationError

from freshdags.api import FreshdagsApi
from freshdags.errors import (
    CycleError,
    FreshdagsError,
    GraphNotFoundError,
    SelfDependencyError,
    UnknownEdgeError,
    UnknownFileError,
    UnknownNodeError,
    UnsupportedVersionError,
)
from freshdags.git import Git, GitError
from freshdags.models import (
    GRAPH_FILE,
    GRAPH_VERSION,
    CheckReport,
    Drift,
    Flag,
    Graph,
    Mode,
    Node,
    NodeView,
    Resolution,
    Settings,
    is_external,
    upgrade,
)


def watches_commits(mode: Mode) -> bool:
    """Whether commits to a file count in this mode."""
    return mode in (Mode.ON_COMMIT, Mode.ON_CHANGE)


def watches_saves(mode: Mode) -> bool:
    """Whether uncommitted saves to a file count in this mode."""
    return mode is Mode.ON_CHANGE


def counting_saves(mode: Mode) -> Mode:
    """The mode for `check --uncommitted`: commits that are still pending count too."""
    return Mode.ON_CHANGE if mode is Mode.ON_COMMIT else mode


@dataclass(frozen=True)
class Moment:
    """A point in a node's history: when, and the commit if it was one."""

    at: datetime
    commit: str | None = None
    note: str | None = None


def latest(*moments: Moment | None) -> Moment | None:
    present = [m for m in moments if m is not None]
    return max(present, key=lambda m: m.at) if present else None


@dataclass
class History:
    """What git knows about the graph's files, up to one revision."""

    last: dict[str, Moment]
    """Latest commit touching each path (by author date)."""
    first: dict[str, Moment]
    """Commit that created each path (earliest author date)."""
    saved: dict[str, Moment]
    """Uncommitted changes, timed by file modification time. Empty when checking a rev."""


class Freshdags(FreshdagsApi):
    """freshdags for the git repository at `root`.

    `git` runs git commands; it is injectable so tests can isolate git config.
    """

    def __init__(self, root: Path, *, git: Git | None = None) -> None:
        self.root = root
        self.git = git or Git(root)

    @classmethod
    def discover(cls, start: Path) -> Self:
        """freshdags for the repository containing `start`."""
        try:
            root = Git(start).run("rev-parse", "--show-toplevel")
        except GitError as error:
            raise FreshdagsError(f"Not inside a git repository: {start}") from error
        return cls(Path(root))

    # --- editing the graph ------------------------------------------------------------------

    def add(self, doc: str, *sources: str) -> None:
        graph = self._load_or_new()
        doc = self._normalise(doc)
        names = [self._normalise(source) for source in sources]
        for name in (doc, *names):
            if not is_external(name) and not (self.root / name).is_file():
                raise UnknownFileError(name)
        if doc in names:
            raise SelfDependencyError(doc)
        for source in names:
            if cycle := self._path_between(graph, source, doc):
                raise CycleError([doc, *cycle])

        for name in (doc, *names):
            graph.nodes.setdefault(name, Node(external=is_external(name)))
        node = graph.nodes[doc]
        node.depends_on = Node(depends_on=[*node.depends_on, *names]).depends_on
        self._save(graph)

    def rm(self, doc: str, *sources: str) -> None:
        graph = self._load()
        doc = self._normalise(doc)
        names = [self._normalise(source) for source in sources]
        current = graph.nodes[doc].depends_on if doc in graph.nodes else []
        for source in names:
            if source not in current:
                raise UnknownEdgeError(doc, source)

        graph.nodes[doc].depends_on = [s for s in current if s not in names]
        used = {source for node in graph.nodes.values() for source in node.depends_on}
        graph.nodes = {
            name: node for name, node in graph.nodes.items() if node.depends_on or name in used
        }
        self._save(graph)

    def configure(
        self, *, auto_flag: Mode | None = None, auto_resolve: Mode | None = None
    ) -> Settings:
        graph = self._load_or_new()
        given = {"auto_flag": auto_flag, "auto_resolve": auto_resolve}
        changes = {key: value for key, value in given.items() if value}
        if changes or not self._graph_path.exists():
            graph.settings = graph.settings.model_copy(update=changes)
            self._save(graph)
        return graph.settings

    # --- reading the graph ------------------------------------------------------------------

    def graph(self) -> Graph:
        return self._load()

    def neighbours(self, node: str) -> NodeView:
        graph = self._load()
        name = self._require_node(graph, node)
        return NodeView(
            name=name,
            sources=graph.nodes[name].depends_on,
            dependents=sorted(doc for doc, n in graph.nodes.items() if name in n.depends_on),
        )

    # --- drift ------------------------------------------------------------------------------

    def check(self, rev: str | None = None, *, uncommitted: bool = False) -> CheckReport:
        if uncommitted and rev is not None:
            raise FreshdagsError("--uncommitted checks the working tree, not a revision.")
        graph = self._load(rev)
        settings = graph.settings
        if uncommitted:
            settings = Settings(
                auto_flag=counting_saves(settings.auto_flag),
                auto_resolve=counting_saves(settings.auto_resolve),
            )
        history = self._history(graph, rev, settings, saved_at=self._now() if uncommitted else None)
        drift = []
        docs = 0
        for doc, node in sorted(graph.nodes.items()):
            if not node.depends_on:
                continue
            docs += 1
            fresh = self._fresh(doc, node, history, settings.auto_resolve)
            for source in node.depends_on:
                changed = self._changed(source, graph.nodes[source], history, settings.auto_flag)
                if changed is None or (fresh is not None and changed.at <= fresh.at):
                    continue
                drift.append(
                    Drift(
                        doc=doc,
                        source=source,
                        doc_fresh_at=fresh.at if fresh else None,
                        doc_fresh_commit=fresh.commit if fresh else None,
                        source_changed_at=changed.at,
                        source_changed_commit=changed.commit,
                        note=changed.note,
                    )
                )
        return CheckReport(rev=rev, docs_checked=docs, drift=drift)

    def resolve(self, *docs: str) -> list[str]:
        graph = self._load()
        names = [self._require_node(graph, doc) for doc in docs]
        record = Resolution(at=self._now(), by=self._user(), commit=self._head())
        for name in names:
            graph.nodes[name].resolved = record
        self._save(graph)
        return names

    def resolve_all(self) -> list[str]:
        drifted = self.check().drifted_docs
        return self.resolve(*drifted) if drifted else []

    def flag(self, node: str, note: str | None = None) -> None:
        graph = self._load()
        name = self._require_node(graph, node)
        graph.nodes[name].flagged = Flag(at=self._now(), by=self._user(), note=note)
        self._save(graph)

    # --- freshness rules --------------------------------------------------------------------

    @staticmethod
    def _fresh(doc: str, node: Node, history: History, mode: Mode) -> Moment | None:
        """When `doc` was last up to date: created, edited (if edits resolve), or resolved."""
        resolved = node.resolved
        return latest(
            history.first.get(doc),
            history.last.get(doc) if watches_commits(mode) else None,
            history.saved.get(doc) if watches_saves(mode) else None,
            Moment(resolved.at, resolved.commit) if resolved else None,
        )

    @staticmethod
    def _changed(source: str, node: Node, history: History, mode: Mode) -> Moment | None:
        """When `source` last changed: committed or saved (if those count), or flagged."""
        flagged = node.flagged
        return latest(
            history.last.get(source) if watches_commits(mode) else None,
            history.saved.get(source) if watches_saves(mode) else None,
            Moment(flagged.at, None, flagged.note) if flagged else None,
        )

    # --- git --------------------------------------------------------------------------------

    log_batch_size = 200
    """Paths per `git log` call. Windows limits a command line to 32,767 characters."""

    def _history(
        self, graph: Graph, rev: str | None, settings: Settings, saved_at: datetime | None
    ) -> History:
        paths = sorted(name for name in graph.nodes if not is_external(name))
        last: dict[str, Moment] = {}
        first: dict[str, Moment] = {}
        tip = rev or (self._head() and "HEAD")
        for start in range(0, len(paths) if tip else 0, self.log_batch_size):
            batch = paths[start : start + self.log_batch_size]
            log = self.git.run(
                "-c", "core.quotepath=off", "--literal-pathspecs",
                "log", "--format=@@%H %aI", "--name-only", tip, "--", *batch,
            )  # fmt: skip
            moment: Moment | None = None
            for line in log.splitlines():
                if line.startswith("@@"):
                    sha, date = line[2:].split(" ")
                    moment = Moment(datetime.fromisoformat(date), sha)
                elif line and moment:
                    if line not in last or moment.at > last[line].at:
                        last[line] = moment
                    if line not in first or moment.at <= first[line].at:
                        first[line] = moment
        any_saves = watches_saves(settings.auto_flag) or watches_saves(settings.auto_resolve)
        saved = self._saved(paths, saved_at) if rev is None and any_saves else {}
        return History(last=last, first=first, saved=saved)

    def _saved(self, paths: list[str], at: datetime | None) -> dict[str, Moment]:
        """Uncommitted changes (modified or untracked) among `paths`.

        Timed by file modification time, or all at `at` when given: then they count as one
        pending commit, so their order does not matter.

        Asks for the whole working tree and filters here, so the command line stays short.
        """
        status = self.git.run(
            "status", "--porcelain=v1", "-z", "--untracked-files=all", strip=False
        )
        wanted = set(paths)
        entries = iter(status.split("\0"))
        saved = {}
        for entry in entries:
            if not entry:
                continue
            code, path = entry[:2], entry[3:]
            if code[0] in "RC":
                next(entries, None)  # the original path of a rename or copy
            file = self.root / path
            if path in wanted and file.is_file():
                saved[path] = Moment(at or datetime.fromtimestamp(file.stat().st_mtime, UTC))
        return saved

    def _head(self) -> str | None:
        try:
            return self.git.run("rev-parse", "--verify", "--quiet", "HEAD")
        except GitError:
            return None

    def _user(self) -> str:
        try:
            return self.git.run("config", "user.name") or getpass.getuser()
        except GitError:
            return getpass.getuser()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    # --- graph file -------------------------------------------------------------------------

    @property
    def _graph_path(self) -> Path:
        return self.root / GRAPH_FILE

    def _load(self, rev: str | None = None) -> Graph:
        if rev is None:
            if not self._graph_path.exists():
                raise GraphNotFoundError()
            text = self._graph_path.read_text(encoding="utf-8")
        else:
            self.git.run("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
            try:
                text = self.git.run("show", f"{rev}:{GRAPH_FILE}")
            except GitError as error:
                raise GraphNotFoundError() from error
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise FreshdagsError(f"{GRAPH_FILE} is not valid JSON: {error}") from error
        version = data.get("version") if isinstance(data, dict) else None
        if not isinstance(version, int) or version < 1:
            raise FreshdagsError(f"{GRAPH_FILE} has no valid version number.")
        if version > GRAPH_VERSION:
            raise UnsupportedVersionError(version, GRAPH_VERSION)
        try:
            return Graph.model_validate(upgrade(data))
        except ValidationError as error:
            raise FreshdagsError(f"{GRAPH_FILE} is invalid:\n{error}") from error

    def _load_or_new(self) -> Graph:
        return self._load() if self._graph_path.exists() else Graph()

    def _save(self, graph: Graph) -> None:
        self._graph_path.write_bytes(graph.to_json().encode("utf-8"))

    # --- names ------------------------------------------------------------------------------

    def _normalise(self, name: str) -> str:
        """`ext:` names as given; paths relative to the repository root, with `/`."""
        name = name.strip()
        if is_external(name):
            return name
        path = (Path.cwd() / name.replace("\\", "/")).resolve()
        try:
            return path.relative_to(self.root.resolve()).as_posix()
        except ValueError as error:
            raise FreshdagsError(f"Outside the repository: {name}") from error

    def _require_node(self, graph: Graph, node: str) -> str:
        name = self._normalise(node)
        if name not in graph.nodes:
            raise UnknownNodeError(name)
        return name

    @staticmethod
    def _path_between(graph: Graph, start: str, goal: str) -> list[str] | None:
        """A dependency path from `start` to `goal`, if one exists (depth-first)."""
        stack = [[start]]
        seen = set()
        while stack:
            path = stack.pop()
            if path[-1] == goal:
                return path
            if path[-1] in seen:
                continue
            seen.add(path[-1])
            node = graph.nodes.get(path[-1])
            stack.extend([*path, source] for source in (node.depends_on if node else []))
        return None
