# Contributing

Thank you for looking. This is maintained by one person at CodelessOps;
contributions of every size are welcome.

## The most useful contribution

A formula the parser rejects or misreads. Open an issue with the formula
text (rename the modules and line items if you must; keep the shape) and
what Anaplan does with it. An anonymised Line Items export from an old
model is the next most useful thing, by agreement in an issue first.

## Running it

```bash
pip install -e ".[dev]"
python -m pytest -q tests
```

The tests are self-contained; the calibration corpus is private and not
needed. `corpus/` holds the scripts that build and verify a corpus from
your own exports.

## Ground rules

- Every grammar change cites the Anapedia page or the corpus evidence for
  it, in `grammar/anaplan.ebnf` or the parser docstring.
- A new lint rule names its source (Anaplan's checklist, a formula fact, or
  graph structure) and comes with a fixture in `tests/`.
- Private model exports are never committed, quoted in issues, or turned
  into fixtures without the owner's written permission.

## Issues and pull requests

Small pull requests with a test are easiest to review. CI runs the tests on
Python 3.10 to 3.13.
