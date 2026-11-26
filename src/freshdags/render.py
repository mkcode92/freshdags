"""Human-readable output for the CLI."""

import html
import json
import re
from datetime import datetime
from itertools import groupby

from freshdags.models import (
    CheckReport,
    Drift,
    Graph,
    NodeStatus,
    NodeView,
    Settings,
    is_external,
)

SHORT_SHA = 7


def render_check(report: CheckReport) -> str:
    """Format a check report for a terminal.

    For each drift: what changed, a `git diff` command to review it, and how to clear the
    flag. For external or flagged sources, the flag note replaces the diff. Ends with a
    summary line led by the badger.
    """
    blocks = []
    for doc, drifts in groupby(report.drift, key=lambda d: d.doc):
        lines = [f"{doc} may have drifted"]
        for drift in drifts:
            lines.extend(_describe(drift, report.rev))
        lines.append(f"  then: update {doc}, or run: freshdags resolve {doc}")
        blocks.append("\n".join(lines))
    blocks.append(_summary(report))
    return "\n\n".join(blocks)


def _describe(drift: Drift, rev: str | None) -> list[str]:
    if drift.flagged:
        note = f": {drift.note}" if drift.note else ""
        return [f"  {drift.source} flagged{note}"]
    fresh = drift.doc_fresh_commit
    committed = drift.source_changed_commit is not None
    since = f" since {fresh[:SHORT_SHA]}" if fresh else ""
    lines = [f"  {drift.source} changed{since}{'' if committed else ' (uncommitted)'}"]
    if fresh:
        # A committed change is diffed up to the checked revision, a saved one against the
        # working tree.
        end = f"..{rev or 'HEAD'}" if committed else ""
        lines.append(f"    review: git diff {fresh[:SHORT_SHA]}{end} -- {drift.source}")
    elif not committed:
        lines.append(f"    review: git diff HEAD -- {drift.source}")
    return lines


def _summary(report: CheckReport) -> str:
    if not report.ok:
        count = len(report.drifted_docs)
        return f"🦡 {count} {_docs(count)} may have drifted. The badger is watching."
    if report.docs_checked == 0:
        return "🦡✨ Nothing to check yet. Add a dependency with `freshdags add DOC SOURCE`."
    if report.docs_checked == 1:
        return "🦡✨ 1 doc is fresh."
    return f"🦡✨ All {report.docs_checked} docs are fresh."


def _docs(count: int) -> str:
    return "doc" if count == 1 else "docs"


DRIFT_MARK = "(!)"
CHANGED_MARK = "(*)"
MARKS_LEGEND = (
    f"{DRIFT_MARK} may have drifted   {CHANGED_MARK} changed after the doc it is listed for"
)


def render_graph(graph: Graph, report: CheckReport | None = None) -> str:
    """Format the whole graph: each doc with the sources it depends on.

    With a report, a doc that may have drifted is marked `(!)`, and a source that changed
    after the doc it is listed under was up to date is marked `(*)`.
    """
    stale = _stale(report)
    lines = []
    for doc, node in sorted(graph.nodes.items()):
        if node.depends_on:
            lines.append(_marked(doc, stale))
            lines.extend(f"  {_marked(source, stale, doc=doc)}" for source in node.depends_on)
    if not lines:
        return "No dependencies yet. Add one with `freshdags add DOC SOURCE`."
    if stale:
        lines.extend(["", MARKS_LEGEND])
    return "\n".join(lines)


def render_settings(settings: Settings) -> str:
    """One `name: value` line per setting."""
    return "\n".join(
        f"{name}: {value}"
        for name, value in settings.model_dump(mode="json", by_alias=True).items()
    )


def render_node(view: NodeView, report: CheckReport | None = None) -> str:
    """Format one node with its sources and dependents, marked as in `render_graph`."""
    stale = _stale(report)
    name = _marked(view.name, stale)
    sources = [_marked(source, stale, doc=view.name) for source in view.sources]
    dependents = [_marked(doc, stale) for doc in view.dependents]
    lines = [
        name,
        f"  depends on: {', '.join(sources) or '-'}",
        f"  needed by:  {', '.join(dependents) or '-'}",
    ]
    if [name, *sources, *dependents] != [view.name, *view.sources, *view.dependents]:
        lines.extend(["", MARKS_LEGEND])
    return "\n".join(lines)


def _marked(name: str, stale: set[tuple[str, str]], *, doc: str | None = None) -> str:
    """`name`, followed by `(!)` if it may have drifted and `(*)` if it changed after `doc`
    was up to date."""
    marks = [DRIFT_MARK] if any(d == name for d, _ in stale) else []
    if doc is not None and (doc, name) in stale:
        marks.append(CHANGED_MARK)
    return " ".join([name, *marks])


def _stale(report: CheckReport | None) -> set[tuple[str, str]]:
    """(doc, source) of every drifted edge."""
    return {(d.doc, d.source) for d in report.drift} if report else set()


# --- diagrams ------------------------------------------------------------------------------
# Edges point from source to doc, the way changes ripple. External nodes are drawn with a
# dashed outline. Drifted docs are red; the sources whose changes made them drift are amber;
# a doc that is both has a red fill and a thick amber border. DOT and HTML also give each
# node a tooltip with what `check` reports about it.

TEXT_COLOR = "#1f2328"
STATE_STYLES = {
    # state: (fill, stroke, stroke width)
    "drifted": ("#ffebe9", "#cf222e", 1.5),
    "changed": ("#fff8c5", "#bf8700", 1.5),
    "drifted_changed": ("#ffebe9", "#bf8700", 3),
}
"""Light fills with dark text, so diagrams read on light and dark pages alike. The HTML
page has its own colours per theme, in its stylesheet."""
MERMAID_VERSION = "11.4.1"
"""Loaded from a CDN by the HTML page."""
MERMAID_INTEGRITY = "sha384-rbtjAdnIQE/aQJGEgXrVUlMibdfTSa4PQju4HDhN3sR2PmaKFzhEafuePsl9H/9I"
"""Subresource Integrity hash of `dist/mermaid.min.js`: the browser runs no other file.
Update it together with MERMAID_VERSION."""
HTML_CSP = "; ".join(
    [
        "default-src 'none'",
        f"script-src 'unsafe-inline' https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/",
        "style-src 'unsafe-inline'",
        "img-src data:",
        "font-src data:",
        "connect-src 'none'",
        "form-action 'none'",
    ]
)
"""The page may load Mermaid and nothing else, and may not send anything anywhere: the
graph stays on the viewer's machine."""


def render_mermaid(graph: Graph, report: CheckReport | None = None) -> str:
    """The graph as a Mermaid flowchart, for GitHub, GitLab and other Mermaid viewers."""
    return "\n".join(_mermaid_lines(graph, report))


def render_markdown(graph: Graph, report: CheckReport | None = None) -> str:
    """The Mermaid flowchart in a fenced block, which GitHub and GitLab draw directly."""
    return f"```mermaid\n{render_mermaid(graph, report)}\n```"


def _mermaid_ids(graph: Graph) -> dict[str, str]:
    """Paths are not valid Mermaid ids, so nodes get ids `n0`, `n1`, ... instead."""
    return {name: f"n{i}" for i, name in enumerate(sorted(graph.nodes))}


def _mermaid_lines(graph: Graph, report: CheckReport | None, *, colors: bool = True) -> list[str]:
    """Each node is labelled with its quoted path. Without `colors`, the state classes only
    set the border width, so a stylesheet can colour them: Mermaid writes class colours
    inline with `!important`, and rejects CSS variables in them."""
    ids = _mermaid_ids(graph)
    states = _states(report)
    lines = ["flowchart RL"]
    for name, node_id in ids.items():
        label = _mermaid_label(name)
        lines.append(f"  {node_id}([{label}])" if is_external(name) else f"  {node_id}[{label}]")
    lines.extend(f"  {ids[e.source]} --> {ids[e.doc]}" for e in graph.edges())
    if externals := [ids[name] for name in ids if is_external(name)]:
        lines.append("  classDef external stroke-dasharray: 4 3")
        lines.append(f"  class {','.join(externals)} external")
    for state, (fill, stroke, width) in STATE_STYLES.items():
        if members := [ids[name] for name in ids if states.get(name) == state]:
            style = f"stroke-width:{width}px"
            if colors:
                style = f"fill:{fill},stroke:{stroke},{style},color:{TEXT_COLOR}"
            lines.append(f"  classDef {state} {style}")
            lines.append(f"  class {','.join(members)} {state}")
    return lines


def _mermaid_label(name: str) -> str:
    """A quoted label. `#` starts Mermaid's entity codes, so it is escaped first."""
    for char, code in (("#", "#35;"), ('"', "#quot;"), ("<", "#lt;"), (">", "#gt;")):
        name = name.replace(char, code)
    return f'"{name}"'


def render_dot(
    graph: Graph, report: CheckReport | None = None, status: list[NodeStatus] | None = None
) -> str:
    """The graph in Graphviz DOT. `dot -Tsvg` turns the tooltips into hover text."""
    states = _states(report)
    tooltips = _tooltips(graph, report, status)
    lines = ["digraph freshdags {", "  rankdir=RL;", "  node [shape=box];"]
    for name in sorted(graph.nodes):
        styles = ["rounded", "dashed"] if is_external(name) else []
        attrs = []
        if state := states.get(name):
            fill, stroke, width = STATE_STYLES[state]
            styles.insert(0, "filled")
            attrs.append(f'color="{stroke}" fillcolor="{fill}" penwidth={width}')
        if styles:
            attrs.insert(0, f'style="{",".join(styles)}"')
        if name in tooltips:
            attrs.append(f"tooltip={_dot_string(*tooltips[name])}")
        lines.append(f"  {_dot_string(name)}" + (f" [{' '.join(attrs)}]" if attrs else "") + ";")
    lines.extend(f"  {_dot_string(e.source)} -> {_dot_string(e.doc)};" for e in graph.edges())
    lines.append("}")
    return "\n".join(lines)


def _dot_string(*lines: str) -> str:
    """A quoted DOT string; backslashes and quotes are escaped, lines joined with `\\n`."""
    escaped = (line.replace("\\", "\\\\").replace('"', '\\"') for line in lines)
    return '"' + "\\n".join(escaped) + '"'


def render_html(graph: Graph, report: CheckReport, status: list[NodeStatus] | None = None) -> str:
    """A standalone page that draws the Mermaid diagram, with a tooltip on each node.

    Mermaid is loaded from a CDN, so viewing the page needs a network connection; the
    page's security policy pins Mermaid's exact file and lets the page send nothing. The page
    is pure ASCII (other characters become entities), so it survives any output encoding.
    """
    diagram = "\n".join(_mermaid_lines(graph, report, colors=False))
    ids = _mermaid_ids(graph)
    tips = {ids[name]: "\n".join(tip) for name, tip in _tooltips(graph, report, status).items()}
    values = {
        "summary": html.escape(_summary(report)),
        "diagram": html.escape(diagram),
        # `<` is escaped, so no path can end the script element or open a tag.
        "tooltips": json.dumps(tips).replace("<", "\\u003c"),
        "version": MERMAID_VERSION,
        "integrity": MERMAID_INTEGRITY,
        "csp": HTML_CSP,
    }
    # One pass, so a path that looks like `{{tooltips}}` is never substituted itself.
    page = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], _HTML)
    return page.encode("ascii", "xmlcharrefreplace").decode("ascii")


def _states(report: CheckReport | None) -> dict[str, str]:
    """`drifted`, `changed` or `drifted_changed` for each node that drift involves."""
    drift = report.drift if report else []
    drifted = {d.doc for d in drift}
    changed = {d.source for d in drift}
    return {
        name: "drifted_changed" if name in drifted and name in changed
        else "drifted" if name in drifted
        else "changed"
        for name in drifted | changed
    }  # fmt: skip


def _tooltips(
    graph: Graph, report: CheckReport | None, status: list[NodeStatus] | None = None
) -> dict[str, list[str]]:
    """Per node with something to say: its name, what `check` reports about it, then its
    history.

    A drifted doc lists its changed sources with the review command; a changed source lists
    the docs it is now newer than. The history is the last commit, uncommitted save, resolve
    and flag, as far as `status` knows them. Times are shown in local time.
    """
    facts = {s.name: _history_lines(s) for s in status or []}
    drift = report.drift if report else []
    rev = report.rev if report else None
    newer_than: dict[str, list[str]] = {}
    for d in drift:
        newer_than.setdefault(d.source, []).append(d.doc)
    by_doc = {doc: list(drifts) for doc, drifts in groupby(drift, key=lambda d: d.doc)}
    tips = {}
    for name, node in sorted(graph.nodes.items()):
        lines = []
        if name in by_doc:
            lines.append("may have drifted:")
            for d in by_doc[name]:
                lines.extend(_describe(d, rev))
        elif node.depends_on and report:
            lines.append("fresh")
        if name in newer_than:
            lines.append(f"changed after: {', '.join(newer_than[name])}")
        if history := facts.get(name):
            lines.extend(["", *history] if lines else history)
        if lines:
            tips[name] = [name, *lines]
    return tips


def _history_lines(status: NodeStatus) -> list[str]:
    lines = []
    if commit := status.last_commit:
        lines.append(
            f"last commit: {commit.sha[:SHORT_SHA]}, {_when(commit.at)} by {commit.author}"
        )
        if commit.subject:
            lines.append(f"  {commit.subject}")
    if status.saved_at:
        lines.append(f"uncommitted changes, saved {_when(status.saved_at)}")
    if resolved := status.resolved:
        lines.append(f"resolved {_when(resolved.at)} by {resolved.by}")
    if flagged := status.flagged:
        note = f": {flagged.note}" if flagged.note else ""
        lines.append(f"flagged {_when(flagged.at)} by {flagged.by}{note}")
    return lines


def _when(at: datetime) -> str:
    return at.astimezone().strftime("%Y-%m-%d %H:%M")


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{{csp}}">
<meta name="referrer" content="no-referrer">
<title>freshdags graph</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #ffffff; --surface: #f6f8fa; --fg: #1f2328; --muted: #59636e; --border: #d0d7de;
    --node: #ffffff; --node-stroke: #8c959f; --edge: #8c959f;
    --drift: #ffebe9; --drift-stroke: #cf222e;
    --changed: #fff8c5; --changed-stroke: #bf8700;
    --shadow: 0 8px 24px rgba(140, 149, 159, 0.2);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0d1117; --surface: #151b23; --fg: #e6edf3; --muted: #9198a1; --border: #3d444d;
      --node: #212830; --node-stroke: #656c76; --edge: #656c76;
      --drift: #3d1d20; --drift-stroke: #f85149;
      --changed: #3a2d0f; --changed-stroke: #d29922;
      --shadow: 0 8px 24px rgba(1, 4, 9, 0.6);
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 32px 16px; background: var(--bg); color: var(--fg);
         font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 20px; font-weight: 600; margin: 0 0 4px; }
  .summary { margin: 0 0 20px; color: var(--muted); }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
          padding: 24px; overflow-x: auto; }
  .legend { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 0 0 20px; padding: 0;
            list-style: none; color: var(--muted); font-size: 13px; }
  .legend li { display: flex; align-items: center; gap: 8px; }
  .swatch { width: 18px; height: 12px; border-radius: 3px; background: var(--node);
            border: 1.5px solid var(--node-stroke); }
  .swatch.drifted { background: var(--drift); border-color: var(--drift-stroke); }
  .swatch.changed { background: var(--changed); border-color: var(--changed-stroke); }
  .swatch.drifted_changed { background: var(--drift); border: 3px solid var(--changed-stroke); }
  .swatch.external { border-style: dashed; border-radius: 6px; }
  .hint { margin: 16px 0 0; color: var(--muted); font-size: 13px; }
  pre.mermaid { margin: 0; background: none; text-align: center; }
  pre.mermaid:not([data-processed]) { visibility: hidden; }
  pre.mermaid[data-processed="failed"] { text-align: left; }
  /* Mermaid writes each class's colours inline; these follow the page theme instead. */
  .mermaid .node :is(rect, path, polygon) { fill: var(--node) !important;
         stroke: var(--node-stroke) !important; }
  .mermaid .node.drifted :is(rect, path, polygon) { fill: var(--drift) !important;
         stroke: var(--drift-stroke) !important; }
  .mermaid .node.changed :is(rect, path, polygon) { fill: var(--changed) !important;
         stroke: var(--changed-stroke) !important; }
  .mermaid .node.drifted_changed :is(rect, path, polygon) { fill: var(--drift) !important;
         stroke: var(--changed-stroke) !important; stroke-width: 3px !important; }
  .mermaid .node :is(.nodeLabel, .nodeLabel *) { color: var(--fg) !important; }
  .mermaid .node.has-tip { cursor: help; }
  .tooltip { position: absolute; z-index: 10; max-width: min(560px, calc(100vw - 32px));
         padding: 10px 12px; white-space: pre-wrap; text-align: left;
         background: var(--surface); color: var(--fg); border: 1px solid var(--border);
         border-radius: 8px; box-shadow: var(--shadow);
         font: 12px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace;
         pointer-events: none; transform: translate(-50%, calc(-100% - 10px));
         opacity: 0; transition: opacity 120ms; }
  .tooltip.shown { opacity: 1; }
</style>
</head>
<body>
<main>
<h1>freshdags</h1>
<p class="summary">{{summary}}</p>
<ul class="legend">
  <li><span class="swatch"></span>fresh</li>
  <li><span class="swatch drifted"></span>may have drifted</li>
  <li><span class="swatch changed"></span>changed after a dependent doc</li>
  <li><span class="swatch drifted_changed"></span>both</li>
  <li><span class="swatch external"></span>external (ext:)</li>
</ul>
<div class="card"><pre class="mermaid">{{diagram}}</pre></div>
<p class="hint">Arrows point from a source to the doc that depends on it. Hover over a node
for details.</p>
</main>
<script type="application/json" id="tooltips">{{tooltips}}</script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@{{version}}/dist/mermaid.min.js"
  integrity="{{integrity}}" crossorigin="anonymous"></script>
<script type="module">
  const pre = document.querySelector("pre.mermaid");
  const mermaid = window.mermaid;
  if (!mermaid) {
    pre.dataset.processed = "failed";
    pre.insertAdjacentHTML("beforebegin",
      "<p>Mermaid could not be loaded (offline?). Its source is shown instead.</p>");
    throw new Error("Mermaid could not be loaded");
  }
  const css = getComputedStyle(document.documentElement);
  const color = (name) => css.getPropertyValue(name).trim();
  mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    themeVariables: {
      background: color("--surface"),
      primaryColor: color("--node"),
      primaryBorderColor: color("--node-stroke"),
      primaryTextColor: color("--fg"),
      lineColor: color("--edge"),
      fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
      fontSize: "14px",
    },
    flowchart: { curve: "basis", nodeSpacing: 30, rankSpacing: 60 },
  });
  await mermaid.run();

  // Tooltips: Mermaid names node groups like `flowchart-n3-2`.
  const tips = JSON.parse(document.getElementById("tooltips").textContent);
  const tip = document.createElement("div");
  tip.className = "tooltip";
  document.body.append(tip);
  for (const node of document.querySelectorAll("pre.mermaid g.node")) {
    const text = tips[node.id.match(/flowchart-(n\\d+)-/)?.[1]];
    if (!text) continue;
    node.classList.add("has-tip");
    node.addEventListener("mouseenter", () => {
      const box = node.getBoundingClientRect();
      tip.textContent = text;
      tip.style.left = `${scrollX + box.left + box.width / 2}px`;
      tip.style.top = `${scrollY + box.top}px`;
      tip.classList.add("shown");
    });
    node.addEventListener("mouseleave", () => tip.classList.remove("shown"));
  }
</script>
</body>
</html>
"""
