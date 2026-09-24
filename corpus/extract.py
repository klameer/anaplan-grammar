"""Extract formulas from Anaplan line-item exports into corpus/derived/formulas.jsonl.
Each record: {source, module, line_item, formula, format_type, applies_to, time_scale, versions}.
Formulas are the only sensitive content kept; cell counts/notes/access columns are dropped.
"""
import csv, json, sys, pathlib, hashlib
csv.field_size_limit(10**8)
ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "derived" / "formulas.jsonl"

def fmt_type(s):
    if not s: return ""
    try: return json.loads(s).get("dataType","")
    except Exception: return s[:20]

def extract(path, label):
    n=0
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        first = r.fieldnames[0]
        module = None
        for row in r:
            name = row.get(first,"")
            mod_col = row.get("Module Name","")
            formula = (row.get("Formula") or "").strip()
            # module header rows carry the module name in the first column and blank Format
            if not row.get("Format") and not formula:
                module = name; continue
            if mod_col: module = mod_col
            if not formula: continue
            yield {"source": label, "module": module, "line_item": name, "formula": formula,
                   "format_type": fmt_type(row.get("Format","")), "applies_to": row.get("Applies To",""),
                   "time_scale": row.get("Time Scale",""), "versions": row.get("Versions",""),
                   "summary": row.get("Summary","")[:80]}
            n+=1

def main(sources):
    OUT.parent.mkdir(exist_ok=True)
    total=0; seen=set()
    with open(OUT,"w",encoding="utf-8") as out:
        for label, path in sources:
            c=0
            for rec in extract(path, label):
                key=hashlib.sha1(rec["formula"].encode()).hexdigest()
                rec["dup"] = key in seen; seen.add(key)
                out.write(json.dumps(rec, ensure_ascii=False)+"\n"); c+=1
            print(f"{label:30s} {c:6d} formulas")
            total+=c
    print(f"{'TOTAL':30s} {total:6d}  unique={len(seen)}")

if __name__=="__main__":
    # Sources are private and machine-specific, so they live outside the repo:
    #   corpus/sources.local.json  -> {"sources": [["label", "path/to/Line Items.csv"], ...]}   (gitignored)
    # or on the command line:  python corpus/extract.py label=path/to/file.csv ...
    sources = []
    local = ROOT / "sources.local.json"
    if local.exists():
        cfg = json.loads(local.read_text(encoding="utf-8"))
        sources += [(l, pathlib.Path(pth)) for l, pth in (cfg.get("sources", []) if isinstance(cfg, dict) else cfg)]
    for arg in sys.argv[1:]:
        label, _, pth = arg.partition("=")
        if label and pth:
            sources.append((label, pathlib.Path(pth)))
    if not sources:
        sys.exit("no sources: create corpus/sources.local.json or pass label=path arguments")
    main([(l, pth) for l, pth in sources if pth.exists()])
