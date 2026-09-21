"""Diff two Anaplan models loaded from exports.

Compares structure (modules, line items), then per line item: formula
(at tree level, so whitespace and quoting differences are not changes),
format, applies-to, time scale, versions, summary. Each change carries
its blast radius from the *after* graph so a reviewer sees what a change
touches, not just that it happened.

Renames are detected heuristically: a removed line item and an added one
in the same module with the same formula tree (or, for inputs, the same
format and applies-to) are reported as a rename, not a delete plus add.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from .model import Model, LineItem
from .graph import Graph, build_graph
from .parser import parse
from .unparse import unparse


def _tree(formula: str):
    if not formula:
        return None
    try:
        return parse(formula)
    except Exception:
        return {"t": "unparsed", "v": formula}


@dataclass
class FieldChange:
    field: str
    before: str
    after: str


@dataclass
class LineItemChange:
    module: str
    name: str
    kind: str                      # added | removed | changed | renamed
    fields: list[FieldChange] = field(default_factory=list)
    renamed_from: str | None = None
    impact_count: int = 0          # downstream line items in the after-graph
    impact_modules: int = 0
    formula_before: str = ""
    formula_after: str = ""


@dataclass
class ModuleChange:
    name: str
    kind: str                      # added | removed | changed
    line_items_added: int = 0
    line_items_removed: int = 0
    line_items_changed: int = 0
    fields: list[FieldChange] = field(default_factory=list)


@dataclass
class Diff:
    before_name: str
    after_name: str
    modules: list[ModuleChange] = field(default_factory=list)
    line_items: list[LineItemChange] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        c = {"modules_added": 0, "modules_removed": 0, "modules_changed": 0,
             "line_items_added": 0, "line_items_removed": 0, "line_items_changed": 0, "line_items_renamed": 0,
             "formula_changes": 0}
        for m in self.modules:
            c[f"modules_{m.kind}"] += 1
        for li in self.line_items:
            c[f"line_items_{li.kind}"] += 1
            if any(f.field == "formula" for f in li.fields):
                c["formula_changes"] += 1
        return c

    def to_dict(self) -> dict:
        return {"before": self.before_name, "after": self.after_name, "summary": self.summary,
                "modules": [asdict(m) for m in self.modules],
                "line_items": [asdict(li) for li in self.line_items]}


_LI_FIELDS = ["format_type", "applies_to", "time_scale", "versions", "summary"]
_MOD_FIELDS = ["functional_area", "applies_to", "time_scale", "versions"]


def _li_fields(a: LineItem, b: LineItem) -> list[FieldChange]:
    out = []
    ta, tb = _tree(a.formula), _tree(b.formula)
    if ta != tb:
        out.append(FieldChange("formula", a.formula, b.formula))
    for f in _LI_FIELDS:
        va, vb = getattr(a, f), getattr(b, f)
        if isinstance(va, tuple): va = ", ".join(va)
        if isinstance(vb, tuple): vb = ", ".join(vb)
        if va != vb:
            out.append(FieldChange(f, str(va), str(vb)))
    return out


def diff_models(before: Model, after: Model, graph_after: Graph | None = None) -> Diff:
    g = graph_after or build_graph(after)
    d = Diff(before_name=before.name, after_name=after.name)

    def impact(key):
        imp = g.impact(key)
        return len(imp), len({m for m, _ in imp})

    # modules
    mb, ma = set(before.modules), set(after.modules)
    for name in sorted(ma - mb):
        d.modules.append(ModuleChange(name, "added", line_items_added=len(after.modules[name].line_items)))
    for name in sorted(mb - ma):
        d.modules.append(ModuleChange(name, "removed", line_items_removed=len(before.modules[name].line_items)))

    # line items, per module present in both
    per_module: dict[str, ModuleChange] = {}
    kb = {k for k, li in before.line_items.items() if not li.is_header}
    ka = {k for k, li in after.line_items.items() if not li.is_header}
    added, removed = ka - kb, kb - ka

    # rename detection within a module
    renamed: dict[tuple[str, str], tuple[str, str]] = {}   # removed key -> added key
    by_mod_removed: dict[str, list] = {}
    for k in removed:
        by_mod_removed.setdefault(k[0], []).append(k)
    for k in sorted(added):
        cands = by_mod_removed.get(k[0], [])
        b_li = after.line_items[k]
        tb = _tree(b_li.formula)
        for r in cands:
            a_li = before.line_items[r]
            same_formula = tb is not None and _tree(a_li.formula) == tb
            same_input = tb is None and not a_li.formula and a_li.format_type == b_li.format_type and a_li.applies_to == b_li.applies_to
            if (same_formula or same_input) and r not in renamed:
                renamed[r] = k
                cands.remove(r)
                break

    for r, k in renamed.items():
        n, m = impact(k)
        d.line_items.append(LineItemChange(k[0], k[1], "renamed", renamed_from=r[1], impact_count=n, impact_modules=m,
                                           formula_before=before.line_items[r].formula, formula_after=after.line_items[k].formula))
    for k in sorted(added - set(renamed.values())):
        li = after.line_items[k]
        n, m = impact(k)
        d.line_items.append(LineItemChange(k[0], k[1], "added", impact_count=n, impact_modules=m, formula_after=li.formula))
    for k in sorted(removed - set(renamed)):
        li = before.line_items[k]
        d.line_items.append(LineItemChange(k[0], k[1], "removed", formula_before=li.formula))
    for k in sorted(kb & ka):
        a, b = before.line_items[k], after.line_items[k]
        fc = _li_fields(a, b)
        if fc:
            n, m = impact(k)
            d.line_items.append(LineItemChange(k[0], k[1], "changed", fields=fc, impact_count=n, impact_modules=m,
                                               formula_before=a.formula, formula_after=b.formula))

    # module-level changed rollup
    for li in d.line_items:
        if li.module in (ma - mb) or li.module in (mb - ma):
            continue
        mc = per_module.setdefault(li.module, ModuleChange(li.module, "changed"))
        if li.kind == "added": mc.line_items_added += 1
        elif li.kind == "removed": mc.line_items_removed += 1
        else: mc.line_items_changed += 1
    for name in sorted(mb & ma):
        if not (before.has_modules_export and after.has_modules_export):
            break   # module attributes only come from the Modules export; skip when either side lacks it
        a, b = before.modules[name], after.modules[name]
        fc = []
        for f in _MOD_FIELDS:
            va, vb = getattr(a, f), getattr(b, f)
            if isinstance(va, tuple): va = ", ".join(va)
            if isinstance(vb, tuple): vb = ", ".join(vb)
            if va != vb and (va or vb):
                fc.append(FieldChange(f, str(va), str(vb)))
        if fc:
            per_module.setdefault(name, ModuleChange(name, "changed")).fields = fc
    d.modules.extend(per_module[n] for n in sorted(per_module))
    d.line_items.sort(key=lambda c: (-c.impact_count, c.module, c.name))
    return d


def render_markdown(d: Diff, max_items: int = 200) -> str:
    s = d.summary
    out = [f"# Model diff: {d.before_name} -> {d.after_name}", "",
           f"Modules: +{s['modules_added']} -{s['modules_removed']} ~{s['modules_changed']}. "
           f"Line items: +{s['line_items_added']} -{s['line_items_removed']} ~{s['line_items_changed']} "
           f"renamed {s['line_items_renamed']}. Formula changes: {s['formula_changes']}.", ""]
    if d.modules:
        out += ["## Modules", "", "| Module | Change | +LI | -LI | ~LI | Fields |", "|---|---|---|---|---|---|"]
        for m in d.modules:
            f = "; ".join(f"{x.field}: {x.before} -> {x.after}" for x in m.fields)
            out.append(f"| {m.name} | {m.kind} | {m.line_items_added} | {m.line_items_removed} | {m.line_items_changed} | {f} |")
        out.append("")
    out += ["## Line items, by blast radius", "", "| Impact | Module | Line item | Change | Detail |", "|---|---|---|---|---|"]
    for li in d.line_items[:max_items]:
        if li.kind == "renamed":
            detail = f"was `{li.renamed_from}`"
        elif li.kind == "added":
            detail = f"`{li.formula_after[:80]}`" if li.formula_after else "input"
        elif li.kind == "removed":
            detail = f"`{li.formula_before[:80]}`" if li.formula_before else "input"
        else:
            parts = []
            for f in li.fields:
                if f.field == "formula":
                    parts.append(f"formula: `{f.before[:60]}` -> `{f.after[:60]}`")
                else:
                    parts.append(f"{f.field}: {f.before} -> {f.after}")
            detail = "; ".join(parts)
        imp = f"{li.impact_count} / {li.impact_modules} mod" if li.kind != "removed" else ""
        out.append(f"| {imp} | {li.module} | {li.name} | {li.kind} | {detail} |")
    if len(d.line_items) > max_items:
        out.append(f"| | | ... {len(d.line_items) - max_items} more | | |")
    return "\n".join(out)
