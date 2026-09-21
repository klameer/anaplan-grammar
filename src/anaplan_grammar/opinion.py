"""The architect's opinion: an LLM reads the as-built spec, the findings
and the graph facts, and writes the sections a senior reviewer would
write. Every claim must cite objects the deterministic layers produced.

Rules that keep it honest:
  - The model never sees raw exports; it sees the spec facts, the lint
    findings and graph statistics, all of which name real objects.
  - Output is JSON: a list of observations, each with a `claim`, a list
    of `refs` (module, module.line_item, list, action, finding id) and
    a `kind` (design_decision | risk | option | automation | question).
  - A validator checks every ref against the model. An observation with a
    bad ref is dropped and logged; one with no refs becomes a question.
  - Temperature 0; observations sorted by kind then ref, so two runs on
    the same spec produce a diffable document.
  - Two passes: generate, then critique (the same model, asked to find
    unsupported claims and rewrite or remove them).

Two ways to run:
  opinion.run(spec, lint, model, api_key=...)     Anthropic SDK, bring your own key
  opinion.prompt(spec, lint) -> text              write the prompt for any model or a human
  opinion.ingest(spec, lint, model, json_text)    validate + assemble a response produced elsewhere
"""
from __future__ import annotations
import json, re
from dataclasses import dataclass, field, asdict
from .model import Model
from .lint import LintResult
from .spec import Spec

KINDS = ["design_decision", "risk", "option", "automation", "question"]

SYSTEM = """You are a senior Anaplan solution architect with fifteen years of FP&A and planning-system work, reviewing a model you have never seen from its as-built specification and a rules-based findings list. You write for the model's owner: plain, specific, no flattery, no hedging. You never invent an object. Every claim cites the modules, line items, lists, actions or finding ids it rests on, exactly as named in the material. If the material does not support a claim, you ask a question instead of asserting."""

INSTRUCTIONS = """Produce a JSON array of observations. Each observation:
{"kind": one of design_decision | risk | option | automation | question,
 "title": short noun phrase,
 "claim": two to five sentences, specific, citing objects by their exact names,
 "refs": ["Module", "Module.Line Item", "List", "action:Name", "finding:RULE-ID"] exact names from the material,
 "effort": for options only: "days" | "weeks" | "quarter",
 "priority": 1 (do first) to 5}

Cover:
- design_decision: the five to eight decisions that explain how this model is built (dimensional strategy, how currency and versions are handled, how summaries and reports are produced, how data enters and leaves). Say what each decision costs and buys.
- risk: key-person, calculation, size, change and data risks, each with the evidence.
- option: three levels: hygiene (days, no design change), restructure (weeks, one layer), rebuild (a quarter, what a clean design would keep). Each with what it fixes and what it risks.
- automation: where a deterministic process (regression tests, load tie-outs, release diffs, documentation generation) replaces manual work; where an AI assistant helps (explaining chains, reviewing proposed formulas, drafting notes); where neither should touch it.
- question: what you would ask the builder in the first hour.

Between 18 and 30 observations. Refs must be exact. No markdown inside JSON strings."""


@dataclass
class Observation:
    kind: str
    title: str
    claim: str
    refs: list[str]
    priority: int = 3
    effort: str = ""
    valid_refs: list[str] = field(default_factory=list)
    dropped_refs: list[str] = field(default_factory=list)


@dataclass
class Opinion:
    observations: list[Observation]
    dropped: list[dict]          # observations removed by the validator, with reason
    model_name: str
    provider: str

    def by_kind(self):
        out = {k: [] for k in KINDS}
        for o in self.observations:
            out[o.kind].append(o)
        return out

    def to_dict(self):
        return {"model": self.model_name, "provider": self.provider,
                "observations": [asdict(o) for o in self.observations], "dropped": self.dropped}


# ---------- material ----------

def material(spec: Spec, lint: LintResult, max_findings_per_rule: int = 12) -> str:
    """What the model is shown. The spec markdown plus a compact findings digest."""
    from .cluster import cluster
    parts = [spec.markdown(), "", "# Rule-based findings, grouped by pattern", "",
             f"Counts by rule (raw findings): {json.dumps(lint.counts['by_rule'])}", "",
             "A pattern is one rule firing on a line item copied across modules, or across the line items of one module. "
             "Cite patterns by their rule id (finding:RULE) and name the modules and line items they list.", ""]
    grouped = {}
    for c in cluster(lint.findings):
        grouped.setdefault(c.rule, []).append(c)
    for rid, cs in grouped.items():
        total = sum(c.count for c in cs)
        parts.append(f"## finding:{rid} ({total} findings in {len(cs)} patterns) severity {cs[0].severity}")
        for c in cs[:max_findings_per_rule]:
            ex = c.objects[0] if c.objects else ""
            parts.append(f"- [{c.count}] {c.label}: {c.message[:120]} (e.g. {ex})")
        if len(cs) > max_findings_per_rule:
            parts.append(f"- ... {len(cs) - max_findings_per_rule} more patterns")
        parts.append("")
    return "\n".join(parts)


def prompt(spec: Spec, lint: LintResult) -> str:
    return SYSTEM + "\n\n" + INSTRUCTIONS + "\n\n# Material\n\n" + material(spec, lint)


# ---------- validation ----------

def _ref_index(model: Model, spec: Spec, lint: LintResult) -> dict[str, set[str]]:
    mods = {n for n in model.modules}
    lis = {f"{a}.{b}" for a, b in model.line_items}
    lists = set(spec.estate.lists) if spec.estate else set()
    acts = {f"action:{a}" for a in (spec.estate.actions if spec.estate else {})} | {f"action:{p}" for p in (spec.estate.processes if spec.estate else {})}
    finds = {f"finding:{r}" for r in lint.counts["by_rule"]}
    return {"module": mods, "line_item": lis, "list": lists, "action": acts, "finding": finds}


def validate(obs: list[dict], model: Model, spec: Spec, lint: LintResult) -> tuple[list[Observation], list[dict]]:
    idx = _ref_index(model, spec, lint)
    allrefs = set().union(*idx.values())
    lower = {r.lower(): r for r in allrefs}
    kept, dropped = [], []
    for o in obs:
        kind = o.get("kind", "question")
        if kind not in KINDS:
            kind = "question"
        refs = [str(r).strip() for r in o.get("refs", []) if str(r).strip()]
        ok, bad = [], []
        for r in refs:
            if r in allrefs:
                ok.append(r)
            elif r.lower() in lower:
                ok.append(lower[r.lower()])
            else:
                bad.append(r)
        title = str(o.get("title", ""))[:120]
        claim = str(o.get("claim", "")).strip()
        if not claim:
            continue
        if bad and not ok:
            dropped.append({"title": title, "reason": "no valid refs", "bad_refs": bad, "claim": claim[:200]})
            continue
        if bad:
            # keep, but only with the refs that exist; a claim resting partly on invented objects is downgraded to a question
            kind = "question" if len(bad) > len(ok) else kind
        if not ok and kind != "question":
            kind = "question"
        kept.append(Observation(kind=kind, title=title, claim=claim, refs=refs,
                                priority=int(o.get("priority", 3) or 3), effort=str(o.get("effort", "") or ""),
                                valid_refs=ok, dropped_refs=bad))
    kept.sort(key=lambda x: (KINDS.index(x.kind), x.priority, x.title))
    return kept, dropped


def _extract_json(text: str):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("no JSON array in response")
    return json.loads(m.group(0))


def ingest(spec: Spec, lint: LintResult, model: Model, json_text: str, provider: str = "ingested") -> Opinion:
    obs = _extract_json(json_text)
    kept, dropped = validate(obs, model, spec, lint)
    return Opinion(kept, dropped, model.name, provider)


# ---------- Anthropic path ----------

CRITIQUE = """Below are observations about an Anaplan model, and the material they were written from. For each observation, check that every sentence is supported by the material and that every ref is an exact name from it. Rewrite any unsupported sentence to what the material does support, or remove it. Remove any ref that is not an exact name. Return the corrected JSON array only."""


def run(spec: Spec, lint: LintResult, model: Model, api_key: str, model_id: str = "claude-sonnet-5", critique: bool = True) -> Opinion:
    try:
        import anthropic
    except ImportError as e:
        raise SystemExit("pip install anthropic, or use `opinion prompt` and `opinion ingest`") from e
    client = anthropic.Anthropic(api_key=api_key)
    mat = material(spec, lint)
    first = client.messages.create(model=model_id, max_tokens=8000, temperature=0, system=SYSTEM,
                                   messages=[{"role": "user", "content": INSTRUCTIONS + "\n\n# Material\n\n" + mat}])
    text = "".join(b.text for b in first.content if getattr(b, "type", "") == "text")
    if critique:
        second = client.messages.create(model=model_id, max_tokens=8000, temperature=0, system=SYSTEM,
                                        messages=[{"role": "user", "content": CRITIQUE + "\n\n# Observations\n\n" + text + "\n\n# Material\n\n" + mat}])
        text = "".join(b.text for b in second.content if getattr(b, "type", "") == "text")
    return ingest(spec, lint, model, text, provider=f"anthropic:{model_id}")


# ---------- rendering ----------

TITLES = {"design_decision": "How the model is built: the decisions and what they cost",
          "risk": "Risk register", "option": "Options", "automation": "What to automate, and what not to",
          "question": "Questions for the builder"}


def render_markdown(op: Opinion) -> str:
    out = [f"# Architect's opinion: {op.model_name}", "",
           f"Written by {op.provider} from the as-built specification and the rule-based findings. "
           f"Every claim cites objects the deterministic layers produced; {len(op.dropped)} claim(s) were removed because they named objects that do not exist.", ""]
    for kind, obs in op.by_kind().items():
        if not obs:
            continue
        out += [f"## {TITLES[kind]}", ""]
        for o in obs:
            hdr = f"**{o.title}**"
            if o.kind == "option" and o.effort:
                hdr += f" ({o.effort})"
            if o.kind in ("risk", "option"):
                hdr += f" · priority {o.priority}"
            out.append(hdr)
            out.append("")
            out.append(o.claim)
            out.append("")
            out.append("Evidence: " + ", ".join(f"`{r}`" for r in o.valid_refs))
            if o.dropped_refs:
                out.append(f"(refs not found and removed: {', '.join(o.dropped_refs)})")
            out.append("")
    if op.dropped:
        out += ["## Removed by the validator", ""]
        for d in op.dropped:
            out.append(f"- {d['title']}: {d['reason']} ({', '.join(d['bad_refs'])})")
    return "\n".join(out)
