"""Diff layer: mutate the Caldergate fixture in memory and check the change set."""
import sys, pathlib, copy
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.model import load_model, LineItem
from anaplan_grammar.diff import diff_models, render_markdown

FX = pathlib.Path(__file__).parent / "fixtures"


def base():
    return load_model(FX / "caldergate_line_items.csv", FX / "caldergate_modules.csv", name="v1")


def test_identical_models_have_no_changes():
    a, b = base(), base()
    d = diff_models(a, b)
    assert d.line_items == [] and d.modules == []


def test_whitespace_and_quoting_are_not_changes():
    a, b = base(), base()
    li = b.line_items[("CAL02 Revenue", "Net Revenue")]
    li.formula = "'Gross Revenue'   -   Discounts"          # same tree as: Gross Revenue - Discounts
    assert diff_models(a, b).line_items == []


def test_formula_change_carries_blast_radius():
    a, b = base(), base()
    b.line_items[("INP01 Volumes", "Price")].formula = "10"   # an input became a formula
    d = diff_models(a, b)
    ch = [c for c in d.line_items if c.name == "Price"][0]
    assert ch.kind == "changed" and ch.fields[0].field == "formula"
    assert ch.impact_count >= 8 and ch.impact_modules >= 3   # Gross Revenue -> ... -> Board Pack


def test_add_remove_rename():
    a, b = base(), base()
    # rename Bonus -> Bonus Accrual (same formula), remove Unused Helper, add a new line item
    old = b.line_items.pop(("CAL03 Opex", "Bonus"))
    b.line_items[("CAL03 Opex", "Bonus Accrual")] = LineItem(module="CAL03 Opex", name="Bonus Accrual", formula=old.formula, format_type=old.format_type, applies_to=old.applies_to)
    b.line_items[("CAL03 Opex", "Total Opex")].formula = "Salaries + Bonus Accrual"
    b.line_items.pop(("CAL03 Opex", "Unused Helper"))
    b.line_items[("CAL03 Opex", "Travel")] = LineItem(module="CAL03 Opex", name="Travel", formula="Salaries * 0.05", format_type="NUMBER", applies_to=("Departments",))
    d = diff_models(a, b)
    kinds = {(c.name, c.kind) for c in d.line_items}
    assert ("Bonus Accrual", "renamed") in kinds
    assert ("Unused Helper", "removed") in kinds
    assert ("Travel", "added") in kinds
    assert ("Total Opex", "changed") in kinds
    ren = [c for c in d.line_items if c.kind == "renamed"][0]
    assert ren.renamed_from == "Bonus"
    s = d.summary
    assert s["line_items_renamed"] == 1 and s["line_items_added"] == 1 and s["line_items_removed"] == 1


def test_module_added_and_removed():
    a, b = base(), base()
    for k in [k for k in b.line_items if k[0] == "CAL04 Margin"]:
        b.line_items.pop(k)
    b.modules.pop("CAL04 Margin")
    d = diff_models(a, b)
    assert any(m.name == "CAL04 Margin" and m.kind == "removed" and m.line_items_removed == 6 for m in d.modules)
    md = render_markdown(d)
    assert "CAL04 Margin" in md and "removed" in md


def test_sorted_by_impact():
    a, b = base(), base()
    b.line_items[("INP01 Volumes", "Price")].formula = "10"
    b.line_items[("OUT01 Board Pack", "Margin")].formula = "'CAL04 Margin'.Margin * 1"
    d = diff_models(a, b)
    assert d.line_items[0].name == "Price"   # larger blast radius first
