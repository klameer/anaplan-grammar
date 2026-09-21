"""Lint on the Caldergate fixture, which plants: an unguarded divide (Margin %),
a cycle (Cycle A/B), a daisy chain (Revenue Copy 2), a hard-coded constant (Bonus = Salaries * 0.1)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.model import load_model
from anaplan_grammar.graph import build_graph
from anaplan_grammar.lint import lint, render_markdown, RULES

FX = pathlib.Path(__file__).parent / "fixtures"


def run(**overrides):
    m = load_model(FX / "caldergate_line_items.csv", FX / "caldergate_modules.csv", name="Caldergate")
    return m, lint(m, build_graph(m), overrides=overrides)


def rules_hit(res):
    return {(f.rule, f.object) for f in res.findings}


def test_planted_findings():
    m, res = run()
    hit = rules_hit(res)
    assert ("F-DIVIDE", "CAL04 Margin.Margin %") in hit
    assert ("G-CYCLE", "CAL04 Margin.Cycle A") in hit or ("G-CYCLE", "CAL04 Margin.Cycle B") in hit
    assert ("A-DAISY", "OUT01 Board Pack.Revenue Copy 2") in hit
    assert ("F-HARDCODE", "CAL03 Opex.Bonus") in hit
    assert not any(f.rule == "F-PARSE" for f in res.findings)


def test_cycle_without_previous_is_critical():
    m, res = run()
    cyc = [f for f in res.findings if f.rule == "G-CYCLE"]
    assert cyc and cyc[0].severity == "critical"


def test_thresholds_override():
    m, res = run()
    assert not any(f.rule == "A-LI-COUNT" for f in res.findings)
    m, res = run(**{"A-LI-COUNT": {"max_line_items": 5}})
    assert any(f.rule == "A-LI-COUNT" and f.object == "CAL04 Margin" for f in res.findings)


def test_notes_is_one_finding():
    m, res = run()
    notes = [f for f in res.findings if f.rule == "H-NOTES"]
    assert len(notes) == 1 and "7 of 7" in notes[0].message


def test_sorted_and_rendered():
    m, res = run()
    sev = [f.severity for f in res.findings]
    order = {"critical": 0, "major": 1, "minor": 2, "info": 3}
    assert sev == sorted(sev, key=order.get)
    md = render_markdown(res)
    assert "# Lint" in md and "F-DIVIDE" in md and "Margin %" in md
    assert set(res.rules_run) == set(RULES)
