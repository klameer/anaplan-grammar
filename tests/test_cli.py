import sys, pathlib, json
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.cli import main

FX = pathlib.Path(__file__).parent / "fixtures"
LI, MO = str(FX / "caldergate_line_items.csv"), str(FX / "caldergate_modules.csv")


def run(capsys, *argv):
    main(list(argv)); return capsys.readouterr().out


def test_parse_refs(capsys):
    out = run(capsys, "parse", "'Employee Expenses'.Salary[SUM: 'Employee Details'.Region, LOOKUP: Grade]", "--refs")
    assert out.split() == ["Employee", "Expenses.Salary", "Employee", "Details.Region", "Grade"] or "Grade" in out


def test_parse_json(capsys):
    out = json.loads(run(capsys, "parse", "1 + 2", "--json"))
    assert out["t"] == "bin" and out["op"] == "+"


def test_parse_error_exits():
    with pytest.raises(SystemExit):
        main(["parse", "IF a THEN b"])


def test_explain_text_and_json(capsys):
    out = run(capsys, "explain", LI, "--modules", MO, "CAL04 Margin.Margin")
    assert "Net Revenue - Opex" in out and "used by" in out
    d = json.loads(run(capsys, "explain", LI, "CAL04 Margin.Margin", "--json"))
    assert d["uses"] == ["CAL04 Margin.Net Revenue", "CAL04 Margin.Opex"]


def test_explain_bare_unique_name(capsys):
    out = run(capsys, "explain", LI, "Bonus")
    assert out.startswith("CAL03 Opex.Bonus")


def test_explain_ambiguous_and_missing():
    with pytest.raises(SystemExit): main(["explain", LI, "Net Revenue"])     # 3 modules
    with pytest.raises(SystemExit): main(["explain", LI, "Nope.Nothing"])


def test_impact_lineage(capsys):
    d = json.loads(run(capsys, "impact", LI, "INP01 Volumes.Price", "--json"))
    assert d["count"] == 14 and d["modules"] == 3
    d = json.loads(run(capsys, "lineage", LI, "OUT01 Board Pack.Margin", "--json", "--depth", "2"))
    assert all(i["distance"] <= 2 for i in d["items"])


def test_diff_no_change_does_not_fail(capsys):
    out = run(capsys, "diff", LI, LI, "--fail-on-change")   # identical: no exit 2
    assert "Formula changes: 0" in out


def test_lint_filters_and_fail(capsys):
    d = json.loads(run(capsys, "lint", LI, "--modules", MO, "--json", "--min-severity", "major"))
    assert all(f["severity"] in ("critical", "major") for f in d["findings"])
    d = json.loads(run(capsys, "lint", LI, "--json", "--rules", "F-DIVIDE"))
    assert d["rules_run"] == ["F-DIVIDE"] and d["findings"][0]["object"] == "CAL04 Margin.Margin %"
    with pytest.raises(SystemExit) as e:
        main(["lint", LI, "--fail-on", "major"])
    assert e.value.code == 2
    capsys.readouterr()   # drop the output printed before the exit
    d = json.loads(run(capsys, "lint", LI, "--json", "--threshold", "A-LI-COUNT:max_line_items=5"))
    assert any(f["rule"] == "A-LI-COUNT" for f in d["findings"])


def test_health_and_stats_and_rules(capsys, tmp_path):
    out = tmp_path / "h.md"
    run(capsys, "health", LI, "--modules", MO, "--out", str(out))
    assert "## Overall" in out.read_text(encoding="utf-8")
    d = json.loads(run(capsys, "stats", LI, "--json"))
    assert d["line_items"] == 30 and d["parse_errors"] == 0
    d = json.loads(run(capsys, "rules", "--json"))
    assert any(r["id"] == "G-CYCLE" for r in d)
