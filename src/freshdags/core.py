"""The implementation of FreshdagsApi."""

import getpass
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
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
    UntrackedFileError,
)
from freshdags.git import Git, GitError
from freshdags.models import (
    GRAPH_FILE,
    GRAPH_VERSION,
    CheckReport,
    Commit,
    Drift,
    Flag,
    Graph,
    Mode,
    Node,
    NodeStatus,
    NodeView,
    Resolution,
    Settings,
    is_external,
    upgrade,
)

log = logging.getLogger(__name__)


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
    """A point in a node's history: a commit, an uncommitted save, a resolve or a flag."""

    at: datetime
    commit: str | None = None
    """The commit it was, or (for a resolve) was made on. Only these have a place in git's
    history; everything else can only be ordered by `at`."""
    note: str | None = None
    flagged: bool = False
    """Recorded by `freshdags flag`, not seen by git."""
    author: str | None = None
    """Author of the commit, if it was one."""
    subject: str | None = None
    """First line of the commit message, if it was one."""


def latest(*moments: Moment | None) -> Moment | None:
    present = [m for m in moments if m is not None]
    return max(present, key=lambda m: m.at) if present else None


@dataclass
class History:
    """What git knows about the graph's files, up to one revision: the tip."""

    tip: str | None
    """The revision checked, or HEAD; None in a repository without commits."""
    commits: dict[str, list[Moment]]
    """Every commit in the tip's history that touched each path, newest first (author date).
    A merge touched a path only where it changed it itself, as when resolving a conflict."""
    saved: dict[str, Moment]
    """Uncommitted changes, timed by file modification time. Empty when checking a rev."""

    def last_commit(self, path: str) -> Moment | None:
        commits = self.commits.get(path)
        return commits[0] if commits else None

    def creating_commit(self, path: str) -> Moment | None:
        """The oldest commit that touched `path`, which created it."""
        commits = self.commits.get(path)
        return commits[-1] if commits else None


@dataclass(frozen=True)
class DocReview:
    """Everything that brought a doc up to date: the evidence against changes to its sources.

    Each kind of change is held against the evidence that can order it (see `check`).
    """

    seen_commits: frozenset[str]
    """Commits the doc was written or reviewed on: the commit that created it, its later
    commits if `auto-resolve` counts them, and HEAD at its last resolve. The doc has seen
    these commits and every commit they descend from."""
    reviewed_content: dict[str, str]
    """Git blob hash of each source as the last resolve reviewed it."""
    saved: Moment | None
    """The doc's uncommitted save, if `auto-resolve` counts saves. It has no place in the
    history yet, so it covers the source commits made before it, by time."""
    last_update: Moment | None
    """The latest of the doc's commits, save and resolve, by time. Saves and flags of sources
    are held against it, and the review diff starts at its commit."""


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
        files = [name for name in (doc, *names) if not is_external(name)]
        for name in files:
            if not (self.root / name).is_file():
                raise UnknownFileError(name)
        tracked = self._tracked(files)
        for name in files:
            if name not in tracked:
                raise UntrackedFileError(name)
        if doc in names:
            raise SelfDependencyError(doc)
        for source in names:
            if cycle := self._path_between(graph, source, doc):
                raise CycleError([doc, *cycle])

        for name in (doc, *names):
            graph.nodes.setdefault(name, Node())
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

    def node_status(self) -> list[NodeStatus]:
        graph = self._load()
        history = self._history(graph, None, graph.settings, saved_at=None)
        files = sorted(name for name in graph.nodes if not is_external(name))
        saved = history.saved or self._saved(files, None)
        result = []
        for name, node in sorted(graph.nodes.items()):
            last = history.last_commit(name)
            commit = (
                Commit(sha=last.commit, at=last.at, author=last.author, subject=last.subject)
                if last and last.commit and last.author is not None and last.subject is not None
                else None
            )
            result.append(
                NodeStatus(
                    name=name,
                    last_commit=commit,
                    saved_at=saved[name].at if name in saved else None,
                    resolved=node.resolved,
                    flagged=node.flagged,
                )
            )
        return result

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
        existing_resolve_commits = self._existing_commits(
            [n.resolved.commit for n in graph.nodes.values() if n.resolved and n.resolved.commit]
        )
        drift = []
        docs = 0
        for doc, node in sorted(graph.nodes.items()):
            if not node.depends_on:
                continue
            docs += 1
            review = self._review(
                doc, node, history, settings.auto_resolve, existing_resolve_commits
            )
            unseen = (
                self._newest_unseen_commits(node.depends_on, review, history)
                if watches_commits(settings.auto_flag)
                else {}
            )
            for source in node.depends_on:
                changes = self._unreviewed_changes(
                    source,
                    graph.nodes[source],
                    review,
                    unseen.get(source),
                    history,
                    settings.auto_flag,
                )
                if change := latest(*changes):
                    update = review.last_update
                    drift.append(
                        Drift(
                            doc=doc,
                            source=source,
                            doc_fresh_at=update.at if update else None,
                            doc_fresh_commit=update.commit if update else None,
                            source_changed_at=change.at,
                            source_changed_commit=change.commit,
                            note=change.note,
                            flagged=change.flagged,
                        )
                    )
        return CheckReport(rev=rev, docs_checked=docs, drift=drift)

    def resolve(self, *docs: str, note: str | None = None) -> list[str]:
        graph = self._load()
        names = [self._require_node(graph, doc) for doc in docs]
        at, by, head = self._now(), self._user(), self._head()
        for name in names:
            files = [s for s in graph.nodes[name].depends_on if not is_external(s)]
            graph.nodes[name].resolved = Resolution(
                at=at, by=by, commit=head, sources=self._working_hashes(files), note=note
            )
        self._save(graph)
        return names

    def resolve_all(self, note: str | None = None) -> list[str]:
        drifted = self.check().drifted_docs
        return self.resolve(*drifted, note=note) if drifted else []

    def flag(self, node: str, note: str | None = None) -> None:
        graph = self._load()
        name = self._require_node(graph, node)
        graph.nodes[name].flagged = Flag(at=self._now(), by=self._user(), note=note)
        self._save(graph)

    # --- freshness rules --------------------------------------------------------------------
    # A doc may have drifted when one of its sources has a change the doc has not reviewed:
    #
    # 1. A commit is reviewed when the doc has seen it: one of the doc's commits or resolves
    #    descends from it. Ancestry, not dates, so rebases and merges cannot reorder it. A
    #    merge is a change of its own only where it differs from git's automatic merge.
    # 2. A save or a flag has no place in the history, so it is reviewed when the doc was
    #    updated after it, by time. A save of the doc likewise covers earlier commits.
    # 3. Any change is reviewed when it leaves the source exactly as a resolve reviewed it.

    @staticmethod
    def _review(
        doc: str, node: Node, history: History, mode: Mode, existing_resolve_commits: set[str]
    ) -> DocReview:
        """Collect what brought `doc` up to date, as `auto-resolve` (`mode`) allows.

        The commit of a resolve counts only if it still exists: a rebase or squash merge
        replaces it, and the commit it replaced may be gone. Its reviewed content still counts.
        """
        created = history.creating_commit(doc)
        edits = history.commits.get(doc, []) if watches_commits(mode) else []
        own_commits = [*edits, created] if created else edits
        saved = history.saved.get(doc) if watches_saves(mode) else None
        resolved = node.resolved
        resolve = None
        if resolved:
            on_commit = resolved.commit if resolved.commit in existing_resolve_commits else None
            resolve = Moment(resolved.at, on_commit)
        return DocReview(
            seen_commits=frozenset(m.commit for m in [*own_commits, resolve] if m and m.commit),
            reviewed_content=resolved.sources if resolved else {},
            saved=saved,
            last_update=latest(*own_commits, saved, resolve),
        )

    def _unreviewed_changes(
        self,
        source: str,
        node: Node,
        review: DocReview,
        unseen_commit: Moment | None,
        history: History,
        mode: Mode,
    ) -> list[Moment]:
        """The changes to `source` the doc has not reviewed, as `auto-flag` (`mode`) allows.

        At most one of each kind: its newest commit the doc has not seen (`unseen_commit`, rule
        1 is applied already), its uncommitted save, and its flag.
        """
        saved = history.saved.get(source) if watches_saves(mode) else None
        flagged = node.flagged
        flag = Moment(flagged.at, None, flagged.note, flagged=True) if flagged else None
        # Each change with the doc update that rule 2 holds it against: an unseen commit is in
        # the history, so only a save of the doc (outside it) can still cover it by time.
        held_against = [
            (unseen_commit, review.saved),
            (saved, review.last_update),
            (flag, review.last_update),
        ]
        return [
            change
            for change, update in held_against
            if change
            and self._is_after(change, update)
            and not self._leaves_reviewed_content(source, change, review, history)
        ]

    def _newest_unseen_commits(
        self, sources: list[str], review: DocReview, history: History
    ) -> dict[str, Moment]:
        """For each source with commits the doc has not seen, the newest of them (rule 1)."""
        seen = review.seen_commits
        candidates = {
            source: [m for m in history.commits.get(source, []) if m.commit not in seen]
            for source in sources
        }
        unseen = self._not_seen_from(
            seen,
            {m.commit for moments in candidates.values() for m in moments if m.commit},
            history.tip,
            paths=[source for source, moments in candidates.items() if moments],
        )
        newest = {
            source: next((m for m in moments if m.commit in unseen), None)
            for source, moments in candidates.items()
        }
        return {source: moment for source, moment in newest.items() if moment}

    @staticmethod
    def _is_after(change: Moment, update: Moment | None) -> bool:
        """Whether `change` happened after `update` by time; always, if there was none.

        Rule 2. A tie counts as reviewed: `check --uncommitted` gives all saves the same time,
        as one pending commit.
        """
        return update is None or change.at > update.at

    def _leaves_reviewed_content(
        self, source: str, change: Moment, review: DocReview, history: History
    ) -> bool:
        """Whether `source`, as `change` left it, is exactly what the last resolve reviewed.

        Rule 3. A resolve reviews the working tree, so committing that content later, or
        rebasing or squashing the commit, makes a new commit that needs no new review. A flag
        changes no content, so it is never covered this way.
        """
        reviewed = review.reviewed_content.get(source)
        if reviewed is None or change.flagged:
            return False
        if change.commit is None:  # an uncommitted save
            content = self._working_hashes([source]).get(source)
        else:
            content = self._committed_content(source, history.tip)
        return content == reviewed

    # --- git --------------------------------------------------------------------------------

    log_batch_size = 200
    """Paths per `git log` call. Windows limits a command line to 32,767 characters."""

    merge_resolutions_since = (2, 36)
    """The git version that added `--remerge-diff`."""

    @cached_property
    def _sees_merge_resolutions(self) -> bool:
        """Whether git can list what a merge commit changed itself: where its result differs
        from git's automatic merge of its parents, as when a conflict was resolved.

        Without this, `git log` lists no files for a merge, so a source rewritten while
        resolving a conflict would go unseen. A clean merge changes nothing itself, even
        where both sides edited a file; those changes are in the commits it merged.
        """
        version = self.git.version()
        if version >= self.merge_resolutions_since:
            return True
        log.warning(
            "git %s cannot show what merges changed while resolving conflicts (needs %s), "
            "so check does not see those changes. Please upgrade git.",
            ".".join(map(str, version)),
            ".".join(map(str, self.merge_resolutions_since)),
        )
        return False

    def _history(
        self, graph: Graph, rev: str | None, settings: Settings, saved_at: datetime | None
    ) -> History:
        paths = sorted(name for name in graph.nodes if not is_external(name))
        commits: dict[str, list[Moment]] = {}
        tip = rev or (self._head() and "HEAD")
        merges = ["--diff-merges=remerge"] if self._sees_merge_resolutions else []
        for start in range(0, len(paths) if tip else 0, self.log_batch_size):
            batch = paths[start : start + self.log_batch_size]
            output = self.git.run(
                "-c", "core.quotepath=off", "--literal-pathspecs",
                "log", "--format=@@%H%x1f%aI%x1f%an%x1f%s", "--name-only", *merges, tip,
                "--", *batch,
            )  # fmt: skip
            wanted = set(batch)
            moment: Moment | None = None
            for line in output.splitlines():
                if line.startswith("@@"):
                    sha, date, author, subject = line[2:].split("\x1f", 3)
                    moment = Moment(
                        datetime.fromisoformat(date), sha, author=author, subject=subject
                    )
                elif moment and line in wanted:
                    commits.setdefault(line, []).append(moment)
        for touching in commits.values():
            touching.sort(key=lambda m: m.at, reverse=True)
        any_saves = watches_saves(settings.auto_flag) or watches_saves(settings.auto_resolve)
        saved = self._saved(paths, saved_at) if rev is None and any_saves else {}
        return History(tip=tip, commits=commits, saved=saved)

    def _saved(self, paths: list[str], at: datetime | None) -> dict[str, Moment]:
        """Uncommitted changes to tracked files among `paths`, staged or not.

        Timed by file modification time, or all at `at` when given: then they count as one
        pending commit, so their order does not matter.

        Asks for the whole working tree and filters here, so the command line stays short.
        """
        status = self.git.run("status", "--porcelain=v1", "-z", "--untracked-files=no", strip=False)
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

    def _not_seen_from(
        self, seen: frozenset[str], candidates: set[str], tip: str | None, *, paths: list[str]
    ) -> set[str]:
        """Those of `candidates`, commits in the tip's history touching `paths`, that are not
        among `seen` or the commits `seen` descend from.

        One walk from the tip that stops at `seen`, so its length is the number of commits
        made since the doc was last brought up to date, not the length of the history.
        """
        if not candidates or not seen or tip is None:
            return candidates
        revisions = [tip, *(f"^{commit}" for commit in sorted(seen)), "--", *paths]
        walked = self.git.run(
            "--literal-pathspecs", "rev-list", "--stdin", input="\n".join(revisions) + "\n"
        )
        return candidates & set(walked.split())

    def _existing_commits(self, shas: list[str]) -> set[str]:
        """Those of `shas` that are commits in this repository."""
        if not shas:
            return set()
        out = self.git.run(
            "cat-file", "--batch-check=%(objectname) %(objecttype)", input="\n".join(shas) + "\n"
        )
        return {
            sha
            for sha, line in zip(shas, out.splitlines(), strict=True)
            if line.endswith(" commit")
        }

    def _committed_content(self, path: str, tip: str | None) -> str | None:
        """Git blob hash of `path` at the tip; None if it does not exist there."""
        if tip is None:
            return None
        try:
            return self.git.run("rev-parse", "--verify", "--quiet", f"{tip}:{path}")
        except GitError:
            return None

    def _working_hashes(self, paths: list[str]) -> dict[str, str]:
        """Git blob hash of each existing file among `paths`, as in the working tree.

        `git hash-object` applies the same filters (such as line endings) as `git add`, so the
        hash matches the blob a commit of the file would contain.
        """
        files = [p for p in paths if (self.root / p).is_file()]
        if not files:
            return {}
        out = self.git.run("--literal-pathspecs", "hash-object", "--", *files)
        return dict(zip(files, out.splitlines(), strict=True))

    def _tracked(self, paths: list[str]) -> set[str]:
        """The subset of `paths` that git tracks (committed or staged)."""
        if not paths:
            return set()
        listed = self.git.run(
            "-c", "core.quotepath=off", "--literal-pathspecs", "ls-files", "-z", "--", *paths,
            strip=False,
        )  # fmt: skip
        return set(listed.split("\0")) - {""}

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
        """Whole seconds, like git dates, so records and commits compare cleanly."""
        return datetime.now(UTC).replace(microsecond=0)

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
