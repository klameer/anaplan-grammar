import json, re, collections, pathlib
recs=[json.loads(l) for l in open("corpus/derived/formulas.jsonl",encoding="utf-8")]
uniq={}
for r in recs: uniq.setdefault(r["formula"], r)
F=list(uniq)
print("unique formulas:",len(F))
# length distribution
L=sorted(len(f) for f in F); print("len p50/p90/p99/max:",L[len(L)//2],L[int(len(L)*.9)],L[int(len(L)*.99)],L[-1])
# functions used: NAME( pattern, excluding IF(
fn=collections.Counter()
for f in F:
    for m in re.finditer(r"\b([A-Z][A-Z0-9_]+)\s*\(", f): fn[m.group(1)]+=1
print("\nfunctions (top 60):"); print(fn.most_common(60))
# bracket forms
br=collections.Counter()
for f in F:
    for m in re.finditer(r"\[([^\]]*)\]", f):
        inner=m.group(1)
        kinds=tuple(sorted(set(re.findall(r"\b(SELECT|LOOKUP|SUM|AVERAGE|MIN|MAX|ANY|ALL|FIRSTNONBLANK|LASTNONBLANK|TEXTLIST|COUNT|STDEVS|STDEVP|VARS|VARP)\s*:", inner))))
        br[kinds]+=1
print("\nbracket clause kinds:"); print(br.most_common(30))
# keywords
kw=collections.Counter()
for f in F:
    for k in ["IF","THEN","ELSE","AND","OR","NOT","TRUE","FALSE","BLANK","TIME.","VERSIONS.","VERSION.","USERS.","ITEM(","PARENT(","CODE(","NAME(","COLLECT()","CURRENTVERSION","'Current Period'","Current Period","&","<>","<=",">=","\n",'"']:
        if k in f: kw[k]+=1
print("\nkeyword presence:"); print(kw.most_common())
# quoted names with odd chars
odd=collections.Counter()
for f in F:
    for m in re.finditer(r"'([^']*)'", f):
        s=m.group(1)
        for ch in set(s):
            if not (ch.isalnum() or ch in " _-"): odd[ch]+=1
print("\nchars inside quoted names:"); print(odd.most_common(40))
# unquoted identifier shapes: sequences before a dot
dots=collections.Counter()
for f in F:
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_ ]*?)\.([A-Za-z_'][^\s\[\]\(\),+\-*/=<>&]*)", f):
        dots["unquoted.x"]+=1
print("unquoted dotted refs:",dots)
# samples by feature
def show(title, pred, n=6):
    print(f"\n--- {title}")
    c=0
    for f in F:
        if pred(f): print("  ", f[:220].replace("\n","⏎")); c+=1
        if c>=n: break
show("SELECT", lambda f:"SELECT:" in f)
show("LOOKUP", lambda f:"LOOKUP:" in f)
show("SUM", lambda f:"SUM:" in f)
show("multi-clause", lambda f: f.count(":")>=2 and "[" in f)
show("TIME.", lambda f:"TIME." in f.upper())
show("VERSIONS", lambda f:"VERSION" in f.upper())
show("nested IF", lambda f: f.count("IF ")>=3)
show("text concat &", lambda f:"&" in f)
show("newlines", lambda f:"\n" in f)
show("number literals w/ decimals or negatives", lambda f: re.search(r"(?<![A-Za-z0-9_'])-?\d+\.\d+", f) is not None)
show("longest", lambda f: len(f)>1500, 2)
show("contains ITEM(", lambda f:"ITEM(" in f)
show("double-quoted strings", lambda f:'"' in f)
show("percent or currency chars", lambda f: any(c in f for c in "%$£€"))
