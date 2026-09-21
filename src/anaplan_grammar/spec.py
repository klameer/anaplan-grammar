"""The as-built specification: how the model is constructed, generated
from the exports. Deterministic. This is the document the architect
would write in week one, and the evidence the opinion layer must cite.

Sections
  1 Purpose and shape      DISCO layout, module families, flows between them
  2 Dimensional design     lists and hierarchies, where each is used, dense vs sparse
  3 Data in, data out      imports and their targets, exports and their sources, processes
  4 Versions, time, currency  how the model handles them, from the SYS modules
  5 Calculation chains     for each export and each output module, lineage back to inputs
  6 The systems layer      every SYS module and what it feeds
  7 Documentation as found module notes, verbatim
  8 What the exports do not show

Every object named is a real module, line item, list or action, so the
opinion layer's reference validator can check its citations against this.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import re
from .model import Model
from .graph import Graph
from .estate import Estate

DISCO = {"D": "Data", "I": "Inputs", "S": "System", "C": "Calculation", "O": "Output", "F": "Filter"}
_PREFIX = re.compile(r"^([DISCOF])\s+([A-Z][A-Za-z0-9]*?)(\d*[a-z]?)\b")


# Convention without the letter: "OUT01 Board Pack", "CAL02 Revenue", "INP01 Volumes", "SYS00 Settings", "DAT01 ...", "FIL01 ..."
_CODE = re.compile(r"^(OUT|CAL|INP|SYS|DAT|FIL)([A-Z]*)(\d*[a-z]?)\b")
_CODE_ROLE = {"OUT": "O", "CAL": "C", "INP": "I", "SYS": "S", "DAT": "D", "FIL": "F"}


def disco_role(module: str) -> tuple[str, str]:
    """(role letter, family code) from a DISCO-style module name, else ('?', '')."""
    m = _PREFIX.match(module)
    if m:
        return m.group(1), m.group(2)
    m = _CODE.match(module)
    if m:
        return _CODE_ROLE[m.group(1)], m.group(1) + m.group(2)
    return "?", ""


@dataclass
class Spec:
    model: Model
    graph: Graph
    estate: Estate
    sections: dict[str, str] = field(default_factory=dict)   # title -> markdown
    facts: dict = field(default_factory=dict)                # machine-readable for the opinion layer

    def markdown(self) -> str:
        out = [f"# As-built specification: {self.model.name}", ""]
        for title, body in self.sections.items():
            out += [f"## {title}", "", body, ""]
        return "\n".join(out)


def _real_modules(m: Model):
    return {n: mod for n, mod in m.modules.items() if mod.line_items and not re.match(r"^[-▼▲=\s#]", n)}


def build_spec(m: Model, g: Graph, e: Estate) -> Spec:
    s = Spec(m, g, e)
    mods = _real_modules(m)
    roles = {n: disco_role(n) for n in mods}
    by_role = defaultdict(list)
    for n, (r, fam) in roles.items():
        by_role[r].append(n)
    families = defaultdict(list)
    for n, (r, fam) in roles.items():
        if fam:
            families[fam].append(n)
    me = g.module_edges()

    # ---------- 1 purpose and shape ----------
    lines = []
    lines.append(f"{len(mods)} modules, {sum(1 for li in m.line_items.values() if not li.is_header):,} line items, "
                 f"{len(e.lists) - sum(1 for l in e.lists.values() if l.is_header)} lists, "
                 f"{sum(1 for a in e.actions.values() if a.kind == 'import')} imports, "
                 f"{sum(1 for a in e.actions.values() if a.kind == 'export')} exports, "
                 f"{len(e.processes)} processes, {len(e.ux_pages)} UX pages.")
    lines.append("")
    lines.append("| DISCO role | Modules | Line items | Cells (export) |")
    lines.append("|---|---|---|---|")
    role_stats = {}
    for r in "DISCOF?":
        ns = by_role.get(r, [])
        if not ns:
            continue
        li = sum(len(mods[n].line_items) for n in ns)
        cells = sum(mods[n].cell_count for n in ns)
        role_stats[r] = (len(ns), li, cells)
        lines.append(f"| {r} {DISCO.get(r, 'unprefixed')} | {len(ns)} | {li:,} | {cells:,} |")
    lines.append("")
    # families: group by code, show largest
    fam_rows = sorted(((fam, ns) for fam, ns in families.items()), key=lambda x: -sum(mods[n].cell_count for n in x[1]))
    lines.append("Module families (by name code), largest first:")
    lines.append("")
    lines.append("| Family | Modules | Roles | Line items | Cells (export) | Feeds |")
    lines.append("|---|---|---|---|---|---|")
    fam_feeds = {}
    for fam, ns in fam_rows[:25]:
        rs = "".join(sorted({roles[n][0] for n in ns}))
        li = sum(len(mods[n].line_items) for n in ns)
        cells = sum(mods[n].cell_count for n in ns)
        feeds = Counter()
        for n in ns:
            for used_by in (a for a, bs in me.items() if n in bs):
                f2 = roles.get(used_by, ("?", ""))[1]
                if f2 and f2 != fam:
                    feeds[f2] += 1
        fam_feeds[fam] = feeds
        lines.append(f"| {fam} | {len(ns)} | {rs} | {li} | {cells:,} | {', '.join(f for f, _ in feeds.most_common(4))} |")
    lines.append("")
    # flow: role-level edges
    role_flow = Counter()
    for a, bs in me.items():
        for b in bs:
            role_flow[(roles.get(b, ('?', ''))[0], roles.get(a, ('?', ''))[0])] += 1   # b feeds a
    lines.append("Flow between roles (module references, source role to consuming role):")
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart LR")
    for r in "DISCOF":
        if r in role_stats:
            lines.append(f"  {r}[\"{r} {DISCO[r]}<br/>{role_stats[r][0]} modules\"]")
    for (src, dst), n in role_flow.most_common():
        if src in role_stats and dst in role_stats and src != dst and n >= 3:
            lines.append(f"  {src} -- {n} --> {dst}")
    lines.append("```")
    s.sections["1. Purpose and shape"] = "\n".join(lines)
    s.facts["roles"] = {r: {"modules": v[0], "line_items": v[1], "cells": v[2]} for r, v in role_stats.items()}
    s.facts["families"] = {fam: {"modules": ns, "feeds": dict(fam_feeds.get(fam, {}))} for fam, ns in fam_rows}
    s.facts["role_flow"] = {f"{a}->{b}": n for (a, b), n in role_flow.items()}

    # ---------- 2 dimensional design ----------
    lines = []
    real_lists = [l for l in e.lists.values() if not l.is_header]
    # hierarchies: chains via parent
    children = defaultdict(list)
    for l in real_lists:
        if l.parent:
            children[l.parent].append(l.name)
    roots = [l for l in real_lists if not l.parent and l.name in children]
    lines.append("Hierarchies (top down, with item counts):")
    lines.append("")
    hier = []
    def walk(name, depth):
        l = e.lists.get(name)
        if not l:
            return
        hier.append((name, depth, l.item_count, l.numbered, len(l.subsets)))
        for c in children.get(name, []):
            walk(c, depth + 1)
    for r in roots:
        walk(r.name, 0)
    for name, depth, n, num, ns in hier:
        lines.append(f"{'  ' * depth}- {name}: {n:,} items" + (" (numbered)" if num else "") + (f", {ns} subsets" if ns else ""))
    flat = sorted((l for l in real_lists if not l.parent and l.name not in children and l.item_count > 0), key=lambda l: -l.item_count)
    lines.append("")
    lines.append("Flat lists, largest first:")
    lines.append("")
    lines.append("| List | Items | Numbered | Subsets | Properties | Used as dimension in | As format in | In formulas |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for l in flat[:25]:
        lines.append(f"| {l.name} | {l.item_count:,} | {'yes' if l.numbered else ''} | {len(l.subsets)} | {len(l.properties)} | {len(l.in_applies_to)} | {len(l.as_format)} | {len(l.in_formula)} |")
    # dimension usage from applies-to across modules
    dim_use = Counter()
    for mod in mods.values():
        for d in mod.applies_to:
            dim_use[d] += 1
    lines.append("")
    lines.append("Dimensions by number of modules that use them:")
    lines.append("")
    lines.append("| Dimension | Modules |")
    lines.append("|---|---|")
    for d, n in dim_use.most_common(20):
        lines.append(f"| {d} | {n} |")
    # dense/sparse: line items with the most dimensions
    multi = sorted(((len(li.applies_to), li) for li in m.line_items.values() if not li.is_header), key=lambda x: -x[0])[:10]
    lines.append("")
    lines.append("Most dimensioned line items (where the cube is widest):")
    lines.append("")
    for n, li in multi:
        lines.append(f"- {li.module}.{li.name}: {n} dimensions ({', '.join(li.applies_to)}), {li.cell_count:,} cells")
    s.sections["2. Dimensional design"] = "\n".join(lines)
    s.facts["hierarchies"] = hier
    s.facts["dimension_use"] = dict(dim_use.most_common())
    s.facts["lists"] = {l.name: {"items": l.item_count, "parent": l.parent, "numbered": l.numbered, "subsets": list(l.subsets)} for l in real_lists}

    # ---------- 3 data in, data out ----------
    lines = []
    imports = [a for a in e.actions.values() if a.kind == "import"]
    exports = [a for a in e.actions.values() if a.kind == "export"]
    tgt = Counter(a.target for a in imports)
    lines.append(f"{len(imports)} import actions into {len(tgt)} targets; {len(exports)} export actions; "
                 f"{sum(1 for a in e.actions.values() if a.kind == 'delete')} delete actions; {len(e.processes)} processes.")
    lines.append("")
    lines.append("Import targets (modules and lists), by number of import actions:")
    lines.append("")
    lines.append("| Target | Imports | Kind |")
    lines.append("|---|---|---|")
    for t, n in tgt.most_common(20):
        kind = "module" if t in m.modules else "list" if t in e.lists else "?"
        lines.append(f"| {t} | {n} | {kind} |")
    lines.append("")
    lines.append("Exports and their source modules:")
    lines.append("")
    lines.append("| Export | From | In process |")
    lines.append("|---|---|---|")
    for a in exports:
        lines.append(f"| {a.name} | {a.target} | {', '.join(a.processes)} |")
    lines.append("")
    lines.append("Processes, longest last run first:")
    lines.append("")
    lines.append("| Process | Steps | Last run | Duration |")
    lines.append("|---|---|---|---|")
    for p in sorted(e.processes.values(), key=lambda p: -p.duration_ms):
        lines.append(f"| {p.name} | {len(p.steps) or '?'} | {p.last_run[:10]} | {p.duration_ms / 1000:.0f} s |")
    # data modules with no import
    d_mods = by_role.get("D", [])
    fed = {a.target for a in imports}
    orphans = [n for n in d_mods if n not in fed]
    if orphans:
        lines.append("")
        lines.append(f"Data (D) modules with no import action targeting them: {', '.join(orphans[:10])}" + (" ..." if len(orphans) > 10 else ""))
    s.sections["3. Data in, data out"] = "\n".join(lines)
    s.facts["imports"] = {a.name: a.target for a in imports}
    s.facts["exports"] = {a.name: a.target for a in exports}
    s.facts["processes"] = {p.name: {"steps": p.steps, "duration_ms": p.duration_ms, "last_run": p.last_run} for p in e.processes.values()}

    # ---------- 4 versions, time, currency ----------
    lines = []
    ts = Counter(mod.time_scale or "-" for mod in mods.values())
    vs = Counter(mod.versions or "-" for mod in mods.values())
    lines.append("Time scale by module: " + ", ".join(f"{k} ({n})" for k, n in ts.most_common()))
    lines.append("")
    lines.append("Versions by module: " + ", ".join(f"{k} ({n})" for k, n in vs.most_common()))
    lines.append("")
    # version-related line items
    vlines = [li for li in m.line_items.values() if not li.is_header and re.search(r"version|switchover|actual\?|forecast\?|budget\?", li.name, re.I) and li.module.startswith("S ")]
    if vlines:
        lines.append("Version and switchover logic in system modules:")
        lines.append("")
        for li in vlines[:15]:
            lines.append(f"- {li.module}.{li.name}: `{li.formula[:110]}`" if li.formula else f"- {li.module}.{li.name}: input")
    ccy = [n for n in mods if re.search(r"currenc|ccy|fx", n, re.I)]
    if ccy:
        lines.append("")
        lines.append("Currency handling lives in: " + ", ".join(ccy[:12]))
        ccy_hub = [(k, len(v)) for k, v in g.rev.items() if k[0] in ccy]
        ccy_hub.sort(key=lambda kv: -kv[1])
        if ccy_hub:
            k, n = ccy_hub[0]
            imp = g.impact(k)
            lines.append(f"The rate that matters: {k[0]}.{k[1]}, {n} direct dependents, {len(imp)} downstream across {len({x[0] for x in imp})} modules.")
    s.sections["4. Versions, time and currency"] = "\n".join(lines)
    s.facts["time_scales"] = dict(ts)
    s.facts["versions"] = dict(vs)

    # ---------- 5 calculation chains to outputs ----------
    lines = []
    chains = {}
    targets = []
    for a in exports:
        if a.target in mods:
            targets.append((f"export {a.name}", a.target))
    for n in by_role.get("O", []):
        if not any(t == n for _, t in targets):
            targets.append(("output module", n))
    lines.append("For each export and output module: how many line items feed it, through how many modules, "
                 "and which inputs it ultimately rests on. Depth is the longest dependency path.")
    lines.append("")
    lines.append("| Output | Line items | Upstream line items | Upstream modules | Depth | Input modules it rests on |")
    lines.append("|---|---|---|---|---|---|")
    rows = []
    for label, modname in targets:
        keys = [k for k in m.line_items if k[0] == modname and m.line_items[k].formula]
        up = {}
        for k in keys:
            for x, d in g.lineage(k).items():
                up[x] = max(up.get(x, 0), d)
        upmods = {x[0] for x in up}
        inputs = sorted({x[0] for x in up if not m.line_items[x].formula and not m.line_items[x].is_header})
        depth = max(up.values(), default=0)
        rows.append((label, modname, len(keys), len(up), len(upmods), depth, inputs))
        chains[modname] = {"label": label, "line_items": len(keys), "upstream": len(up), "upstream_modules": sorted(upmods), "depth": depth, "inputs": inputs}
    rows.sort(key=lambda r: -r[3])
    for label, modname, nli, nup, nmods, depth, inputs in rows[:30]:
        lines.append(f"| {modname} ({label}) | {nli} | {nup:,} | {nmods} | {depth} | {', '.join(inputs[:5])}{' ...' if len(inputs) > 5 else ''} |")
    s.sections["5. Calculation chains to outputs"] = "\n".join(lines)
    s.facts["chains"] = chains

    # ---------- 6 the systems layer ----------
    lines = []
    sys_mods = sorted(by_role.get("S", []), key=lambda n: -len({a for a, bs in me.items() if n in bs}))
    lines.append("| System module | Line items | Feeds modules | Notes |")
    lines.append("|---|---|---|---|")
    for n in sys_mods[:40]:
        feeds = sorted({a for a, bs in me.items() if n in bs})
        lines.append(f"| {n} | {len(mods[n].line_items)} | {len(feeds)}: {', '.join(feeds[:4])}{' ...' if len(feeds) > 4 else ''} | {mods[n].notes[:80]} |")
    s.sections["6. The systems layer"] = "\n".join(lines)
    s.facts["systems"] = {n: sorted({a for a, bs in me.items() if n in bs}) for n in sys_mods}

    # ---------- 7 documentation as found ----------
    lines = []
    noted = [(n, mod.notes.strip()) for n, mod in mods.items() if mod.notes.strip()]
    lines.append(f"{len(noted)} of {len(mods)} modules carry notes. Verbatim:")
    lines.append("")
    for n, note in noted:
        lines.append(f"- **{n}**: {note[:300]}")
    lnotes = [(l.name, l.notes.strip()) for l in real_lists if l.notes.strip()]
    if lnotes:
        lines.append("")
        lines.append(f"{len(lnotes)} lists carry notes:")
        for n, note in lnotes:
            lines.append(f"- **{n}**: {note[:200]}")
    s.sections["7. Documentation as found"] = "\n".join(lines)
    s.facts["notes"] = dict(noted)

    # ---------- 8 what the exports do not show ----------
    lines = [
        "- Saved views, dashboards and UX page contents. The page names are known "
        f"({len(e.ux_pages)} pages) but not which modules each shows, so 'unreferenced' means by no formula, not unused.",
        "- Line-item subset membership, so COLLECT() sources are not in the graph.",
        "- Cell values, so nothing here says whether a number is right.",
        "- Model history, so nothing here says when a design decision was made or by whom.",
        "- Import mappings at field level, so cross-model lineage stops at the action.",
    ]
    if e.ux_pages:
        lines.append("")
        lines.append("UX pages, by name: " + "; ".join(e.ux_pages[:48]))
    s.sections["8. What the exports do not show"] = "\n".join(lines)
    s.facts["ux_pages"] = e.ux_pages
    return s
