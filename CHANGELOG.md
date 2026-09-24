# Changelog

## 0.1.0 (2026-09-24)

First release.

- Grammar and parser for the Anaplan formula language (EBNF in
  `grammar/anaplan.ebnf` with the Anapedia source for each rule); plain-dict
  AST, `references`, `references_ctx`, `unparse`.
- Model loader for the Line Items and Modules exports; dependency graph with
  impact, lineage, hubs, unused, cycles, daisy chains, module roll-up;
  verified against Anaplan's Referenced By column.
- Diff of two models loaded from exports, with blast radius per change.
- Lint: 19 rules with their source (Anaplan's checklist, formula facts, graph
  structure), thresholds overridable.
- Health report: five category scores, findings grouped into patterns,
  recommendations; opinion material for a review.
- 111 tests. The formula corpus used for calibration is private and not
  included; the scripts that build and verify one are.
