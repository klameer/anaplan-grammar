import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.model import load_model
from anaplan_grammar.graph import build_graph
from anaplan_grammar.health import health, render_markdown, CATEGORIES

FX = pathlib.Path(__file__).parent / "fixtures"


def report():
    m = load_model(FX / "caldergate_line_items.csv", FX / "caldergate_modules.csv", name="Caldergate Planning")
    return health(m, build_graph(m))


def test_scores_shape():
    r = report()
    assert [s.category for s in r.scores] == CATEGORIES
    assert all(0 <= s.score <= 100 for s in r.scores)
    assert 0 <= r.overall <= 100
    assert r.scores[0].score == 100                    # structure: nothing planted
    assert r.scores[3].score < 90                      # integrity: a critical cycle
    assert r.scores[4].score < 60                      # governance: no notes


def test_recommendations_lead_with_critical():
    r = report()
    assert r.recommendations and "critical" in r.recommendations[0]
    assert "Cycle" in r.recommendations[0]


def test_render_and_json():
    r = report()
    md = render_markdown(r)
    for h in ["# Model health: Caldergate Planning", "## Overall", "## Model at a glance", "## Top findings", "## Recommendations", "## Findings by rule", "Unsigned"]:
        assert h in md
    d = r.to_dict()
    assert d["overall"] == r.overall and len(d["scores"]) == 5 and "lint" in d


def test_small_model_not_punished_for_size():
    r = report()
    assert r.scores[1].score >= 85   # formulas: one divide + one hardcode on 30 line items
