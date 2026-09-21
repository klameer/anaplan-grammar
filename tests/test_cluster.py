import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.lint import Finding
from anaplan_grammar.cluster import cluster, shape


def f(rule, mod, li, msg="unguarded / by a line item", sev="major"):
    return Finding(rule, sev, mod, li, msg, "fix", "FORMULA")


def test_template_cluster_same_name_across_modules():
    fs = [f("F-DIVIDE", f"C M{i}", "Cost per Month") for i in range(9)] + [f("F-DIVIDE", "C X", "Other")]
    cs = cluster(fs)
    t = [c for c in cs if c.key == "template"]
    assert len(t) == 1 and t[0].count == 9 and "Cost per Month" in t[0].label and len(t[0].modules) == 9
    assert any(c.key == "single" and c.label == "C X.Other" for c in cs)


def test_module_cluster_same_shape():
    fs = [f("F-MIXED-CLAUSE", "C SUM", f"Apr {y}", "[LOOKUP + SELECT] in one bracket") for y in range(21, 26)]
    fs += [f("F-MIXED-CLAUSE", "C SUM", "Total", "[LOOKUP + SUM] in one bracket")]
    cs = cluster(fs)
    m = [c for c in cs if c.key == "module"]
    assert len(m) == 1 and m[0].count == 5 and m[0].label.startswith("C SUM (5 line items)")


def test_weight_is_log_not_linear():
    one = cluster([f("F-DIVIDE", "A", "x")])[0].weight
    ninety = cluster([f("F-DIVIDE", f"M{i}", "x") for i in range(96)])[0].weight
    assert 2.5 < ninety / one < 3.5


def test_shape_blanks_numbers_and_names():
    assert shape("91 line items") == shape("107 line items")
    assert shape("applies to 'A' in a module on 'B'; used by 3 formulas") == shape("applies to 'C' in a module on 'D'; used by 12 formulas")


def test_family_merge():
    mods = [f"C MA{i}b Calculate" for i in range(5)]
    fs = [f("F-MIXED-CLAUSE", m, li, "[LOOKUP + SELECT] in one bracket") for m in mods for li in ["2024 Budget", "2025 Jan Fcst", "Actual"]]
    cs = cluster(fs)
    fam = [c for c in cs if c.key == "family"]
    assert len(fam) == 1 and fam[0].count == 15 and "3 line items × 5 modules" in fam[0].label
    assert not [c for c in cs if c.key == "template"]


def test_subsidiary_views_in_one_module_are_one_decision():
    fs = [f("A-SUBSIDIARY", "C CAL03 Values", f"Flag {i}", f"applies to L{i}, Time in a module on L{i}, Cost, Time; used by {i} formulas") for i in range(5)]
    cs = cluster(fs)
    assert len(cs) == 1 and cs[0].key == "module" and cs[0].count == 5
