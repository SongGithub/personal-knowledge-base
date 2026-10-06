# Tasks: Local Retrieval Quality Experiment

- [x] T001 Document constitution exception and experiment specification.
- [x] T002 Design local index, authority rules, benchmark and privacy boundary.
- [x] T003 Implement index, lexical/vector/hybrid search and deterministic ranks.
- [x] T004 Implement benchmark metrics, repeated runs and per-case report.
- [x] T005 Add synthetic fixtures and meaningful acceptance tests.
- [x] T006 Run on real KB, inspect outcomes and privacy boundary.
- [x] T007 Commit public artifacts and report the adoption decision.

## Incremental indexing (2026-10-07)

- [x] T008 Implement per-note reconciliation in build(): added, changed, deleted, unchanged.
- [x] T009 Preserve chunks and vectors for unchanged notes; embed only new chunks.
- [x] T010 Implement the compatibility gate (model, chunker, index schema, missing vectors) for full rebuilds.
- [x] T011 Record index schema version and reconciliation statistics in the build result.
- [x] T012 Add incremental-index tests (no-op, change, add, delete, authority, model/chunker, missing vector).
- [x] T013 Add a scheduled reconciliation workflow (.github/workflows/kb-index.yml) for a self-hosted macOS runner.
- [x] T014 Update spec 002, spec 003 and docs/openclaw-kb-connection.md for incremental refresh.
