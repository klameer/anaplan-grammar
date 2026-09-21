# Corpus

The grammar is measured against real formulas, never published.

## Sources (2026-09-21)

| Label | Origin | Formulas | Unique |
|---|---|---|---|
| dl-lineitems-2025-01 | Line-item export, biotech FP&A, Jan 2025 | 628 | 383 |
| dl-lineitems-1-2025-10 | Line-item export, biotech FP&A, Oct 2025 | 656 | 228 |
| dl-lineitems-14-2025-12 | Line-item export, media participations model, Dec 2025 | 9,175 | 6,260 |
| dl-fy25 | Line-item export, media production model, FY25 | 7,978 | 976 |
| dl-fy26 | Line-item export, media production model, FY26 | 7,685 | 219 |
| exs-1-fpa | Archived FP&A hub model, 2019 to 2025 | 3,816 | 3,023 |
| exs-2-hr | Archived HR model | 1,124 | 773 |
| exs-3-dept | Archived department model | 335 | 187 |
| exs-4-exec | Archived exec model (duplicate of exs-1-fpa) | 3,816 | 0 new |
| exs-5-clinical | Archived clinical studies model | 92 | 87 |
| exs-6-pipeline | Archived pipeline project planning model | 1,307 | 1,078 |
| **Total** | 11 exports, 10 distinct models, 3 organisations | **36,612** | **13,214** |

All formulas come from models Karim built or maintained under contract.
The formulas themselves (which reference line-item and module names of
those organisations) are in `derived/`, which is gitignored and never
leaves this machine. What is published is the grammar, the parser, the
parse rate per source, the failure classes, and a fictional test set
that reproduces every syntactic shape the corpus contains.

## Extraction

`extract.py` reads the standard Anaplan "Line Items" grid export (CSV,
the columns Anaplan produces: Format, Formula, Summary, Applies To, Time
Scale, Time Range, Versions, ...). Module header rows are detected by an
empty Format and Formula. Only rows with a non-empty Formula are kept.

## Profile

`profile.py` reports what the corpus contains before any grammar is
written: length distribution, function usage, bracket-clause
combinations, keyword presence, characters inside quoted names, and
samples per feature. Its 2026-09-21 output drove the grammar:

- Median formula 73 characters, p99 735, max 4,573.
- 3,418 IF formulas, 3,417 with ELSE.
- Bracket clauses: LOOKUP 2,093, SUM 1,542, SELECT 1,471, and 446 formulas
  that mix kinds despite Anapedia's advice.
- Doubled single quotes as an apostrophe escape inside quoted names.
- Bare names containing `?`, `%`, `#`, `/`, `|`, `!`, digits and spaces,
  and bare names that begin or end with keyword-looking words (`Sum
  Channels`, `Category Lookup`, `all Phases`, `Count`).

## Parse rate

`run_parse.py` parses every unique formula and writes
`derived/failures.json`. History:

| Grammar | Parsed | Rate | Note |
|---|---|---|---|
| 0.1 first draft | 12,458 / 13,214 | 94.3% | keyword-in-name and '' escape missing |
| 0.1 + escape + keyword-as-whole-word | 13,001 / 13,214 | 98.4% | clause-kind at end of name |
| 0.1 + clause-kind only before `:`/`(` | 13,210 / 13,214 | 99.97% | 4 left, one shape |
