"""The rest of the model estate beyond line items and modules: lists,
actions and processes, and the UX page inventory. All from Anaplan's
standard exports.

  lists/General Lists.csv   one row per list: hierarchy, top level, parent,
                            properties, subsets, numbered, item count,
                            referenced in applies-to / as format / in formula
  actions/Actions.csv       sections: Processes, Imports, Exports,
                            Other Actions, then one section per process
                            listing its member actions
  UX Pages/*.pdf            one PDF per page; the file name is the page name
"""
from __future__ import annotations
import csv, re
from dataclasses import dataclass, field
from pathlib import Path

csv.field_size_limit(10**8)


@dataclass
class ListDef:
    name: str
    top_level: str = ""
    parent: str = ""
    properties: tuple[str, ...] = ()
    subsets: tuple[str, ...] = ()
    numbered: bool = False
    item_count: int = 0
    production_data: bool = False
    selective_access: bool = False
    notes: str = ""
    in_applies_to: tuple[str, ...] = ()
    as_format: tuple[str, ...] = ()
    in_formula: tuple[str, ...] = ()
    is_header: bool = False


@dataclass
class Action:
    name: str
    kind: str                 # import | export | delete | process | other
    target: str = ""          # module or list imported into / exported from
    detail: str = ""
    last_run: str = ""
    duration_ms: int = 0
    processes: tuple[str, ...] = ()
    notes: str = ""


@dataclass
class Process:
    name: str
    last_run: str = ""
    duration_ms: int = 0
    steps: list[str] = field(default_factory=list)


@dataclass
class Estate:
    lists: dict[str, ListDef] = field(default_factory=dict)
    actions: dict[str, Action] = field(default_factory=dict)
    processes: dict[str, Process] = field(default_factory=dict)
    ux_pages: list[str] = field(default_factory=list)


def _split(s: str) -> tuple[str, ...]:
    s = (s or "").strip()
    if not s:
        return ()
    # comma-separated, names may be quoted and contain commas inside quotes
    out, buf, q = [], [], False
    for ch in s:
        if ch == "'":
            q = not q; buf.append(ch)
        elif ch == "," and not q:
            out.append("".join(buf).strip()); buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf).strip())
    return tuple(x for x in out if x)


def _int(s):
    try:
        return int(str(s).replace(",", ""))
    except Exception:
        return 0


def load_lists(path: str | Path, est: Estate) -> None:
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        first = r.fieldnames[0]
        for row in r:
            name = row.get(first, "")
            hdr = bool(re.match(r"^[-▼▲=\s]", name))
            est.lists[name] = ListDef(
                name=name, top_level=row.get("Top Level", "") or "", parent=row.get("Parent Hierarchy", "") or "",
                properties=_split(row.get("Properties", "")), subsets=_split(row.get("Subsets", "")),
                numbered=(row.get("Numbered", "") == "true"), item_count=_int(row.get("Item Count", "0")),
                production_data=(row.get("Production Data", "") == "true"),
                selective_access=(row.get("Selective Access", "") == "true"),
                notes=row.get("Notes", "") or "",
                in_applies_to=_split(row.get("Referenced in Applies To", "")),
                as_format=_split(row.get("Referenced as Format", "")),
                in_formula=_split(row.get("Referenced in Formula", "")),
                is_header=hdr,
            )


_TARGET = re.compile(r"^(Import into|Export from)\s+'?(.+?)'?$")


def load_actions(path: str | Path, est: Estate) -> None:
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        first = r.fieldnames[0]
        section = None
        for row in r:
            name = row.get(first, "")
            act = row.get("Action", "") or ""
            started = row.get("Start Date and Time (UTC)", "") or ""
            dur = row.get("Most recent duration (ms)", "") or ""
            used = row.get("Used in Processes", "") or ""
            if not act and not started and not dur and not used:
                section = name          # "Processes", "Imports", "Exports", "Other Actions", or a process name
                if section not in ("Processes", "Imports", "Exports", "Other Actions"):
                    est.processes.setdefault(section, Process(name=section))
                continue
            if section == "Processes":
                p = est.processes.setdefault(name, Process(name=name))
                p.last_run, p.duration_ms = started, _int(dur)
                continue
            if section not in ("Imports", "Exports", "Other Actions"):
                # member step of a process section
                est.processes.setdefault(section, Process(name=section)).steps.append(name)
                if name not in est.actions:
                    est.actions[name] = Action(name=name, kind="other", detail=act[:80])
                continue
            m = _TARGET.match(act)
            if m:
                kind = "import" if m.group(1).startswith("Import") else "export"
                target = m.group(2)
            elif '"actionType":"DELETE' in act:
                kind, target = "delete", ""
            else:
                kind, target = ("import" if section == "Imports" else "export" if section == "Exports" else "other"), ""
            est.actions[name] = Action(name=name, kind=kind, target=target, detail=act[:120], last_run=started,
                                       duration_ms=_int(dur), processes=_split(used), notes=row.get("Notes", "") or "")


def load_ux_pages(folder: str | Path, est: Estate) -> None:
    p = Path(folder)
    if p.is_dir():
        est.ux_pages = sorted(f.stem for f in p.glob("*.pdf"))


def load_estate(lists_csv=None, actions_csv=None, ux_dir=None) -> Estate:
    est = Estate()
    if lists_csv: load_lists(lists_csv, est)
    if actions_csv: load_actions(actions_csv, est)
    if ux_dir: load_ux_pages(ux_dir, est)
    return est
