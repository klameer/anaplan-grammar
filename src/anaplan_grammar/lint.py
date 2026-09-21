"""Lint an Anaplan model.

Rules come from three places and each rule says which:
  ANAPLAN  Anaplan's Model Optimization Checklist (support.anaplan.com, six
           section pages, fetched 2026-09-21), reproduced with its threshold.
  GRAPH    Structural facts from the dependency graph.
  FORMULA  Facts from the parse tree.

A finding names the object so a builder can click straight to it.
Severity: critical (wrong or will break), major (performance or
maintainability with a stated threshold), minor (hygiene), info.

Rules are functions registered with @rule; a rule set can be filtered by
id or by tag, and per-model thresholds can be overridden.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from collections import Counter, defaultdict
import re
from .model import Model, LineItem
from .graph import Graph, build_graph
from .parser import parse

@dataclass
class Finding:
    rule: str
    severity: str            # critical | major | minor | info
    module: str
    line_item: str | None
    message: str
    fix: str
    source: str              # ANAPLAN | GRAPH | FORMULA
    value: str = ""          # the measured value, for sorting and tables

    @property
    def object(self) -> str:
        return f"{self.module}.{self.line_item}" if self.line_item else self.module


@dataclass
class Rule:
    id: str
    title: str
    severity: str
    source: str
    description: str
    fn: object
    thresholds: dict = field(default_factory=dict)


RULES: dict[str, Rule] = {}


def rule(id, title, severity, source, description, **thresholds):
    def deco(fn):
        RULES[id] = Rule(id, title, severity, source, description, fn, thresholds)
        return fn
    return deco


# ---------- helpers over the AST ----------

def _walk(n):
    if isinstance(n, dict):
        yield n
        for v in n.values():
            yield from _walk(v)
    elif isinstance(n, list):
        for v in n:
            yield from _walk(v)


def _ast(li: LineItem):
    if not li.formula:
        return None
    try:
        return parse(li.formula)
    except Exception:
        return None


def _if_count(ast):
    return sum(1 for n in _walk(ast) if n.get("t") == "if")


def _if_depth(ast):
    def d(n):
        if not isinstance(n, dict):
            return 0
        best = 0
        for k, v in n.items():
            if isinstance(v, dict):
                best = max(best, d(v))
            elif isinstance(v, list):
                for x in v:
                    best = max(best, d(x))
        return best + (1 if n.get("t") == "if" else 0)
    return d(ast)


def _calls(ast):
    return [n["f"] for n in _walk(ast) if n.get("t") == "call"]


def _clause_kinds(ast):
    out = []
    for n in _walk(ast):
        if n.get("t") == "clause":
            out.append(tuple(sorted({c["k"] for c in n["clauses"]})))
    return out


def _numbers(ast):
    return [n["v"] for n in _walk(ast) if n.get("t") == "num"]


def _token_count(formula: str) -> int:
    return len(re.findall(r"[A-Za-z_][A-Za-z0-9_ ]*|\d+(?:\.\d+)?|'[^']*'|\"[^\"]*\"|[^\s]", formula))


# ---------- rules ----------

@rule("A-LI-COUNT", "More than 50 line items in a module", "major", "ANAPLAN",
      "Modules with many line items are slow to open and hard to maintain. Anaplan's checklist: no more than 50.", max_line_items=50)
def r_li_count(m: Model, g: Graph, t):
    for name, mod in m.modules.items():
        n = sum(1 for li in m.by_module(name) if not li.is_header)
        if n > t["max_line_items"]:
            yield Finding("A-LI-COUNT", "major", name, None, f"{n} line items", "Split into modules by purpose (DISCO).", "ANAPLAN", str(n))


@rule("A-SUMMARY-ON", "Summary method on where a formula suggests it is not needed", "minor", "ANAPLAN",
      "Summaries calculate on every parent; turn them off unless a parent value is used. Flags large number line items with a summary that no formula references.", min_cells=10000)
def r_summary(m: Model, g: Graph, t):
    for k, li in m.line_items.items():
        if li.is_header or li.format_type != "NUMBER" or li.cell_count < t["min_cells"]:
            continue
        if li.summary and li.summary.split(";")[0] not in ("NONE", "", "-") and not g.rev.get(k):
            yield Finding("A-SUMMARY-ON", "minor", li.module, li.name, f"summary {li.summary}, referenced by no formula", "Set summary to None unless a view needs the total.", "ANAPLAN", li.summary)


@rule("A-TEXT-FORMAT", "Text-formatted line item", "minor", "ANAPLAN",
      "Text line items use more memory and cannot aggregate. Anaplan's checklist: minimise; prefer list-formatted items.", min_cells=50000)
def r_text(m: Model, g: Graph, t):
    for li in m.line_items.values():
        if li.format_type == "TEXT" and li.cell_count > t["min_cells"]:
            yield Finding("A-TEXT-FORMAT", "minor", li.module, li.name, f"TEXT with {li.cell_count:,} cells", "Use a list-formatted item or move text to a system module.", "ANAPLAN", str(li.cell_count))


@rule("A-SUBSIDIARY", "Subsidiary view on a calculation line item", "major", "ANAPLAN",
      "A line item whose Applies To differs from its module's is a subsidiary view. Anaplan's checklist: display and export only, never calculation data.")
def r_subsidiary(m: Model, g: Graph, t):
    if not m.has_modules_export:
        return
    for k, li in m.line_items.items():
        mod = m.modules.get(li.module)
        if li.is_header or not mod or not mod.applies_to or not li.applies_to:
            continue
        if set(li.applies_to) != set(mod.applies_to) and li.formula and g.rev.get(k):
            yield Finding("A-SUBSIDIARY", "major", li.module, li.name,
                          f"applies to {', '.join(li.applies_to)} in a module on {', '.join(mod.applies_to)}; used by {len(g.rev[k])} formulas",
                          "Move to a module dimensioned as the line item is.", "ANAPLAN", str(len(g.rev[k])))


@rule("A-DAISY", "Daisy-chain formula", "major", "ANAPLAN",
      "A references B references C where each is a pure pass-through; the whole sequence recalculates on any change. Anaplan's checklist: never.", min_len=3)
def r_daisy(m: Model, g: Graph, t):
    for chain in g.daisy_chains(min_len=t["min_len"]):
        a, b = chain[0], chain[-1]
        yield Finding("A-DAISY", "major", a[0], a[1], f"{len(chain)}-step pass-through chain ending at {b[0]}.{b[1]}",
                      f"Reference {b[0]}.{b[1]} directly.", "ANAPLAN", str(len(chain)))


@rule("A-IF-COUNT", "Formula with more than 10 IF THEN ELSE", "major", "ANAPLAN",
      "Anaplan's checklist: refactor above 10 IF conditions; use a LOOKUP or Boolean flag line items.", max_ifs=10)
def r_if_count(m: Model, g: Graph, t):
    for li in m.line_items.values():
        ast = _ast(li)
        if ast is None:
            continue
        n = _if_count(ast)
        if n > t["max_ifs"]:
            yield Finding("A-IF-COUNT", "major", li.module, li.name, f"{n} IF THEN ELSE in one formula", "Split conditions into Boolean line items or use a mapping module with LOOKUP.", "ANAPLAN", str(n))


@rule("A-SYSTEMS-FN", "Unchanging function in a calculation module", "minor", "ANAPLAN",
      "PARENT(), text joins, START(), CURRENTPERIODSTART() produce values that do not change per cell; Anaplan's checklist: compute once in a systems module.",
      fns=("PARENT", "START", "END", "CURRENTPERIODSTART", "CURRENTPERIODEND", "ITEM", "NAME", "CODE"))
def r_systems(m: Model, g: Graph, t):
    for li in m.line_items.values():
        if li.cell_count < t.get("min_cells", 5000):
            continue
        ast = _ast(li)
        if ast is None:
            continue
        calls = [f for f in _calls(ast) if f in t["fns"]]
        if calls and len(li.applies_to) >= 2:
            yield Finding("A-SYSTEMS-FN", "minor", li.module, li.name, f"{', '.join(sorted(set(calls)))} in a {li.cell_count:,}-cell line item",
                          "Compute in a single-dimension systems module and reference it.", "ANAPLAN", ",".join(sorted(set(calls))))


@rule("A-TEXT-JOIN", "Text concatenation in a large line item", "minor", "ANAPLAN",
      "Anaplan's checklist: combining text strings takes memory; restructure into systems modules.")
def r_text_join(m: Model, g: Graph, t):
    for li in m.line_items.values():
        if li.cell_count < t.get("min_cells", 10000):
            continue
        ast = _ast(li)
        if ast is None:
            continue
        if any(n.get("t") == "bin" and n["op"] == "&" for n in _walk(ast)):
            yield Finding("A-TEXT-JOIN", "minor", li.module, li.name, f"& in a {li.cell_count:,}-cell line item", "Build the text once in a systems module.", "ANAPLAN", str(li.cell_count))


@rule("A-FINDITEM", "FINDITEM in a large line item", "minor", "ANAPLAN",
      "Anaplan's checklist: FINDITEM is expensive; minimise and null-check first.")
def r_finditem(m: Model, g: Graph, t):
    for li in m.line_items.values():
        if li.cell_count < t.get("min_cells", 10000):
            continue
        ast = _ast(li)
        if ast is None:
            continue
        if "FINDITEM" in _calls(ast):
            yield Finding("A-FINDITEM", "minor", li.module, li.name, f"FINDITEM in a {li.cell_count:,}-cell line item", "Map once in a systems module.", "ANAPLAN", str(li.cell_count))


@rule("F-MIXED-CLAUSE", "SUM and LOOKUP (or SELECT) in one bracket", "major", "FORMULA",
      "Anapedia: never combine SUM with LOOKUP or SELECT in the same expression; the engine builds a large intermediate mapping.")
def r_mixed(m: Model, g: Graph, t):
    bad = {("LOOKUP", "SUM"), ("SELECT", "SUM"), ("LOOKUP", "SELECT")}
    for li in m.line_items.values():
        ast = _ast(li)
        if ast is None:
            continue
        for kinds in _clause_kinds(ast):
            if len(kinds) >= 2 and any(set(b) <= set(kinds) for b in bad):
                yield Finding("F-MIXED-CLAUSE", "major", li.module, li.name, f"[{' + '.join(kinds)}] in one bracket", "Split into two line items: aggregate first, then look up.", "FORMULA", "+".join(kinds))
                break


@rule("F-HARDCODE", "Hard-coded constant in a formula", "minor", "FORMULA",
      "Numbers other than 0, 1, 100, 12 inside formulas are assumptions that belong in an input line item.", ignore=("0", "1", "100", "12", "1000", "1000000", "2", "3", "4", "-1", "0.5"))
def r_hardcode(m: Model, g: Graph, t):
    for li in m.line_items.values():
        ast = _ast(li)
        if ast is None:
            continue
        nums = [v for v in _numbers(ast) if v not in t["ignore"]]
        # numbers as function arguments (ROUND(x, -3), LEFT(x, 4)) are positional, not assumptions
        arg_nums = {a["v"] for n in _walk(ast) if n.get("t") == "call" for a in n["args"] if a.get("t") == "num"}
        nums = [v for v in nums if v not in arg_nums]
        if nums:
            yield Finding("F-HARDCODE", "minor", li.module, li.name, f"constants {', '.join(sorted(set(nums))[:4])}", "Move to an input line item with a name and a note.", "FORMULA", ",".join(sorted(set(nums))[:4]))


@rule("F-LONG", "Very long formula", "minor", "FORMULA",
      "Anaplan's checklist: a formula should be explainable in one sentence.", max_tokens=120)
def r_long(m: Model, g: Graph, t):
    for li in m.line_items.values():
        if not li.formula:
            continue
        n = _token_count(li.formula)
        if n > t["max_tokens"]:
            yield Finding("F-LONG", "minor", li.module, li.name, f"{n} tokens", "Break into named intermediate line items.", "FORMULA", str(n))


@rule("F-DIVIDE", "Division with no zero guard", "major", "FORMULA",
      "A / B errors when B is zero; the summary then shows an error too. Use DIVIDE() or guard with IF.")
def r_divide(m: Model, g: Graph, t):
    for li in m.line_items.values():
        ast = _ast(li)
        if ast is None:
            continue
        has_div = any(n.get("t") == "bin" and n["op"] == "/" and n["r"].get("t") != "num" for n in _walk(ast))
        guarded = _if_count(ast) > 0 or "DIVIDE" in _calls(ast)
        if has_div and not guarded:
            yield Finding("F-DIVIDE", "major", li.module, li.name, "unguarded / by a line item", "Use DIVIDE(a, b) or IF b <> 0 THEN a / b ELSE 0.", "FORMULA")


@rule("F-PARSE", "Formula does not parse", "critical", "FORMULA",
      "The parser rejected this formula; either the grammar has a gap or the export is corrupt.")
def r_parse(m: Model, g: Graph, t):
    for k, err in g.parse_errors.items():
        yield Finding("F-PARSE", "critical", k[0], k[1], err[:120], "Report the formula shape.", "FORMULA")


TIME_OFFSET_FNS = ("PREVIOUS", "NEXT", "LAG", "LEAD", "OFFSET", "CUMULATE", "DECUMULATE", "MOVINGSUM",
                   "PREVIOUSVERSION", "NEXTVERSION", "POST", "SPREAD", "PROFILE")


@rule("G-CYCLE", "Circular reference", "info", "GRAPH",
      "Line items that depend on each other at the line-item level. Anaplan rejects a direct circular reference at formula entry, "
      "so a real cycle always passes through a time or version offset (PREVIOUS, LAG, OFFSET, CUMULATE, PREVIOUSVERSION): an "
      "opening balance from last period's closing balance. Reported as info to confirm it is intended. A cycle with NO such "
      "function cannot exist in Anaplan; if one appears, the parser has misread a reference and it is reported as critical.")
def r_cycle(m: Model, g: Graph, t):
    for comp in g.cycles():
        a = comp[0]
        fns = set()
        for k in comp:
            ast = _ast(m.line_items[k])
            if ast is not None:
                fns.update(f for f in _calls(ast) if f in TIME_OFFSET_FNS)
        names = ", ".join(f"{x[0]}.{x[1]}" for x in comp[:4]) + (" ..." if len(comp) > 4 else "")
        if fns:
            yield Finding("G-CYCLE", "info", a[0], a[1], f"balance pattern via {'/'.join(sorted(fns))}: {names}",
                          "Confirm the opening/closing pattern is intended.", "GRAPH", str(len(comp)))
        else:
            yield Finding("G-CYCLE", "critical", a[0], a[1], f"cycle with no time offset: {names}",
                          "Anaplan would reject this; the parser has misread a reference. Report the formulas.", "GRAPH", str(len(comp)))


@rule("G-UNUSED", "Line item with a formula that nothing references", "info", "GRAPH",
      "Not used by any formula. May be used by a view, export or dashboard, which the exports do not show; confirm before removing.", min_cells=50000)
def r_unused(m: Model, g: Graph, t):
    for k in g.unused():
        li = m.line_items[k]
        if li.formula and li.cell_count >= t["min_cells"]:
            yield Finding("G-UNUSED", "info", li.module, li.name, f"calculated, {li.cell_count:,} cells, referenced by no formula", "Check views and exports; remove if unused.", "GRAPH", str(li.cell_count))


@rule("G-HUB", "Hub line item", "info", "GRAPH",
      "Referenced by many line items; a change here has a wide blast radius. Not a fault, a fact for reviewers.", min_dependents=25)
def r_hub(m: Model, g: Graph, t):
    for k, n in g.hubs(50):
        if n >= t["min_dependents"]:
            imp = g.impact(k)
            yield Finding("G-HUB", "info", k[0], k[1], f"{n} direct dependents, {len(imp)} downstream across {len({x[0] for x in imp})} modules", "Cover in every release test.", "GRAPH", str(n))


@rule("G-EMPTY-MODULE", "Module with no line items", "minor", "GRAPH",
      "Empty modules are usually leftovers.")
def r_empty(m: Model, g: Graph, t):
    for name, mod in m.modules.items():
        if not mod.line_items and not re.match(r"^[-▼▲=\s]", name):
            yield Finding("G-EMPTY-MODULE", "minor", name, None, "no line items", "Delete or document.", "GRAPH")


@rule("H-NOTES", "Modules without notes", "info", "GRAPH",
      "Documentation coverage. One finding per model: how many modules carry no notes, and the largest of them.")
def r_notes(m: Model, g: Graph, t):
    if not m.has_modules_export:
        return
    real = [mod for name, mod in m.modules.items() if mod.line_items and not re.match(r"^[-▼▲=\s#]", name)]
    missing = sorted((mod for mod in real if not mod.notes.strip()), key=lambda x: -x.cell_count)
    if real and missing:
        top = ", ".join(x.name for x in missing[:5])
        yield Finding("H-NOTES", "info", "(model)", None, f"{len(missing)} of {len(real)} modules have no notes; largest: {top}",
                      "Add a one-line purpose note to each module, largest first.", "GRAPH", f"{len(missing)}/{len(real)}")


# ---------- runner ----------

@dataclass
class LintResult:
    findings: list[Finding]
    counts: dict
    rules_run: list[str]

    def by_severity(self):
        out = defaultdict(list)
        for f in self.findings:
            out[f.severity].append(f)
        return out

    def to_dict(self):
        return {"counts": self.counts, "rules_run": self.rules_run, "findings": [asdict(f) | {"object": f.object} for f in self.findings]}


SEV_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3}


def lint(model: Model, graph: Graph | None = None, rules: list[str] | None = None, overrides: dict | None = None) -> LintResult:
    g = graph or build_graph(model)
    overrides = overrides or {}
    findings, run = [], []
    for rid, r in RULES.items():
        if rules and rid not in rules:
            continue
        t = dict(r.thresholds); t.update(overrides.get(rid, {}))
        findings.extend(r.fn(model, g, t))
        run.append(rid)
    findings.sort(key=lambda f: (SEV_ORDER[f.severity], f.rule, f.module, f.line_item or ""))
    counts = Counter(f.rule for f in findings)
    return LintResult(findings, {"by_severity": dict(Counter(f.severity for f in findings)), "by_rule": dict(counts)}, run)


def render_markdown(res: LintResult, max_per_rule: int = 15) -> str:
    out = ["# Lint", "", "| Severity | Count |", "|---|---|"]
    for s in ("critical", "major", "minor", "info"):
        out.append(f"| {s} | {res.counts['by_severity'].get(s, 0)} |")
    out.append("")
    grouped = defaultdict(list)
    for f in res.findings:
        grouped[f.rule].append(f)
    for rid in sorted(grouped, key=lambda r: (SEV_ORDER[RULES[r].severity], r)):
        r = RULES[rid]; fs = grouped[rid]
        out += [f"## {rid}: {r.title} ({len(fs)})", "", f"*{r.description}* Source: {r.source}.", "",
                "| Object | Finding | Fix |", "|---|---|---|"]
        for f in fs[:max_per_rule]:
            out.append(f"| {f.object} | {f.message} | {f.fix} |")
        if len(fs) > max_per_rule:
            out.append(f"| ... | {len(fs) - max_per_rule} more | |")
        out.append("")
    return "\n".join(out)
