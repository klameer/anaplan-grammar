# anaplan-grammar

A formal grammar and parser for the Anaplan formula language, which has
no published grammar. Reverse-engineered from Anapedia and a corpus of
13,214 unique formulas from ten production models.

Parse rate on that corpus: **13,214 / 13,214**. Round-trip and reference
recall checks in [corpus/README.md](corpus/README.md).

## What it does

```python
from anaplan_grammar import parse, references, unparse

ast = parse("'Employee Expenses'.Salary[SUM: 'Employee Details'.Region, LOOKUP: Grade]")
references(ast)
# [['Employee Expenses', 'Salary'], ['Employee Details', 'Region'], ['Grade']]
unparse(ast)
# "'Employee Expenses'.Salary[SUM: 'Employee Details'.Region, LOOKUP: Grade]"
```

The AST is plain dicts, so it serialises to JSON and is easy to walk from
any language. Node kinds: `num str bool blank ref un bin if call kwarg
clause`. See the docstring in `src/anaplan_grammar/parser.py`.

## What the corpus taught that Anapedia does not say

- A doubled single quote inside a quoted name is an escaped apostrophe:
  `'FOX''s Share'`.
- Bare (unquoted) names may contain spaces, digits, `? % # / | !`, and may
  begin or end with words that are keywords elsewhere: `Sum Channels`,
  `Category Lookup`, `all Phases`, `Count`. A clause kind (`SUM`,
  `LOOKUP`, `SELECT`, ...) is only a keyword when followed by `:` or `(`.
- Production formulas mix clause kinds in one bracket (`[LOOKUP: a,
  SELECT: b]`, `[LOOKUP: a, SUM: b]`) despite Anapedia's warnings. The
  grammar accepts them; a linter should flag them.
- `IF (` is ambiguous between a parenthesised condition and the
  spreadsheet form `IF(c, a, b)`. The parser tries the classic form first.
- Anapedia's own grammar-relevant facts are in `grammar/anaplan.ebnf`
  with the source page for each rule.

## Graph layer

`model.py` loads the Line Items and Modules exports into a `Model`;
`graph.py` builds the dependency graph and answers the questions builders
ask:

```python
from anaplan_grammar.model import load_model
from anaplan_grammar.graph import build_graph

m = load_model("line_items.csv", "modules.csv")
g = build_graph(m)
g.impact(("INP01 Volumes", "Price"))      # everything downstream, with distance
g.lineage(("OUT01 Board Pack", "Margin")) # everything upstream
g.hubs(20)                                # most-depended-on line items
g.unused()                                # referenced by no formula
g.cycles()                                # circular references
g.daisy_chains()                          # A -> B -> C pass-through chains
g.module_edges()                          # module-level rollup
```

Scored against Anaplan's own `Referenced By` column: precision 0.998,
recall 0.994 on a 900-line-item model; 0.938 and 0.972 on a 17,000-line-
item model, where the residuals are `COLLECT()` (needs the line-item
subset export) and references Anaplan's column itself omits. Details in
[corpus/README.md](corpus/README.md).

## Diff layer

`diff.py` compares two models loaded from exports: modules added and
removed, line items added, removed, renamed (same formula tree or same
input shape in the same module) and changed (formula compared at tree
level, so whitespace and quoting are not changes; plus format, applies-to,
time scale, versions, summary). Every change carries its blast radius
from the after-model's graph, and the list is sorted by it, so a reviewer
reads the change that touches 178 line items across 30 modules first.

```python
from anaplan_grammar.diff import diff_models, render_markdown
d = diff_models(before_model, after_model)
d.summary            # counts
render_markdown(d)   # the review table
d.to_dict()          # JSON
```

Run on a real model nine months apart (biotech FP&A, Jan to Oct 2025): 30
modules added, 40 removed (an entire scenario-modelling block retired),
264 line items added, 250 removed, 8 renames detected, 61 formula
changes, top change 178 downstream line items.

## Layout

```
grammar/anaplan.ebnf        the grammar, with provenance comments
src/anaplan_grammar/
  functions.py              function catalogue (Anapedia All Functions, 2026-09-21)
  lexer.py                  tokenizer; the bare-name rules live here
  parser.py                 recursive-descent parser -> AST
  unparse.py                AST -> formula text (round-trip tested)
  model.py                  Line Items + Modules exports -> Model
  graph.py                  dependency graph: impact, lineage, hubs, unused, cycles, chains
  diff.py                   two models -> change set with blast radius; Markdown and JSON
corpus/
  extract.py                line-item export -> formulas.jsonl (not committed)
  profile.py                what the corpus contains, before any grammar
  run_parse.py              parse rate per source, failures by class
  verify.py                 round trip, reference recall, keyword sanity
  verify_graph.py           graph edges scored against Anaplan's Referenced By column
  README.md                 sources, counts, parse-rate history
tests/test_grammar.py       fictional formulas covering every corpus shape
tests/test_graph.py         graph queries on the fictional Caldergate Planning model
tests/test_diff.py          diff on mutated copies of the fixture
tests/fixtures/             Caldergate Planning line-item and module exports (fictional)
```

## Running

```
python -m pytest tests -q
python corpus/extract.py      # needs your own exports; edit the paths
python corpus/run_parse.py
python corpus/verify.py
```

## Scope

Syntax and structure. No dimension inference, no type checking, no
evaluation, no view or export usage (those are not in the two exports).
Those are the next layers and they sit on this one. The grammar is
0.x until it has been run against models from organisations other than
the three in the corpus; send an anonymised line-item export and the
parse rate for it goes in the table.

## Licence

MIT for the code and grammar. The corpus is private and is not in this
repository; only the fictional test formulas are.

Karim Lameer, Master Anaplanner, CIMA-qualified.
[codelessops.com](https://codelessops.com)
