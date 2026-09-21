"""The architect's review: one document from the as-built specification,
the health report and the opinion. The spec and health are deterministic;
the opinion is written by a model (or a person) and validated against the
spec. The cover says which is which.
"""
from __future__ import annotations
import datetime
from .spec import Spec
from .health import HealthReport, render_markdown as render_health
from .opinion import Opinion, render_markdown as render_opinion


def render_review(spec: Spec, health: HealthReport, opinion: Opinion | None, signed_by: str = "") -> str:
    m = spec.model
    st = health.stats
    out = [f"# Architect's review: {m.name}", "",
           f"Generated {datetime.date.today().isoformat()} from the model's standard exports "
           f"(line items, modules, lists, actions, UX page names). "
           + ("Signed: " + signed_by + "." if signed_by else "Unsigned: no interviews, no materiality agreed, no check against design documents, no letter. A signed review adds those."), "",
           "## How to read this", "",
           "Three parts. **The as-built specification** describes how the model is constructed; every statement in it is computed from the exports. "
           "**The health report** scores the model against Anaplan's published rules and the dependency graph; every finding names the object. "
           "**The opinion** is written by a reviewer from the first two parts; every claim cites the modules, line items, lists, actions and finding ids it rests on, "
           "and a validator removed any claim that named an object the model does not contain. "
           "What the exports do not show, and therefore what no part of this review can say, is listed at the end of the specification.", "",
           "## The model in one paragraph", "",
           f"{st['modules']} modules and {st['line_items']:,} line items ({st['with_formula']:,} calculated), {st['dimensions']} dimensions, "
           f"{st['edges']:,} formula references between line items and {st['module_edges']:,} between modules, "
           f"{len(spec.facts.get('imports', {}))} imports, {len(spec.facts.get('exports', {}))} exports, {len(spec.facts.get('processes', {}))} processes, "
           f"{len(spec.facts.get('ux_pages', []))} UX pages. Health {health.overall} of 100: "
           + ", ".join(f"{s.category} {s.score}" for s in health.scores) + ".", ""]
    if opinion:
        by = opinion.by_kind()
        top = by["design_decision"][:3] + by["risk"][:2]
        if top:
            out += ["## What the reviewer would say first", ""]
            for o in top:
                out.append(f"- **{o.title}.** {o.claim.split('. ')[0]}.")
            out.append("")
    out += ["---", "", render_opinion(opinion) if opinion else "_No opinion generated._", "", "---", "",
            render_health(health), "", "---", "", spec.markdown()]
    return "\n".join(out)
