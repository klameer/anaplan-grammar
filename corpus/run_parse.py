"""Parse every unique formula in the corpus; report parse rate per source
and dump failures grouped by error message for grammar iteration."""
import json, sys, collections, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.parser import parse, ParseError
from anaplan_grammar.lexer import LexError

recs = [json.loads(l) for l in open("corpus/derived/formulas.jsonl", encoding="utf-8")]
by_src = collections.defaultdict(lambda: [0, 0])
fails = collections.defaultdict(list)
seen = set()
ok = tot = 0
for r in recs:
    f = r["formula"]
    if f in seen:
        continue
    seen.add(f)
    tot += 1
    by_src[r["source"]][1] += 1
    try:
        parse(f)
        ok += 1
        by_src[r["source"]][0] += 1
    except (ParseError, LexError) as e:
        msg = str(e).split(" at ")[0]
        fails[msg].append((r["source"], f, getattr(e, "pos", -1)))
    except RecursionError:
        fails["recursion"].append((r["source"], f, -1))

print(f"parsed {ok}/{tot} = {ok/tot:.1%}")
for s, (a, b) in sorted(by_src.items()):
    print(f"  {s:28s} {a:5d}/{b:5d} {a/b:.1%}")
print("\nfailure classes:")
for msg, items in sorted(fails.items(), key=lambda kv: -len(kv[1])):
    print(f"\n[{len(items)}] {msg}")
    for src, f, pos in items[:6]:
        snippet = f[max(0, pos - 60):pos + 60].replace("\n", "⏎")
        print(f"   {src:14s} …{snippet}…")
pathlib.Path("corpus/derived/failures.json").write_text(json.dumps({k: v[:200] for k, v in fails.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
