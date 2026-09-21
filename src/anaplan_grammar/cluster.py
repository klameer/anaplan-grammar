"""Group repeated findings into the design decision behind them.

A model that converts currency the same way in 96 month columns has one
finding, not 96. Two cluster keys, applied in order:

  0. family     several templates copied across the SAME module set (merged after 1)
  1. template   same rule, same line-item NAME, across several modules
                (a formula copied module to module, e.g. "Cost per Month
                (base currency)" divided without a guard in nine collect
                modules)
  2. module     same rule, same module, same message shape (the message
                with numbers and object names blanked), e.g. every month
                column of one summary module mixing LOOKUP and SELECT

A cluster of one is just the finding. Cluster weight for scoring is
severity × (1 + log10(n)), so 96 repeats of one decision count about 3×
one finding, not 96×.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import math, re
from .lint import Finding, SEV_ORDER

_NUM = re.compile(r"\d[\d,\.]*")
_QUOTED = re.compile(r"'[^']*'")


def shape(message: str) -> str:
    """Message with numbers and quoted names blanked, so repeats match."""
    s = _QUOTED.sub("'X'", message)
    s = _NUM.sub("N", s)
    # object names after 'ending at', 'cycle of', 'in a module on' vary per finding; cut at the first colon
    return s.split(":")[0][:80]


@dataclass
class Cluster:
    rule: str
    severity: str
    key: str                      # "family" | "template" | "module" | "single"
    label: str                    # what the cluster is
    count: int
    modules: list[str]
    objects: list[str]            # up to 8 sample objects
    message: str                  # representative message
    fix: str
    weight: float                 # for scoring
    findings: list[Finding] = field(default_factory=list)

    @property
    def object(self) -> str:      # for tables that expect one object
        return self.label

    def to_dict(self):
        d = asdict(self); d.pop("findings"); return d


def cluster(findings: list[Finding], min_size: int = 3) -> list[Cluster]:
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_rule[f.rule].append(f)
    out: list[Cluster] = []
    for rule, fs in by_rule.items():
        remaining = list(fs)
        # 1 template clusters: same line-item name in >= min_size modules
        by_name: dict[str, list[Finding]] = defaultdict(list)
        for f in remaining:
            if f.line_item:
                by_name[f.line_item].append(f)
        taken = set()
        for name, group in by_name.items():
            mods = {f.module for f in group}
            if len(group) >= min_size and len(mods) >= min_size:
                out.append(_mk(rule, group, "template", f"{name} (in {len(mods)} modules)"))
                taken.update(id(f) for f in group)
        remaining = [f for f in remaining if id(f) not in taken]
        # 2 module clusters: same module + message shape
        by_mod: dict[tuple[str, str], list[Finding]] = defaultdict(list)
        for f in remaining:
            by_mod[(f.module, shape(f.message))].append(f)
        for (mod, sh), group in by_mod.items():
            if len(group) >= min_size:
                out.append(_mk(rule, group, "module", f"{mod} ({len(group)} line items)"))
            else:
                for f in group:
                    out.append(_mk(rule, [f], "single", f.object))
    out = _merge_families(out)
    out.sort(key=lambda c: (SEV_ORDER[c.severity], -c.weight, c.rule, c.label))
    return out


def _merge_families(clusters: list[Cluster]) -> list[Cluster]:
    """Template clusters with the same rule, the same module set and the same
    message shape are one family: fifteen line items copied across the same
    five modules is one decision, not fifteen."""
    fam: dict[tuple, list[Cluster]] = defaultdict(list)
    rest = []
    for c in clusters:
        if c.key == "template":
            fam[(c.rule, tuple(c.modules), shape(c.message))].append(c)
        else:
            rest.append(c)
    for (rule, mods, _), group in fam.items():
        if len(group) == 1:
            rest.append(group[0]); continue
        fs = [f for c in group for f in c.findings]
        names = [c.label.split(" (in ")[0] for c in group]
        label = f"{len(names)} line items × {len(mods)} modules ({', '.join(mods[:3])}{' ...' if len(mods) > 3 else ''})"
        m = _mk(rule, fs, "family", label)
        m.objects = [f"{mods[0]}.{n}" for n in names[:8]]
        rest.append(m)
    return rest


def _mk(rule: str, group: list[Finding], key: str, label: str) -> Cluster:
    f0 = group[0]
    mods = sorted({f.module for f in group})
    from .lint import RULES
    sev = f0.severity
    from .health import SEV_WEIGHT
    w = SEV_WEIGHT[sev] * (1 + math.log10(len(group)))
    return Cluster(rule=rule, severity=sev, key=key, label=label, count=len(group), modules=mods,
                   objects=[f.object for f in group[:8]], message=f0.message, fix=f0.fix, weight=round(w, 2), findings=group)


def render_markdown(clusters: list[Cluster], max_rows: int = 40) -> str:
    out = ["| Severity | Rule | Pattern | Count | Example | Fix |", "|---|---|---|---|---|---|"]
    for c in clusters[:max_rows]:
        out.append(f"| {c.severity} | {c.rule} | {c.label} | {c.count} | {c.objects[0] if c.objects else ''}: {c.message[:70]} | {c.fix[:70]} |")
    if len(clusters) > max_rows:
        out.append(f"| | | ... {len(clusters) - max_rows} more patterns | | | |")
    return "\n".join(out)
