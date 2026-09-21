"""Correctness checks that go beyond "it parsed".

1. Round trip: unparse(parse(f)) must re-parse to an identical AST.
   Catches silent misparses where the tree is well-formed but wrong.
2. Reference recall: every quoted name in the source formula must appear
   as (part of) a reference path in the AST. A quoted name that vanishes
   means the tokenizer swallowed it into a neighbour.
3. Keyword sanity: no reference path may equal a bare keyword.
4. Function catalogue: every call node's name must be in the catalogue;
   report unknown names (these are grammar gaps or Anapedia gaps).
5. Distribution: counts of node kinds, so the grammar's coverage is visible.
"""
import json, sys, re, collections, pathlib
sys.setrecursionlimit(20000)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.parser import parse, references
from anaplan_grammar.unparse import unparse
from anaplan_grammar.functions import FUNCTIONS, KEYWORDS

recs = [json.loads(l) for l in open("corpus/derived/formulas.jsonl", encoding="utf-8")]
F = list({r["formula"]: 1 for r in recs})
rt_fail, ref_fail, kw_fail = [], [], []
unknown = collections.Counter()
kinds = collections.Counter()

def walk(n):
    if isinstance(n, dict):
        if "t" in n: kinds[n["t"]] += 1
        if n.get("t") == "call" and n["f"] not in FUNCTIONS:
            unknown[n["f"]] += 1
        for v in n.values(): walk(v)
    elif isinstance(n, list):
        for v in n: walk(v)

for f in F:
    ast = parse(f)
    walk(ast)
    # 1 round trip
    try:
        s2 = unparse(ast)
        if parse(s2) != ast:
            rt_fail.append((f, s2))
    except Exception as e:
        rt_fail.append((f, f"UNPARSE ERROR {e}"))
    # 2 reference recall
    paths = references(ast)
    flat = "|".join(".".join(p) for p in paths)
    for q in re.findall(r"'((?:[^']|'')*)'", f):
        q = q.replace("''", "'")
        if q not in flat:
            ref_fail.append((f, q)); break
    # 3 keyword sanity: a bare (unquoted) keyword must never become a name.
    # A quoted 'TRUE' is a legal line-item name, so only flag when the source
    # does not contain the quoted form.
    for p in paths:
        for seg in p:
            if seg.upper() in KEYWORDS and ("'" + seg + "'") not in f:
                kw_fail.append((f, p)); break

print(f"formulas {len(F)}")
print(f"round-trip failures: {len(rt_fail)}")
for f, s2 in rt_fail[:8]: print("   ", f[:100], "\n   ->", str(s2)[:100])
print(f"reference-recall failures: {len(ref_fail)}")
for f, q in ref_fail[:8]: print("   ", q, "|", f[:100])
print(f"keyword-in-path failures: {len(kw_fail)}")
for f, p in kw_fail[:8]: print("   ", p, "|", f[:100])
print("unknown function names:", unknown.most_common(20))
print("node kinds:", dict(kinds))
