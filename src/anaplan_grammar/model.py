"""Load an Anaplan model's structure from the standard exports.

Inputs (both from Anaplan's grid exports, CSV):
  line_items.csv  Modules > Line Items grid: Format, Formula, Summary,
                  Applies To, Time Scale, Time Range, Versions, ...,
                  Referenced By, Module Name
  modules.csv     Modules grid: Functional Area, Applies To, ..., Line Items

Only the columns needed for structure are read. Cell counts and access
drivers are kept as strings on the line item for later reports.
"""
from __future__ import annotations
import csv, json
from dataclasses import dataclass, field
from pathlib import Path

csv.field_size_limit(10**8)


@dataclass
class LineItem:
    module: str
    name: str
    formula: str = ""
    format_type: str = ""
    applies_to: tuple[str, ...] = ()
    time_scale: str = ""
    versions: str = ""
    summary: str = ""
    cell_count: int = 0
    referenced_by_raw: str = ""
    notes: str = ""
    is_header: bool = False   # "▼▼▼ SECTION ▼▼▼" style rows and other no-format rows

    @property
    def key(self) -> tuple[str, str]:
        return (self.module, self.name)

    def __str__(self):
        return f"{self.module}.{self.name}"


@dataclass
class Module:
    name: str
    functional_area: str = ""
    applies_to: tuple[str, ...] = ()
    time_scale: str = ""
    versions: str = ""
    cell_count: int = 0
    line_items: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class Model:
    name: str = ""
    modules: dict[str, Module] = field(default_factory=dict)
    line_items: dict[tuple[str, str], LineItem] = field(default_factory=dict)
    # dimension names seen in Applies To (lists, subsets, pseudo-lists)
    dimensions: set[str] = field(default_factory=set)

    def by_module(self, module: str) -> list[LineItem]:
        return [li for li in self.line_items.values() if li.module == module]

    def line_item_names(self) -> dict[str, list[LineItem]]:
        """name -> all line items with that name, across modules."""
        out: dict[str, list[LineItem]] = {}
        for li in self.line_items.values():
            out.setdefault(li.name, []).append(li)
        return out


def _split_applies(s: str) -> tuple[str, ...]:
    s = (s or "").strip()
    if not s or s == "-":
        return ()
    # Applies To is a comma-separated list of dimension names; names may be quoted
    parts = []
    for p in s.split(","):
        p = p.strip().strip("'")
        if p:
            parts.append(p)
    return tuple(parts)


def _fmt(s: str) -> str:
    if not s:
        return ""
    try:
        return json.loads(s).get("dataType", "")
    except Exception:
        return s[:20]


def _int(s: str) -> int:
    try:
        return int(str(s).replace(",", ""))
    except Exception:
        return 0


def load_line_items(path: str | Path, model: Model) -> None:
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        first = r.fieldnames[0]
        current_module = None
        for row in r:
            name = row.get(first, "")
            mod_col = row.get("Module Name", "")
            formula = (row.get("Formula") or "").strip()
            fmt = row.get("Format", "")
            if not fmt and not formula and not mod_col:
                # module header row (the module's own name in column 0)
                current_module = name
                model.modules.setdefault(name, Module(name=name))
                continue
            module = mod_col or current_module or ""
            model.modules.setdefault(module, Module(name=module))
            li = LineItem(
                module=module, name=name, formula=formula, format_type=_fmt(fmt),
                applies_to=_split_applies(row.get("Applies To", "")),
                time_scale=row.get("Time Scale", ""), versions=row.get("Versions", ""),
                summary=(row.get("Summary") or "")[:80], cell_count=_int(row.get("Cell Count", "0")),
                referenced_by_raw=row.get("Referenced By", "") or "", notes=row.get("Notes", "") or "",
                is_header=(not fmt and not formula),
            )
            model.line_items[li.key] = li
            model.modules[module].line_items.append(name)
            model.dimensions.update(li.applies_to)


def load_modules(path: str | Path, model: Model) -> None:
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        first = r.fieldnames[0]
        for row in r:
            name = row.get(first, "")
            m = model.modules.setdefault(name, Module(name=name))
            m.functional_area = row.get("Functional Area", "") or ""
            m.applies_to = _split_applies(row.get("Applies To", ""))
            m.time_scale = row.get("Time Scale", "") or ""
            m.versions = row.get("Versions", "") or ""
            m.cell_count = _int(row.get("Cell Count", "0"))
            m.notes = row.get("Notes", "") or ""
            model.dimensions.update(m.applies_to)


def load_model(line_items_csv: str | Path, modules_csv: str | Path | None = None, name: str = "") -> Model:
    model = Model(name=name)
    load_line_items(line_items_csv, model)
    if modules_csv:
        load_modules(modules_csv, model)
    return model
