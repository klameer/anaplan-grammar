"""Graph layer on the fictional Caldergate Planning model (tests/fixtures)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from anaplan_grammar.model import load_model
from anaplan_grammar.graph import build_graph

FX = pathlib.Path(__file__).parent / "fixtures"


def graph():
    m = load_model(FX / "caldergate_line_items.csv", FX / "caldergate_modules.csv", name="Caldergate Planning")
    return m, build_graph(m)


def test_load():
    m, g = graph()
    assert len(m.modules) == 7
    assert ("CAL02 Revenue", "Net Revenue") in m.line_items
    assert m.modules["CAL02 Revenue"].functional_area == "Calculations"
    assert "Segments" in m.dimensions
    assert g.stats()["parse_errors"] == 0


def test_bare_and_qualified_refs_resolve():
    m, g = graph()
    assert g.edges[("CAL02 Revenue", "Net Revenue")] == {("CAL02 Revenue", "Gross Revenue"), ("CAL02 Revenue", "Discounts")}
    assert ("SYS00 Model Settings", "FX Rate USD") in g.edges[("CAL02 Revenue", "Revenue USD")]


def test_same_name_different_module_is_not_confused():
    m, g = graph()
    # CAL04 Margin.Net Revenue uses CAL02 Revenue.Net Revenue, not itself
    assert g.edges[("CAL04 Margin", "Net Revenue")] == {("CAL02 Revenue", "Net Revenue"), ("CAL02 Revenue", "Segment")}
    assert g.edges[("CAL04 Margin", "Margin")] == {("CAL04 Margin", "Net Revenue"), ("CAL04 Margin", "Opex")}


def test_list_refs_are_not_edges():
    m, g = graph()
    refs = g.refs[("CAL02 Revenue", "Segment")]
    assert [r.kind for r in refs] == ["dimension"]
    refs = g.refs[("SYS01 Time Settings", "Current Period?")]
    kinds = {tuple(r.path): r.kind for r in refs}
    assert kinds[("Time",)] == "dimension"
    assert kinds[("SYS00 Model Settings", "Current Period")] == "line_item"


def test_impact_and_lineage():
    m, g = graph()
    imp = g.impact(("INP01 Volumes", "Price"))
    names = {f"{a}.{b}" for a, b in imp}
    assert "CAL02 Revenue.Gross Revenue" in names
    assert "OUT01 Board Pack.Margin" in names          # five hops away
    assert imp[("OUT01 Board Pack", "Revenue Copy 2")] == 4
    lin = g.lineage(("OUT01 Board Pack", "Margin"))
    assert ("INP01 Volumes", "Units") in lin and ("CAL03 Opex", "Salaries") in lin


def test_unused_cycles_hubs_chains():
    m, g = graph()
    assert ("CAL03 Opex", "Unused Helper") in g.unused()
    assert ("CAL02 Revenue", "Net Revenue") not in g.unused()
    cyc = g.cycles()
    assert len(cyc) == 1 and set(cyc[0]) == {("CAL04 Margin", "Cycle A"), ("CAL04 Margin", "Cycle B")}
    hubs = dict(g.hubs(5))
    assert hubs[("CAL02 Revenue", "Net Revenue")] == 3 and hubs[("CAL02 Revenue", "Gross Revenue")] == 3
    chains = g.daisy_chains(min_len=3)
    assert chains[0] == [("OUT01 Board Pack", "Revenue Copy 2"), ("OUT01 Board Pack", "Revenue Copy"),
                         ("OUT01 Board Pack", "Revenue"), ("CAL02 Revenue", "Gross Revenue")]


def test_module_rollup():
    m, g = graph()
    me = g.module_edges()
    assert "CAL02 Revenue" in me["OUT01 Board Pack"]
    assert "INP01 Volumes" in me["CAL02 Revenue"]
    assert not any("OUT01 Board Pack" in v for v in me.values())   # nothing uses the output module
