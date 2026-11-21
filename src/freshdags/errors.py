"""Errors raised by freshdags. The CLI turns every FreshdagsError into exit code 2."""

from freshdags.models import GRAPH_FILE


class FreshdagsError(Exception):
    """Base class for all expected errors: bad input or a broken graph file."""


class GraphNotFoundError(FreshdagsError):
    def __init__(self) -> None:
        super().__init__(f"No {GRAPH_FILE} found. Run `freshdags add` to create one.")


class UnknownFileError(FreshdagsError):
    def __init__(self, path: str) -> None:
        super().__init__(f"File not found: {path}")
        self.path = path


class UnknownNodeError(FreshdagsError):
    def __init__(self, node: str) -> None:
        super().__init__(f"Not in the graph: {node}")
        self.node = node


class UnknownEdgeError(FreshdagsError):
    def __init__(self, doc: str, source: str) -> None:
        super().__init__(f"{doc} does not depend on {source}")
        self.doc, self.source = doc, source


class SelfDependencyError(FreshdagsError):
    def __init__(self, node: str) -> None:
        super().__init__(f"{node} cannot depend on itself")
        self.node = node


class CycleError(FreshdagsError):
    def __init__(self, cycle: list[str]) -> None:
        super().__init__(f"This would create a cycle: {' -> '.join(cycle)}")
        self.cycle = cycle


class UnsupportedVersionError(FreshdagsError):
    def __init__(self, version: int, supported: int) -> None:
        super().__init__(
            f"{GRAPH_FILE} has format version {version}; this freshdags understands up to "
            f"{supported}. Please upgrade freshdags."
        )
        self.version = version
