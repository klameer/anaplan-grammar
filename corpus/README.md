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
| 0.1 + `IF (` classic-first | 13,214 / 13,214 | 100% | |

## Verification (`verify.py`, 2026-09-21)

Parsing is not the same as parsing correctly. Three checks on every
unique formula:

| Check | Result |
|---|---|
| Round trip: `parse(unparse(parse(f))) == parse(f)` | 13,214 / 13,214 |
| Reference recall: every quoted name in the source appears in a reference path | 13,214 / 13,214 |
| Keyword sanity: no bare keyword ends up as a name | 13,214 / 13,214 |
| Function catalogue: every call name is in Anapedia's list | 0 unknown |

Node counts across the corpus: 40,021 references, 14,796 binary ops,
6,454 function calls, 5,714 bracket clauses, 4,792 IFs, 902 unary ops.

Two things the round trip caught that the parse rate did not: an IF in
the middle of an expression must be parenthesised when unparsed or the
tail is swallowed into its ELSE branch; and hand-written chains of a
hundred-plus `+` terms (every month summed by name) overflow a naive
recursive unparser.

## Graph layer (`verify_graph.py`, 2026-09-21)

The exports carry Anaplan's own reverse-edge list in the `Referenced By`
column. The graph built from parsed formulas is scored against it on the
two exports that pair with a Modules export.

| Model | Line items | Formulas | Edges | Precision | Recall |
|---|---|---|---|---|---|
| biotech FP&A, Jan 2025 | 900 | 628 | 853 | 0.998 | 0.994 |
| media participations, Dec 2025 | 16,987 | 9,175 | 21,737 | 0.938 | 0.972 |

The residuals were read by hand:

- **Missed edges (recall)** are `COLLECT()` line items. COLLECT pulls
  source line items through a line-item subset; the membership of that
  subset is not in either export, so those edges cannot be built from
  formulas. Anaplan lists them; we cannot. Known gap, needs the line-item
  subset export.
- **Extra edges (precision)** are real. For `SYS00 Time Settings
  (Month).Start of Month`, Anaplan's column lists 12 dependents; the graph
  finds 14, and the two it adds have formulas that plainly reference it.
  Anaplan's `Referenced By` omits some references. The graph is more
  complete than the export it is checked against, on this point.
- Five missed edges on the biotech model are line items whose formula is
  a constant (`2`, `3`) but which Anaplan lists as referencing another
  item: a non-formula dependency the export does not explain.

Queries run on both models: impact (one input on the media model reaches
1,758 line items across 143 modules, 17 hops deep), lineage, hubs,
unreferenced line items (395 of 900; 8,615 of 16,987, where "unreferenced"
means by no formula; views and exports are not in these files), cycles
(4 and 88, all the deliberate cf/bf and beginning/end-of-month kind),
daisy chains of pure pass-through line items (4 and 81).
