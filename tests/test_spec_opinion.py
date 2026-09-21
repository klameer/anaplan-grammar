import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.model import load_model
from anaplan_grammar.graph import build_graph
from anaplan_grammar.estate import load_estate, Estate
from anaplan_grammar.spec import build_spec, disco_role
from anaplan_grammar.lint import lint, RULES, PLANUAL
from anaplan_grammar.health import health
from anaplan_grammar import opinion
from anaplan_grammar.review import render_review

FX = pathlib.Path(__file__).parent / "fixtures"


def stack():
    m = load_model(FX / "caldergate_line_items.csv", FX / "caldergate_modules.csv", name="Caldergate Planning")
    g = build_graph(m)
    e = load_estate()
    return m, g, e, build_spec(m, g, e), lint(m, g)


def test_disco_role():
    assert disco_role("C CALPROJ01 # Project Phase Cube") == ("C", "CALPROJ")
    assert disco_role("S SYS00 Parameters") == ("S", "SYS")
    assert disco_role("CAL02 Revenue") == ("C", "CAL")
    assert disco_role("Alternative Summary") == ("?", "")


def test_spec_sections_and_facts():
    m, g, e, s, lr = stack()
    assert [t[:2] for t in s.sections] == ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8."]
    md = s.markdown()
    assert "As-built specification: Caldergate Planning" in md and "flowchart LR" in md
    assert "OUT01 Board Pack" in s.facts["chains"]
    assert s.facts["chains"]["OUT01 Board Pack"]["inputs"]     # rests on input modules
    assert "What the exports do not show" in md


def test_planual_cross_refs():
    for rid in ("A-DAISY", "F-MIXED-CLAUSE", "A-SUMMARY-ON"):
        assert RULES[rid].planual and all(p in PLANUAL for p in RULES[rid].planual)


def test_opinion_validator_keeps_drops_and_downgrades():
    m, g, e, s, lr = stack()
    obs = json.dumps([
        {"kind": "risk", "title": "real", "claim": "Margin % divides.", "refs": ["CAL04 Margin.Margin %", "finding:F-DIVIDE"], "priority": 1},
        {"kind": "risk", "title": "mixed", "claim": "two bad one good.", "refs": ["Ghost A", "Ghost B", "CAL02 Revenue"]},
        {"kind": "design_decision", "title": "invented", "claim": "no such thing.", "refs": ["Nope.Nothing"]},
        {"kind": "design_decision", "title": "unreferenced", "claim": "an assertion with no evidence.", "refs": []},
    ])
    op = opinion.ingest(s, lr, m, obs)
    titles = {o.title: o for o in op.observations}
    assert titles["real"].kind == "risk" and titles["real"].valid_refs == ["CAL04 Margin.Margin %", "finding:F-DIVIDE"]
    assert titles["mixed"].kind == "question" and titles["mixed"].dropped_refs == ["Ghost A", "Ghost B"]
    assert titles["unreferenced"].kind == "question"
    assert [d["title"] for d in op.dropped] == ["invented"]
    md = opinion.render_markdown(op)
    assert "Removed by the validator" in md and "Questions for the builder" in md


def test_prompt_contains_material_and_review_assembles():
    m, g, e, s, lr = stack()
    p = opinion.prompt(s, lr)
    assert "finding:F-DIVIDE" in p and "As-built specification" in p and "JSON array" in p
    h = health(m, g, lr)
    op = opinion.ingest(s, lr, m, '[{"kind":"risk","title":"t","claim":"c.","refs":["CAL04 Margin.Margin %"]}]')
    doc = render_review(s, h, op)
    for part in ("Architect's review", "How to read this", "Architect's opinion", "Model health", "As-built specification", "Unsigned"):
        assert part in doc
    assert "Signed: K" in render_review(s, h, op, signed_by="K")


def test_readings_feed_the_health_report():
    m, g, e, s, lr = stack()
    h = health(m, g, lr)
    p = opinion.prompt(s, lr, h)
    assert "# Health scores" in p and "- governance:" in p and "reading: exactly five" in p
    op = opinion.ingest(s, lr, m, json.dumps([
        {"kind": "reading", "title": "Formulas", "claim": "One unguarded divide in the margin module.", "refs": ["finding:F-DIVIDE", "CAL04 Margin"]},
        {"kind": "reading", "title": "not a category", "claim": "stray.", "refs": ["finding:F-DIVIDE"]},
    ]))
    r = op.readings()
    assert list(r) == ["formulas"] and r["formulas"].valid_refs == ["finding:F-DIVIDE", "CAL04 Margin"]
    assert [o.kind for o in op.observations if o.title == "not a category"] == ["question"]
    from anaplan_grammar.health import render_markdown as render_health
    md = render_health(h, r)
    assert "### Reading the scores" in md and "**Formulas " in md and "unguarded divide" in md
    doc = render_review(s, h, op)
    assert doc.count("unguarded divide in the margin") == 1        # in the health section, not repeated in the opinion body
    assert "Reading the health scores" in opinion.render_markdown(op)
