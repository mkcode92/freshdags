"""The freshdags interface: every CLI command as a method.

The CLI only parses arguments, calls one of these methods and renders the result. Tests
exercise the methods directly.

Node names are file paths relative to the repository root, or external names starting with
`ext:`. Paths given by the caller are normalised: `./docs\\api.md` becomes `docs/api.md`.

Every method except `add` and `configure` raises GraphNotFoundError when freshdags.json does
not exist.
All errors derive from freshdags.errors.FreshdagsError.
"""

from abc import ABC, abstractmethod

from freshdags.models import CheckReport, Graph, Mode, NodeStatus, NodeView, Settings


class FreshdagsApi(ABC):
    """Operations on the dependency graph of one git repository."""

    # --- editing the graph ------------------------------------------------------------------

    @abstractmethod
    def add(self, doc: str, *sources: str) -> None:
        """Record that `doc` depends on each of `sources`.

        Creates freshdags.json with default settings if it does not exist. Adding an edge
        that already exists changes nothing.

        Raises:
            UnknownFileError: a non-external node is not an existing file.
            UntrackedFileError: a non-external node is not tracked by git. Only tracked
                files can be checked; everything else must be an `ext:` node.
            SelfDependencyError: `doc` is among `sources`.
            CycleError: an edge would close a cycle. The graph is left unchanged.
        """

    @abstractmethod
    def rm(self, doc: str, *sources: str) -> None:
        """Remove the edges from `doc` to each of `sources`.

        Nodes left without any edge are removed.

        Raises:
            UnknownEdgeError: one of the edges does not exist. The graph is left unchanged.
        """

    @abstractmethod
    def configure(
        self, *, auto_flag: Mode | None = None, auto_resolve: Mode | None = None
    ) -> Settings:
        """Change the given settings and return all settings. With no arguments, only reads.

        Creates freshdags.json with default settings if it does not exist.
        """

    # --- reading the graph ------------------------------------------------------------------

    @abstractmethod
    def graph(self) -> Graph:
        """The whole graph as stored in freshdags.json."""

    @abstractmethod
    def neighbours(self, node: str) -> NodeView:
        """`node` with its direct sources and dependents.

        Raises:
            UnknownNodeError: `node` is not in the graph.
        """

    @abstractmethod
    def node_status(self) -> list[NodeStatus]:
        """Every node with its last commit, uncommitted save, resolve and flag; by name.

        Saves are reported whatever the settings say; they are facts about the working
        tree, not drift.
        """

    # --- drift ------------------------------------------------------------------------------

    @abstractmethod
    def check(self, rev: str | None = None, *, uncommitted: bool = False) -> CheckReport:
        """Find every doc with a source change it has not reviewed.

        A doc reviews a change by being created, updated (as `auto-resolve` allows) or
        resolved after it:
        - A commit counts as reviewed when the doc has seen it: a commit of the doc, or the
          commit a resolve was made on, descends from it. Ancestry, not dates, so rebases and
          merges cannot reorder a change and a doc update. A merge commit changes a file
          only where it differs from git's automatic merge, as when resolving a conflict
          (seen with git 2.36 or later).
        - Saves and flags have no place in the history, so they are ordered by time.
        - Any change that leaves a source exactly as a resolve reviewed it is reviewed.

        Without `rev`, uses the current freshdags.json and, in `on-change` mode, the working
        tree. With `rev`, uses freshdags.json and the history as of that commit only.

        `uncommitted` treats all uncommitted changes as one commit made now, also in
        `on-commit` mode. That is what a pre-commit hook needs: it runs before the commit
        exists. `off` stays off.

        Raises:
            FreshdagsError: `uncommitted` is combined with `rev`.
        """

    # Flags and resolves are scoped to nodes: a file goes stale, and a review covers all of
    # its changed sources at once.

    @abstractmethod
    def resolve(self, *docs: str, note: str | None = None) -> list[str]:
        """Record that each doc was reviewed and is up to date. Returns the docs resolved.

        `note` says why the doc is still correct; the CLI requires one. The record also holds
        the content of each source as reviewed. Does not flag the docs that depend on them.

        Raises:
            UnknownNodeError: a doc is not in the graph.
        """

    @abstractmethod
    def resolve_all(self, note: str | None = None) -> list[str]:
        """Resolve every drifted doc, when the change needed no doc update.

        Returns the docs resolved.
        """

    @abstractmethod
    def flag(self, node: str, note: str | None = None) -> None:
        """Record that `node` changed in a way git cannot see, flagging its dependents.

        Raises:
            UnknownNodeError: `node` is not in the graph.
        """
