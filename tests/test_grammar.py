"""Fictional formulas covering every syntactic shape found in the corpus.
Names are invented (Caldergate Distribution Group, the fictitious company
used across Karim's public work). Run: python -m pytest tests -q
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import pytest
from anaplan_grammar.parser import parse, references, ParseError
from anaplan_grammar.unparse import unparse

CASES = {
    # Anapedia examples
    "sum_two_mappings": ("'Employee Expenses'.Salary[SUM:'Employee Details'.Region, SUM: 'Employee Details'.Role]",
                         ["Employee Expenses.Salary", "Employee Details.Region", "Employee Details.Role"]),
    "lookup_two": ("Pay table.Basic pay[LOOKUP: Grade, LOOKUP: Region]", ["Pay table.Basic pay", "Grade", "Region"]),
    "select_version": ("Income Statement.Sales[SELECT: Versions.Actual]", ["Income Statement.Sales", "Versions.Actual"]),
    "if_and": ("IF 'Value 1' >= 10 AND 'Value 2' >= 10 THEN \"A\" ELSE \"B\"", ["Value 1", "Value 2"]),
    "item_chain": ("IF ITEM(Organization) = Organization.'Company 01' OR Organization.'Company 05' THEN Company Class.Class A ELSE IF ITEM(Organization) = Organization.'Company 08' THEN Company Class.Class C ELSE Company Class.Class B",
                   ["Organization", "Organization.Company 01", "Organization.Company 05", "Company Class.Class A", "Organization", "Organization.Company 08", "Company Class.Class C", "Company Class.Class B"]),
    "previous_list": ("PREVIOUS(Lead count, Sales stage order)", ["Lead count", "Sales stage order"]),
    "time_offset": ("TIME.'Jan 21' + 1", ["TIME.Jan 21"]),
    "spreadsheet_if": ("IF(a > b, x, y)", ["a", "b", "x", "y"]),
    "finditem_literal": ('FINDITEM(Countries, "US")', ["Countries"]),
    "parent_item": ("PARENT(ITEM(Outlets))", ["Outlets"]),
    "textlist": ("Transactions.Product Text[TEXTLIST:Transactions.Customer, TEXTLIST: Transactions.Date]",
                 ["Transactions.Product Text", "Transactions.Customer", "Transactions.Date"]),
    "collect": ("COLLECT()", []),
    "date_nested": ('DATE(VALUE(LEFT(TEXT(Number), 4)), VALUE(MID(TEXT(Number), 5, 2)), VALUE(RIGHT(TEXT(Number), 2)))', ["Number", "Number", "Number"]),
    # corpus shapes, fictionalised
    "apostrophe_escape": ("'CAL Ultimates'.'Caldergate''s Share of Deficit' - Net Loss", ["CAL Ultimates.Caldergate's Share of Deficit", "Net Loss"]),
    "name_ends_in_lookup": ("'SYS Properties'.Final Code[LOOKUP: Category Lookup]", ["SYS Properties.Final Code", "Category Lookup"]),
    "name_starts_with_all": ("Phase Rank[SELECT: Project Phases.all Phases]", ["Phase Rank", "Project Phases.all Phases"]),
    "name_is_count": ("'SYS Counter'.Count", ["SYS Counter.Count"]),
    "name_ends_in_sum": ("IF NOT Use New? THEN all Roles SUM ELSE new Starters SUM", ["Use New?", "all Roles SUM", "new Starters SUM"]),
    "question_mark_names": ("Month only? OR Year? OR ITEM(Time) = TIME.All Periods", ["Month only?", "Year?", "Time", "TIME.All Periods"]),
    "quoted_trailing_dot": ("'Prime Time.' + 'Late Night.'", ["Prime Time.", "Late Night."]),
    "percent_in_name": ("CRO FTE * 'IN - Projects P4'.JV Recharge %", ["CRO FTE", "IN - Projects P4.JV Recharge %"]),
    "if_paren_condition": ("IF ('Amt A' <> 0 OR 'Amt B' <> 0) AND ISNOTBLANK(Code) THEN Code & \"||\" & Territory ELSE BLANK",
                           ["Amt A", "Amt B", "Code", "Code", "Territory"]),
    "mixed_clauses": ("Rate[LOOKUP: Task End, SELECT: Versions.Actual]", ["Rate", "Task End", "Versions.Actual"]),
    "unary_minus_clause": ("-'CALC Payments'.Milestone[SUM: 'CALC Payments'.'Accounts A2', SUM: 'CALC Payments'.Task End]",
                           ["CALC Payments.Milestone", "CALC Payments.Accounts A2", "CALC Payments.Task End"]),
    "rank_keywords": ('"Project Type " & TEXT(RANKCUMULATE(1, 1, ASCENDING, TRUE, \'P1 Project Type\'))', ["P1 Project Type"]),
    "decimal_negative": ("IF Variance > 0.001 THEN 1 ELSE IF Variance < -0.001 THEN -1 ELSE 0", ["Variance", "Variance"]),
    "custom_version_list": ("'IN - Parameters'.DCF Rate %[SELECT: Finance Versions.'#5']", ["IN - Parameters.DCF Rate %", "Finance Versions.#5"]),
    "nested_if_lookup": ("IF Lock? THEN 'Int. Lock' ELSE IF Use Override? THEN 'Int. Override' ELSE IF 'SYS Alloc'.'100% Allocation?'[LOOKUP: Licensee] THEN 1 ELSE 0",
                         ["Lock?", "Int. Lock", "Use Override?", "Int. Override", "SYS Alloc.100% Allocation?", "Licensee"]),
    "timesum_kwarg": ("TIMESUM(Count Month, -1, 0, AVERAGE)", ["Count Month"]),
    "concat_precedence": ("1 + 2 * 3 & \"x\" = \"6x\" AND TRUE OR NOT FALSE", []),
}


@pytest.mark.parametrize("name", list(CASES))
def test_parse_and_refs(name):
    src, expected = CASES[name]
    ast = parse(src)
    assert [".".join(p) for p in references(ast)] == expected


@pytest.mark.parametrize("name", list(CASES))
def test_round_trip(name):
    src, _ = CASES[name]
    ast = parse(src)
    assert parse(unparse(ast)) == ast


def test_precedence_tree():
    ast = parse("1 + 2 * 3 & \"x\" = \"6x\" AND TRUE OR NOT FALSE")
    assert ast["op"] == "OR"
    assert ast["l"]["op"] == "AND"
    assert ast["l"]["l"]["op"] == "="
    assert ast["l"]["l"]["l"]["op"] == "&"
    assert ast["l"]["l"]["l"]["l"]["op"] == "+"
    assert ast["l"]["l"]["l"]["l"]["r"]["op"] == "*"


@pytest.mark.parametrize("bad", [
    "IF a THEN b",            # missing ELSE
    "a[SUM: b",               # unclosed clause
    "a[FOO: b]",              # unknown clause kind
    "'unterminated",
    "a + ",
    "SUM(a,)",
])
def test_rejects(bad):
    with pytest.raises(Exception):
        parse(bad)
