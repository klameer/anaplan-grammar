"""Score the graph against Anaplan's own 'Referenced By' column.

For each line item, Anaplan lists who references it: bare names (same
module) and Module.Name pairs. That is the reverse-edge set the export
already knows. Our graph's rev[key] should match it for line-item refs.
Module-only entries in Referenced By (a module name with no line item)
mean 'used as a dimension/driver by that module' and are not formula
edges; they are skipped.
"""
import sys, pathlib, re, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.model import load_model
from anaplan_grammar.graph import build_graph

# Models to score are private and machine-specific, so they live outside the repo:
#   corpus/sources.local.json with a "pairs" key -> {"pairs": [["label", "Line Items.csv", "Modules.csv"], ...]}
# or on the command line:  python corpus/verify_graph.py label=line_items.csv,modules.csv ...
import json as _json
PAIRS = []
_local = pathlib.Path(__file__).resolve().parent / "sources.local.json"
if _local.exists():
    _cfg = _json.loads(_local.read_text(encoding="utf-8"))
    PAIRS += [(l, pathlib.Path(li), pathlib.Path(mo)) for l, li, mo in (_cfg.get("pairs", []) if isinstance(_cfg, dict) else [])]
for _arg in sys.argv[1:]:
    _label, _, _rest = _arg.partition("=")
    if _label and "," in _rest:
        _li, _mo = _rest.split(",", 1)
        PAIRS.append((_label, pathlib.Path(_li), pathlib.Path(_mo)))

_NAME = r"(?:'(?:[^']|'')*'|[^,']+)"
_ENTRY = re.compile(rf"\s*({_NAME})(?:\.({_NAME}))?\s*(?:,|$)")


def parse_referenced_by(s: str, own_module: str):
    """Yield (module, name) for line-item entries; skip module-only entries."""
    out = set()
    s = (s or "").strip()
    if not s:
        return out
    # split on commas not inside quotes
    parts, buf, q = [], [], False
    for ch in s:
        if ch == "'":
            q = not q
        if ch == "," and not q:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    for p in parts:
        p = p.strip()
        if not p or p == "⠀":
            continue
        # Module.Name or Name; names may be quoted
        segs, cur, q = [], [], False
        for ch in p:
            if ch == "'":
                q = not q; continue
            if ch == "." and not q:
                segs.append("".join(cur)); cur = []
            else:
                cur.append(ch)
        segs.append("".join(cur))
        segs = [x.strip() for x in segs]
        if len(segs) == 1:
            out.add(("?", segs[0]))          # bare: same module OR a module-only entry; decided by caller
        else:
            out.add((segs[0], ".".join(segs[1:])))
    return out


for label, li_csv, mod_csv in PAIRS:
    if not li_csv.exists():
        print(label, "missing"); continue
    model = load_model(li_csv, mod_csv, name=label)
    g = build_graph(model)
    st = g.stats()
    print(f"\n=== {label}: {st}")
    tp = fp = fn = 0
    fn_examples, fp_examples = [], []
    for key, li in model.line_items.items():
        truth_raw = parse_referenced_by(li.referenced_by_raw, li.module)
        truth = set()
        for m, n in truth_raw:
            if m == "?":
                if (li.module, n) in model.line_items:
                    truth.add((li.module, n))
                elif n in model.modules:
                    continue   # module-only entry: dimension usage, not a formula edge
                else:
                    continue   # unknown (view/export name)
            else:
                if (m, n) in model.line_items:
                    truth.add((m, n))
                # else: a list property or a module.item we don't have; skip
        ours = set(g.rev.get(key, set()))
        tp += len(truth & ours); fp += len(ours - truth); fn += len(truth - ours)
        for x in list(truth - ours)[:1]:
            if len(fn_examples) < 8: fn_examples.append((key, x, model.line_items[x].formula[:120]))
        for x in list(ours - truth)[:1]:
            if len(fp_examples) < 8: fp_examples.append((key, x, model.line_items[x].formula[:120]))
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    print(f"edges vs Referenced By: tp={tp} fp={fp} fn={fn}  precision={prec:.3f} recall={rec:.3f}")
    print("missed (in Anaplan's list, not in ours):")
    for k, x, f in fn_examples: print(f"   {k[0]}.{k[1]}  <-  {x[0]}.{x[1]}   formula: {f}")
    print("extra (in ours, not in Anaplan's list):")
    for k, x, f in fp_examples: print(f"   {k[0]}.{k[1]}  <-  {x[0]}.{x[1]}   formula: {f}")
    # queries
    hubs = g.hubs(5)
    print("top hubs:", [(f"{k[0]}.{k[1]}", n) for k, n in hubs])
    cyc = g.cycles(); print("cycles:", len(cyc), [ [f'{a}.{b}' for a,b in c][:4] for c in cyc[:3]])
    dc = g.daisy_chains(); print("daisy chains >=3:", len(dc), [[f'{a}.{b}' for a,b in c] for c in dc[:2]])
    un = g.unused(); print("unreferenced line items:", len(un), "of", len(model.line_items))
    if hubs:
        k = hubs[0][0]; imp = g.impact(k)
        print(f"impact of {k[0]}.{k[1]}: {len(imp)} line items across {len({m for m,_ in imp})} modules, max depth {max(imp.values()) if imp else 0}")
    unres = collections.Counter(".".join(r.path) for rs in g.refs.values() for r in rs if r.kind == "unresolved")
    print("unresolved refs (top 10):", unres.most_common(10))
