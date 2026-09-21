"""Command line for anaplan-grammar. Standard library only.

    anaplan-grammar parse   "FORMULA"                          AST as JSON, or references with --refs
    anaplan-grammar explain LINE_ITEMS.csv "Module.Line Item"  formula, references, used by, uses
    anaplan-grammar impact  LINE_ITEMS.csv "Module.Line Item"  everything downstream
    anaplan-grammar lineage LINE_ITEMS.csv "Module.Line Item"  everything upstream
    anaplan-grammar diff    BEFORE.csv AFTER.csv               change set with blast radius
    anaplan-grammar lint    LINE_ITEMS.csv                     findings
    anaplan-grammar health  LINE_ITEMS.csv                     the one-page report
    anaplan-grammar stats   LINE_ITEMS.csv                     graph statistics

Every model command accepts --modules MODULES.csv (adds module attributes),
--json (machine output), --out FILE (write instead of print). Line items
are named "Module.Line Item"; quote when the name has spaces.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

from . import __version__
from .parser import parse, references, ParseError
from .lexer import LexError
from .unparse import unparse
from .model import load_model
from .graph import build_graph
from . import diff as diffmod
from . import lint as lintmod
from . import health as healthmod
from .estate import load_estate
from .spec import build_spec
from . import opinion as opmod
from .review import render_review


def _key(s: str) -> tuple[str, str]:
    if "." not in s:
        sys.exit(f"line item must be Module.Line Item, got {s!r}")
    m, _, li = s.rpartition(".")
    return (m.strip(), li.strip())


def _find_key(model, s: str):
    if "." in s:
        k = _key(s)
        if k in model.line_items:
            return k
    # tolerate the dot inside a module name: try every split
    parts = s.split(".")
    for i in range(1, len(parts)):
        cand = (".".join(parts[:i]).strip(), ".".join(parts[i:]).strip())
        if cand in model.line_items:
            return cand
    # by line item name alone, if unique
    hits = [key for key in model.line_items if key[1] == s]
    if not hits and "." not in s:
        hits = [key for key in model.line_items if key[1].lower() == s.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        sys.exit(f"{s!r} exists in {len(hits)} modules: " + ", ".join(f"{a}.{b}" for a, b in hits[:8]))
    sys.exit(f"line item not found: {s!r}")


def _emit(args, text: str, data=None):
    out = json.dumps(data, indent=1, ensure_ascii=False) if (args.json and data is not None) else text
    if getattr(args, "out", None):
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        try:
            print(out)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(out.encode("utf-8", "replace"))


def _load(args, path=None, modules=None):
    name = getattr(args, "name", None) or Path(path or args.line_items).stem
    return load_model(path or args.line_items, modules or getattr(args, "modules", None), name=name)


# ---- commands ----

def cmd_parse(args):
    try:
        ast = parse(args.formula)
    except (ParseError, LexError) as e:
        sys.exit(f"parse error: {e}")
    if args.refs:
        refs = [".".join(p) for p in references(ast)]
        _emit(args, "\n".join(refs), refs)
    else:
        _emit(args, json.dumps(ast, indent=1, ensure_ascii=False) if not args.json else "", ast)


def cmd_explain(args):
    m = _load(args); g = build_graph(m); k = _find_key(m, args.line_item); li = m.line_items[k]
    uses = sorted(g.edges.get(k, ()))
    used_by = sorted(g.rev.get(k, ()))
    data = {
        "line_item": f"{k[0]}.{k[1]}", "format": li.format_type, "applies_to": list(li.applies_to),
        "time_scale": li.time_scale, "summary": li.summary, "cell_count": li.cell_count,
        "formula": li.formula, "references": [{"path": ".".join(r.path), "kind": r.kind} for r in g.refs.get(k, [])],
        "uses": [f"{a}.{b}" for a, b in uses], "used_by": [f"{a}.{b}" for a, b in used_by],
        "impact_count": len(g.impact(k)), "notes": li.notes,
    }
    lines = [f"{k[0]}.{k[1]}", f"  format      {li.format_type or 'input'}   applies to {', '.join(li.applies_to) or '-'}   time {li.time_scale or '-'}   cells {li.cell_count:,}",
             f"  formula     {li.formula or '(input)'}",
             f"  uses        {len(uses)}" + ("".join(f"\n              {a}.{b}" for a, b in uses[:30])),
             f"  used by     {len(used_by)}" + ("".join(f"\n              {a}.{b}" for a, b in used_by[:30])),
             f"  downstream  {data['impact_count']} line items in total"]
    if li.notes:
        lines.append(f"  notes       {li.notes}")
    _emit(args, "\n".join(lines), data)


def _closure_cmd(args, direction):
    m = _load(args); g = build_graph(m); k = _find_key(m, args.line_item)
    res = g.impact(k, args.depth) if direction == "impact" else g.lineage(k, args.depth)
    rows = sorted(res.items(), key=lambda kv: (kv[1], kv[0]))
    mods = {}
    for (mod, name), d in rows:
        mods.setdefault(mod, []).append((name, d))
    word = "downstream of" if direction == "impact" else "upstream of"
    lines = [f"{len(rows)} line items across {len(mods)} modules {word} {k[0]}.{k[1]}" + (f" (depth <= {args.depth})" if args.depth else "")]
    for mod in sorted(mods, key=lambda x: min(d for _, d in mods[x])):
        lines.append(f"  {mod}")
        for name, d in sorted(mods[mod], key=lambda x: (x[1], x[0])):
            lines.append(f"    {d:2d}  {name}")
    data = {"line_item": f"{k[0]}.{k[1]}", "direction": direction, "count": len(rows), "modules": len(mods),
            "items": [{"module": mod, "line_item": name, "distance": d} for (mod, name), d in rows]}
    _emit(args, "\n".join(lines), data)


def cmd_impact(args): _closure_cmd(args, "impact")
def cmd_lineage(args): _closure_cmd(args, "lineage")


def cmd_diff(args):
    b = load_model(args.before, args.before_modules, name=Path(args.before).stem)
    a = load_model(args.after, args.after_modules, name=Path(args.after).stem)
    d = diffmod.diff_models(b, a)
    _emit(args, diffmod.render_markdown(d, max_items=args.max), d.to_dict())
    if args.fail_on_change and any(d.summary.values()):
        sys.exit(2)


def _overrides(args):
    ov = {}
    for item in args.threshold or []:
        try:
            rid, kv = item.split(":", 1); key, val = kv.split("=", 1)
        except ValueError:
            sys.exit(f"--threshold wants RULE:key=value, got {item!r}")
        try:
            val = int(val)
        except ValueError:
            pass
        ov.setdefault(rid, {})[key] = val
    return ov


def cmd_lint(args):
    m = _load(args); g = build_graph(m)
    res = lintmod.lint(m, g, rules=args.rules, overrides=_overrides(args))
    if args.min_severity:
        order = lintmod.SEV_ORDER
        res.findings = [f for f in res.findings if order[f.severity] <= order[args.min_severity]]
    _emit(args, lintmod.render_markdown(res, max_per_rule=args.max), res.to_dict())
    if args.fail_on:
        order = lintmod.SEV_ORDER
        if any(order[f.severity] <= order[args.fail_on] for f in res.findings):
            sys.exit(2)


def cmd_health(args):
    m = _load(args); g = build_graph(m)
    r = healthmod.health(m, g, overrides=_overrides(args))
    _emit(args, healthmod.render_markdown(r), r.to_dict())


def _estate(args):
    return load_estate(getattr(args, "lists", None), getattr(args, "actions", None), getattr(args, "ux", None))


def cmd_spec(args):
    m = _load(args); g = build_graph(m); e = _estate(args)
    s = build_spec(m, g, e)
    _emit(args, s.markdown(), s.facts)


def cmd_opinion(args):
    m = _load(args); g = build_graph(m); e = _estate(args)
    s = build_spec(m, g, e); lr = lintmod.lint(m, g); h = healthmod.health(m, g, lr)
    if args.mode == "prompt":
        _emit(args, opmod.prompt(s, lr, h)); return
    if args.mode == "ingest":
        txt = Path(args.response).read_text(encoding="utf-8")
        op = opmod.ingest(s, lr, m, txt, provider=args.provider or "ingested")
    else:
        import os
        key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            sys.exit("set ANTHROPIC_API_KEY or pass --api-key; or use `opinion prompt` then `opinion ingest`")
        op = opmod.run(s, lr, m, key, model_id=args.llm, critique=not args.no_critique, health=h)
    _emit(args, opmod.render_markdown(op), op.to_dict())


def cmd_review(args):
    m = _load(args); g = build_graph(m); e = _estate(args)
    s = build_spec(m, g, e); lr = lintmod.lint(m, g, overrides=_overrides(args)); h = healthmod.health(m, g, lr)
    op = None
    if args.response:
        op = opmod.ingest(s, lr, m, Path(args.response).read_text(encoding="utf-8"), provider=args.provider or "ingested")
    md = render_review(s, h, op, signed_by=args.signed_by or "")
    if args.html:
        from .htmlout import md_to_html
        Path(args.html).write_text(md_to_html(md, f"{m.name} Architect's Review"), encoding="utf-8")
        print(f"wrote {args.html}")
    _emit(args, md, {"spec": s.facts, "health": h.to_dict(), "opinion": op.to_dict() if op else None})


def cmd_stats(args):
    m = _load(args); g = build_graph(m); st = g.stats()
    st["dimensions"] = sorted(m.dimensions)[:50]
    lines = [f"{k:14s} {v}" for k, v in st.items() if k != "dimensions"] + [f"dimensions     {len(m.dimensions)}"]
    _emit(args, "\n".join(lines), st)


def cmd_rules(args):
    rows = [{"id": r.id, "severity": r.severity, "source": r.source, "title": r.title, "thresholds": r.thresholds, "planual": list(r.planual), "description": r.description}
            for r in lintmod.RULES.values()]
    lines = [f"{r['id']:16s} {r['severity']:8s} {r['source']:8s} {r['title']}" + (f"   {r['thresholds']}" if r['thresholds'] else "") + (f"   Planual {', '.join(r['planual'])}" if r['planual'] else "") for r in rows]
    _emit(args, "\n".join(lines), rows)


def main(argv=None):
    p = argparse.ArgumentParser(prog="anaplan-grammar", description="Parse, graph, diff, lint and score Anaplan models from their exports.")
    p.add_argument("--version", action="version", version=f"anaplan-grammar {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def model_args(sp, modules=True):
        sp.add_argument("line_items", help="Line Items grid export (CSV)")
        if modules:
            sp.add_argument("--modules", help="Modules grid export (CSV); adds module attributes")
        sp.add_argument("--name", help="model name for the report title")
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        sp.add_argument("--out", help="write output to this file")

    s = sub.add_parser("parse", help="parse one formula"); s.add_argument("formula"); s.add_argument("--refs", action="store_true", help="list references instead of the tree")
    s.add_argument("--json", action="store_true"); s.add_argument("--out"); s.set_defaults(fn=cmd_parse)

    s = sub.add_parser("explain", help="one line item: formula, references, uses, used by"); model_args(s); s.add_argument("line_item"); s.set_defaults(fn=cmd_explain)
    s = sub.add_parser("impact", help="everything downstream of a line item"); model_args(s); s.add_argument("line_item"); s.add_argument("--depth", type=int); s.set_defaults(fn=cmd_impact)
    s = sub.add_parser("lineage", help="everything upstream of a line item"); model_args(s); s.add_argument("line_item"); s.add_argument("--depth", type=int); s.set_defaults(fn=cmd_lineage)

    s = sub.add_parser("diff", help="change set between two exports")
    s.add_argument("before"); s.add_argument("after")
    s.add_argument("--before-modules"); s.add_argument("--after-modules")
    s.add_argument("--max", type=int, default=200, help="rows in the line-item table")
    s.add_argument("--fail-on-change", action="store_true", help="exit 2 if anything changed (for CI)")
    s.add_argument("--json", action="store_true"); s.add_argument("--out"); s.set_defaults(fn=cmd_diff)

    s = sub.add_parser("lint", help="findings against the rule set"); model_args(s)
    s.add_argument("--rules", nargs="*", help="only these rule ids")
    s.add_argument("--threshold", action="append", metavar="RULE:key=value", help="override a rule threshold, e.g. A-LI-COUNT:max_line_items=40")
    s.add_argument("--min-severity", choices=["critical", "major", "minor", "info"], help="hide findings below this")
    s.add_argument("--fail-on", choices=["critical", "major", "minor", "info"], help="exit 2 if any finding at or above this (for CI)")
    s.add_argument("--max", type=int, default=15, help="rows per rule in the table"); s.set_defaults(fn=cmd_lint)

    s = sub.add_parser("health", help="the one-page health report"); model_args(s)
    s.add_argument("--threshold", action="append", metavar="RULE:key=value"); s.set_defaults(fn=cmd_health)

    def estate_args(sp):
        sp.add_argument("--lists", help="General Lists export (CSV)")
        sp.add_argument("--actions", help="Actions export (CSV)")
        sp.add_argument("--ux", help="folder of UX page PDFs (names only are used)")

    s = sub.add_parser("spec", help="the as-built specification"); model_args(s); estate_args(s); s.set_defaults(fn=cmd_spec)

    s = sub.add_parser("opinion", help="the architect's opinion: prompt | ingest | run"); model_args(s); estate_args(s)
    s.add_argument("mode", choices=["prompt", "ingest", "run"])
    s.add_argument("--response", help="ingest: file with the model's JSON response")
    s.add_argument("--provider", help="ingest: label for who wrote the response")
    s.add_argument("--api-key", help="run: Anthropic API key (or ANTHROPIC_API_KEY)")
    s.add_argument("--llm", default="claude-sonnet-5", help="run: model id")
    s.add_argument("--no-critique", action="store_true", help="run: skip the second, critique pass")
    s.set_defaults(fn=cmd_opinion)

    s = sub.add_parser("review", help="spec + health + opinion in one document"); model_args(s); estate_args(s)
    s.add_argument("--response", help="file with an opinion JSON response to include")
    s.add_argument("--provider"); s.add_argument("--signed-by", help="name to put on the cover")
    s.add_argument("--html", help="also write a self-contained HTML page here")
    s.add_argument("--threshold", action="append", metavar="RULE:key=value"); s.set_defaults(fn=cmd_review)

    s = sub.add_parser("stats", help="graph statistics"); model_args(s); s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("rules", help="list the lint rules"); s.add_argument("--json", action="store_true"); s.add_argument("--out"); s.set_defaults(fn=cmd_rules)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
