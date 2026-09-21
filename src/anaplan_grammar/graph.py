"""Dependency graph over a Model.

Nodes are line items (module, name). Edges go from a line item to each
line item its formula references: A -> B means "A uses B".

Reference resolution, in order:
  1 segment  [X]         line item X in the same module, if it exists;
                         else a dimension/list name (ITEM(List), PREVIOUS(x, List));
                         else unresolved.
  2 segments [M, X]      line item X in module M, if M is a module and X exists there;
                         else list item literal (List.Item, TIME.'Jan 21', VERSIONS.Actual);
                         else unresolved.
  3+ segments            [M, X, ...]: resolve the first two, keep the rest as a property tag.

Every reference is classified so nothing is silently dropped:
  kind in {"line_item", "list_item", "dimension", "unresolved"}.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict, deque
from .model import Model, LineItem
from .parser import parse, references_ctx, ParseError
from .lexer import LexError

PSEUDO_LISTS = {"TIME", "VERSIONS", "VERSION", "USERS"}
# (function, arg index) positions whose argument is a list name, not a line item
LIST_ARG = {("FINDITEM", 0), ("ITEM", 0), ("PREVIOUS", 1), ("NEXT", 1), ("RANK", 4), ("RANKCUMULATE", 4),
            ("ISFIRSTOCCURRENCE", 1), ("TEXTLIST", 1), ("HIERARCHYLEVEL", 0), ("ITEMLEVEL", 0), ("COLLECT", 0)}


@dataclass
class Ref:
    path: tuple[str, ...]
    kind: str                 # line_item | list_item | dimension | unresolved
    target: tuple[str, str] | None = None   # (module, name) when kind == line_item


@dataclass
class Graph:
    model: Model
    edges: dict[tuple[str, str], set[tuple[str, str]]] = field(default_factory=lambda: defaultdict(set))   # A uses B
    rev: dict[tuple[str, str], set[tuple[str, str]]] = field(default_factory=lambda: defaultdict(set))     # B used by A
    refs: dict[tuple[str, str], list[Ref]] = field(default_factory=dict)        # per line item, all refs classified
    parse_errors: dict[tuple[str, str], str] = field(default_factory=dict)

    # ---- build ----
    def resolve(self, li: LineItem, path: list[str], fn: str | None = None, argi: int | None = None) -> Ref:
        m = self.model
        p = tuple(path)
        if len(p) == 1:
            key = (li.module, p[0])
            if (fn, argi) in LIST_ARG:
                # FINDITEM(List, ...), ITEM(List), PREVIOUS(x, List): the argument is a list name even
                # when a same-module line item shares the name (seen in production: a text line item
                # "Marvista Contracts" next to FINDITEM(Marvista Contracts, ...) on the list of that name).
                return Ref(p, "dimension")
            if key in m.line_items:
                return Ref(p, "line_item", key)
            if p[0] in m.dimensions or p[0].upper() in PSEUDO_LISTS or p[0] in m.modules:
                return Ref(p, "dimension")
            return Ref(p, "unresolved")
        key = (p[0], p[1])
        if key in m.line_items:
            return Ref(p, "line_item", key)
        if p[0].upper() in PSEUDO_LISTS or p[0] in m.dimensions or p[0] not in m.modules:
            return Ref(p, "list_item")
        return Ref(p, "unresolved")

    def build(self) -> "Graph":
        for key, li in self.model.line_items.items():
            if not li.formula:
                continue
            try:
                ast = parse(li.formula)
            except (ParseError, LexError, RecursionError) as e:
                self.parse_errors[key] = str(e)
                continue
            out = []
            for path, fn, argi in references_ctx(ast):
                r = self.resolve(li, path, fn, argi)
                out.append(r)
                if r.kind == "line_item" and r.target != key:
                    self.edges[key].add(r.target)
                    self.rev[r.target].add(key)
            self.refs[key] = out
        return self

    # ---- queries ----
    def impact(self, key: tuple[str, str], depth: int | None = None) -> dict[tuple[str, str], int]:
        """Everything downstream of key (things that use it, transitively) with distance."""
        return self._closure(key, self.rev, depth)

    def lineage(self, key: tuple[str, str], depth: int | None = None) -> dict[tuple[str, str], int]:
        """Everything upstream of key (things it uses, transitively) with distance."""
        return self._closure(key, self.edges, depth)

    def _closure(self, start, adj, depth):
        seen = {start: 0}
        q = deque([start])
        while q:
            n = q.popleft()
            d = seen[n]
            if depth is not None and d >= depth:
                continue
            for x in adj.get(n, ()):
                if x not in seen:
                    seen[x] = d + 1
                    q.append(x)
        seen.pop(start, None)
        return seen

    def unused(self) -> list[tuple[str, str]]:
        """Line items nothing references. Excludes header rows. Note: a line item
        used only by a view, export or dashboard shows here too; the exports
        do not carry that usage, so treat as 'not referenced by any formula'."""
        return [k for k, li in self.model.line_items.items() if not li.is_header and not self.rev.get(k)]

    def hubs(self, n: int = 20) -> list[tuple[tuple[str, str], int]]:
        """Line items with the most direct dependents."""
        return sorted(((k, len(v)) for k, v in self.rev.items()), key=lambda kv: -kv[1])[:n]

    def cycles(self) -> list[list[tuple[str, str]]]:
        """Elementary cycles via Tarjan SCCs; each SCC with >1 node or a self-loop is a cycle."""
        index = {}; low = {}; stack = []; on = set(); out = []; counter = [0]
        import sys
        sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))

        def strong(v):
            index[v] = low[v] = counter[0]; counter[0] += 1
            stack.append(v); on.add(v)
            for w in self.edges.get(v, ()):
                if w not in index:
                    strong(w); low[v] = min(low[v], low[w])
                elif w in on:
                    low[v] = min(low[v], index[w])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop(); on.discard(w); comp.append(w)
                    if w == v: break
                if len(comp) > 1 or v in self.edges.get(v, ()):
                    out.append(comp)

        for v in list(self.model.line_items):
            if v not in index:
                strong(v)
        return out

    def daisy_chains(self, min_len: int = 3) -> list[list[tuple[str, str]]]:
        """Chains A -> B -> C ... where each intermediate is a pure pass-through
        (formula is a single reference to one other line item). Anaplan's
        checklist calls these out; they re-calculate the whole sequence on any change."""
        passthrough = {}
        for k, rs in self.refs.items():
            li = self.model.line_items[k]
            lis = [r for r in rs if r.kind == "line_item"]
            if len(lis) == 1 and len(rs) == 1 and parse_is_single_ref(li.formula):
                passthrough[k] = lis[0].target
        targets = set(passthrough.values())
        heads = [k for k in passthrough if k not in targets]   # maximal chains start at heads
        chains = []
        for start in heads:
            chain = [start]; cur = start
            while cur in passthrough and passthrough[cur] not in chain:
                cur = passthrough[cur]; chain.append(cur)
            if len(chain) >= min_len:
                chains.append(chain)
        return sorted(chains, key=len, reverse=True)

    def module_edges(self) -> dict[str, set[str]]:
        """Module-level rollup: module A uses module B."""
        out = defaultdict(set)
        for a, bs in self.edges.items():
            for b in bs:
                if a[0] != b[0]:
                    out[a[0]].add(b[0])
        return out

    def stats(self) -> dict:
        kinds = defaultdict(int)
        for rs in self.refs.values():
            for r in rs:
                kinds[r.kind] += 1
        return {
            "line_items": len(self.model.line_items),
            "with_formula": sum(1 for li in self.model.line_items.values() if li.formula),
            "parse_errors": len(self.parse_errors),
            "edges": sum(len(v) for v in self.edges.values()),
            "refs_by_kind": dict(kinds),
            "modules": len(self.model.modules),
            "module_edges": sum(len(v) for v in self.module_edges().values()),
        }


def parse_is_single_ref(formula: str) -> bool:
    try:
        ast = parse(formula)
    except Exception:
        return False
    return ast.get("t") == "ref"


def build_graph(model: Model) -> Graph:
    return Graph(model=model).build()
