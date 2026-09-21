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
    D = pathlib.Path.home()/"Downloads"
    G = pathlib.Path(r"G:\My Drive\PARA\4_Archive\20250602_EXS Anaplan Winddown")
    sources = [
        ("dl-lineitems-2025-01", D/"Line Items.csv"),
        ("dl-lineitems-1-2025-10", D/"Line Items (1).csv"),
        ("dl-lineitems-14-2025-12", D/"Line Items (14).csv"),
        ("dl-fy25", D/"Line Items FY25 csv Format.csv"),
        ("dl-fy26", D/"Line Items - FY26 csv Format.csv"),
        ("exs-1-fpa", G/"1 FPA Model"/"line items"/"Line Items.csv"),
        ("exs-2-hr", G/"2 HR Model Documentation"/"line items"/"Line Items.csv"),
        ("exs-3-dept", G/"3 Department Model Documentation"/"line items"/"Line Items.csv"),
        ("exs-4-exec", G/"4 Exec Model Documentation"/"line items"/"Line Items.csv"),
        ("exs-5-clinical", G/"5 Clinical Studies PoC Documentation"/"line items"/"Line Items.csv"),
        ("exs-6-pipeline", G/"6 Pipeline Project Planning"/"line items"/"Line Items.csv"),
    ]
    main([(l,p) for l,p in sources if p.exists()])
