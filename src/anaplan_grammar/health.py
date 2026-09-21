"""Model health report: five scores and a one-page summary, generated
from the exports. Mirrors the shape of a partner health check (interviews
excluded) and Operis's issues-report format, so a finance director
recognises it.

Categories and what feeds them:
  structure     module sizes, empty modules, subsidiary calculation views, hubs
  formulas      IF counts, length, mixed clauses, unguarded divides, hard-codes, parse failures
  performance   summary methods on large items, text formats, FINDITEM/joins/system fns in large items, daisy chains
  integrity     cycles (non-deliberate weighted heavily), unreferenced calculations
  governance    notes coverage, naming consistency (module prefix convention), DISCO fit

Scoring: each category starts at 100 and loses points per finding,
weighted by severity and scaled by model size so a 17,000-line-item
model is not punished for being large. Floors at 0. The overall score is
the mean. Scores are for ranking findings and tracking a model over
time, not for comparing two different models.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from collections import Counter, defaultdict
import re, math, datetime
from .model import Model
from .graph import Graph, build_graph
from .lint import lint, LintResult, RULES, Finding

CATEGORY_OF = {
    "A-LI-COUNT": "structure", "G-EMPTY-MODULE": "structure", "A-SUBSIDIARY": "structure", "G-HUB": "structure",
    "A-IF-COUNT": "formulas", "F-LONG": "formulas", "F-MIXED-CLAUSE": "formulas", "F-DIVIDE": "formulas",
    "F-HARDCODE": "formulas", "F-PARSE": "formulas",
    "A-SUMMARY-ON": "performance", "A-TEXT-FORMAT": "performance", "A-FINDITEM": "performance",
    "A-TEXT-JOIN": "performance", "A-SYSTEMS-FN": "performance", "A-DAISY": "performance",
    "G-CYCLE": "integrity", "G-UNUSED": "integrity",
    "H-NOTES": "governance",
}
SEV_WEIGHT = {"critical": 12.0, "major": 3.0, "minor": 0.6, "info": 0.15}
CATEGORIES = ["structure", "formulas", "performance", "integrity", "governance"]


@dataclass
class Score:
    category: str
    score: int
    findings: int
    top: list[str]          # up to 3 one-line findings


@dataclass
class HealthReport:
    model_name: str
    generated: str
    overall: int
    scores: list[Score]
    stats: dict
    top_findings: list[Finding]
    recommendations: list[str]
    lint: LintResult
    naming: dict

    def to_dict(self):
        return {"model": self.model_name, "generated": self.generated, "overall": self.overall,
                "scores": [asdict(s) for s in self.scores], "stats": self.stats, "naming": self.naming,
                "top_findings": [asdict(f) | {"object": f.object} for f in self.top_findings],
                "recommendations": self.recommendations, "lint": self.lint.to_dict()}


def _naming(m: Model) -> dict:
    """Module prefix convention: share of modules whose name starts with an
    upper-case code (SYS01, CAL02, 'IN - ', 'OUT - ') and the prefixes seen."""
    real = [n for n, mod in m.modules.items() if mod.line_items and not re.match(r"^[-▼▲=\s#]", n)]
    pat = re.compile(r"^([A-Z]{2,5})\s*[0-9]*\s*[-_ ]")
    disco = re.compile(r"^([DISCOF])\s+[A-Z]{2,}[A-Za-z0-9_-]*\s")   # "C CALPROJ01 ...", "S SYS00 ...", "O BUD11 ..."
    pref = Counter()
    hit = 0
    for n in real:
        mm = disco.match(n) or pat.match(n)
        if mm:
            hit += 1; pref[mm.group(1)] += 1
    return {"modules": len(real), "with_prefix": hit, "share": round(hit / len(real), 2) if real else 0,
            "prefixes": dict(pref.most_common(12))}


def _stats(m: Model, g: Graph) -> dict:
    lis = [li for li in m.line_items.values() if not li.is_header]
    cells = sorted(((li.cell_count, li) for li in lis), key=lambda x: -x[0])
    total_cells = sum(li.cell_count for li in lis)
    by_mod = Counter()
    for li in lis:
        by_mod[li.module] += li.cell_count
    fmt = Counter(li.format_type or "input/none" for li in lis)
    st = g.stats()
    return {
        "modules": len([n for n, mod in m.modules.items() if mod.line_items]),
        "line_items": len(lis), "with_formula": st["with_formula"], "inputs": len(lis) - st["with_formula"],
        "total_cells": total_cells,
        "top_modules_by_cells": [(n, c, round(100 * c / total_cells, 1) if total_cells else 0) for n, c in by_mod.most_common(10)],
        "top_line_items_by_cells": [(f"{li.module}.{li.name}", c) for c, li in cells[:10]],
        "formats": dict(fmt.most_common()),
        "edges": st["edges"], "module_edges": st["module_edges"],
        "dimensions": len(m.dimensions), "parse_errors": st["parse_errors"],
        "hubs": [(f"{k[0]}.{k[1]}", n) for k, n in g.hubs(10)],
        "unreferenced": len(g.unused()), "cycles": len(g.cycles()), "daisy_chains": len(g.daisy_chains()),
    }


def _score(findings: list[Finding], size: int) -> int:
    """Density scoring: severity-weighted findings per 100 line items, mapped
    through 100 * exp(-density / 12). A model with one major finding per 100
    line items scores about 78; one per 25 scores about 37. Small models use
    a floor of 300 line items so a fixture is not punished for being tiny.
    Scores rank and track; they do not compare models of different purpose."""
    per100 = max(size, 300) / 100.0
    density = sum(SEV_WEIGHT[f.severity] for f in findings) / per100
    return max(0, min(100, int(round(100 * math.exp(-density / 12.0)))))


def _recommend(by_cat: dict[str, list[Finding]], st: dict) -> list[str]:
    recs = []
    c = Counter(f.rule for fs in by_cat.values() for f in fs)
    crit = [f for fs in by_cat.values() for f in fs if f.severity == "critical"]
    if crit:
        recs.append(f"Resolve {len(crit)} critical finding(s) first: " + "; ".join(f"{f.object} ({f.rule})" for f in crit[:3]) + ".")
    if c.get("F-MIXED-CLAUSE"):
        recs.append(f"Split the {c['F-MIXED-CLAUSE']} formulas that mix SUM with LOOKUP or SELECT; Anaplan names this the single largest calculation-time cause.")
    if c.get("F-DIVIDE"):
        recs.append(f"Guard the {c['F-DIVIDE']} unguarded divisions (DIVIDE() or an IF) so a zero denominator cannot put Infinity into a summary.")
    if c.get("A-LI-COUNT"):
        recs.append(f"Split the {c['A-LI-COUNT']} modules over 50 line items along DISCO lines.")
    if c.get("A-DAISY"):
        recs.append(f"Collapse the {c['A-DAISY']} pass-through chains so each consumer references the source directly.")
    if c.get("A-SUMMARY-ON"):
        recs.append(f"Turn summaries off on the {c['A-SUMMARY-ON']} large line items no formula aggregates; this is the cheapest workspace saving available.")
    if c.get("H-NOTES"):
        recs.append("Add a purpose note to every module, largest first; the next builder starts there.")
    top = st["top_modules_by_cells"][:1]
    if top and top[0][2] >= 25:
        recs.append(f"{top[0][0]} holds {top[0][2]}% of all cells; review its dimensionality before anything else.")
    return recs[:6]


def health(model: Model, graph: Graph | None = None, lint_result: LintResult | None = None, overrides: dict | None = None) -> HealthReport:
    g = graph or build_graph(model)
    lr = lint_result or lint(model, g, overrides=overrides)
    st = _stats(model, g)
    by_cat: dict[str, list[Finding]] = defaultdict(list)
    for f in lr.findings:
        by_cat[CATEGORY_OF.get(f.rule, "governance")].append(f)
    size = st["line_items"]
    scores = []
    for cat in CATEGORIES:
        fs = by_cat.get(cat, [])
        sc = _score(fs, size)
        if cat == "governance":
            # notes coverage and naming feed governance directly
            nm = _naming(model)
            notes = [f for f in fs if f.rule == "H-NOTES"]
            if notes:
                a, b = notes[0].value.split("/")
                sc = int(round(100 * (1 - int(a) / max(int(b), 1)) * 0.6 + 100 * nm["share"] * 0.4))
            else:
                sc = int(round(60 + 40 * nm["share"]))
        top = [f"{f.object}: {f.message}" for f in fs[:3]]
        scores.append(Score(cat, sc, len(fs), top))
    overall = int(round(sum(s.score for s in scores) / len(scores)))
    top_findings = [f for f in lr.findings if f.severity in ("critical", "major")][:10]
    return HealthReport(model.name, datetime.date.today().isoformat(), overall, scores, st, top_findings,
                        _recommend(by_cat, st), lr, _naming(model))


def render_markdown(r: HealthReport) -> str:
    st = r.stats
    out = [f"# Model health: {r.model_name}", "",
           f"Generated {r.generated} from the Line Items and Modules exports. Unsigned. "
           f"Scores rank findings and track this model over time; they do not compare models.", "",
           f"## Overall {r.overall} / 100", "",
           "| Category | Score | Findings | Top finding |", "|---|---|---|---|"]
    for s in r.scores:
        out.append(f"| {s.category} | **{s.score}** | {s.findings} | {s.top[0] if s.top else ''} |")
    out += ["", "## Model at a glance", "",
            f"| | |", "|---|---|",
            f"| Modules | {st['modules']} |", f"| Line items | {st['line_items']:,} ({st['with_formula']:,} calculated, {st['inputs']:,} input) |",
            f"| Cells (as reported by the export) | {st['total_cells']:,} |", f"| Dimensions | {st['dimensions']} |",
            f"| Formula references | {st['edges']:,} edges, {st['module_edges']:,} module-to-module |",
            f"| Circular references | {st['cycles']} |", f"| Pass-through chains | {st['daisy_chains']} |",
            f"| Calculated but unreferenced | {st['unreferenced']:,} |",
            f"| Naming convention | {r.naming['with_prefix']} of {r.naming['modules']} modules carry a prefix ({', '.join(list(r.naming['prefixes'])[:6])}) |",
            "", "Largest modules by cells:", "", "| Module | Cells | Share |", "|---|---|---|"]
    for n, c, p in st["top_modules_by_cells"][:8]:
        out.append(f"| {n} | {c:,} | {p}% |")
    out += ["", "Most depended-on line items:", "", "| Line item | Direct dependents |", "|---|---|"]
    for n, c in st["hubs"][:8]:
        out.append(f"| {n} | {c} |")
    out += ["", "## Top findings", "", "| Severity | Rule | Object | Finding | Fix |", "|---|---|---|---|---|"]
    for f in r.top_findings:
        out.append(f"| {f.severity} | {f.rule} | {f.object} | {f.message} | {f.fix} |")
    out += ["", "## Recommendations", ""]
    for i, rec in enumerate(r.recommendations, 1):
        out.append(f"{i}. {rec}")
    out += ["", "## Findings by rule", "", "| Rule | Severity | Source | Planual | Count |", "|---|---|---|---|---|"]
    for rid, n in sorted(r.lint.counts["by_rule"].items(), key=lambda kv: -kv[1]):
        rr = RULES[rid]
        out.append(f"| {rid} {rr.title} | {rr.severity} | {rr.source} | {', '.join(rr.planual)} | {n} |")
    out += ["", "Full findings: run the lint report. Rules and thresholds: `anaplan_grammar.lint.RULES`.", ""]
    return "\n".join(out)
