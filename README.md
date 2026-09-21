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

## Layout

```
grammar/anaplan.ebnf        the grammar, with provenance comments
src/anaplan_grammar/
  functions.py              function catalogue (Anapedia All Functions, 2026-09-21)
  lexer.py                  tokenizer; the bare-name rules live here
  parser.py                 recursive-descent parser -> AST
  unparse.py                AST -> formula text (round-trip tested)
corpus/
  extract.py                line-item export -> formulas.jsonl (not committed)
  profile.py                what the corpus contains, before any grammar
  run_parse.py              parse rate per source, failures by class
  verify.py                 round trip, reference recall, keyword sanity
  README.md                 sources, counts, parse-rate history
tests/test_grammar.py       fictional formulas covering every corpus shape
```

## Running

```
python -m pytest tests -q
python corpus/extract.py      # needs your own exports; edit the paths
python corpus/run_parse.py
python corpus/verify.py
```

## Scope

Syntax only. No dimension inference, no type checking, no evaluation.
Those are the next layers and they sit on this one. The grammar is
0.x until it has been run against models from organisations other than
the three in the corpus; send an anonymised line-item export and the
parse rate for it goes in the table.

## Licence

MIT for the code and grammar. The corpus is private and is not in this
repository; only the fictional test formulas are.

Karim Lameer, Master Anaplanner, CIMA-qualified.
[codelessops.com](https://codelessops.com)
