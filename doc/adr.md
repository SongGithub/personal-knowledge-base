# ADR: Keep semantic retrieval experimental

- **Date:** 2026-10-05
- **Status:** Accepted for the experiment; production adoption deferred

## Context

The local retrieval experiment compared deterministic lexical search, local
multilingual vector search, and authority-aware hybrid search over the same
Obsidian Markdown snapshot. The experiment evaluated answer-note retrieval,
repeatability, paraphrase agreement, respect for canonical authority, and
latency. Vector embeddings and all note-level benchmark details remain local.

The authority order is canonical/binding, verified support, ordinary knowledge,
archive/source material, then draft or unverified. Similarity alone must not let
an archive override canonical knowledge.

## Measured comparison

| Metric | Lexical | Vector | Hybrid |
|---|---:|---:|---:|
| Top-1 accuracy | 36.4% | **68.2%** | 63.6% |
| Top-3 recall | 54.5% | **95.5%** | 77.3% |
| Top-5 recall | 54.5% | **95.5%** | 81.8% |
| Same top-1 for identical repeated queries | 100% | 100% | 100% |
| Ranking variance across repeats | 0.0 | 0.0 | 0.0 |
| Paraphrase agreement | 0% | **57.1%** | 42.9% |
| Canonical top-1 on applicable cases | 66.7% | 66.7% | **100%** |
| Wrong archive override | 33.3% | 22.2% | **0%** |
| Unverified/draft top-1 | 9.1% | 13.6% | 9.1% |
| Median retrieval latency | **1.1 ms** | 22.9 ms | 24.4 ms |
| P95 retrieval latency | **2.1 ms** | 28.0 ms | 29.0 ms |

All three produced identical top-five rankings for each query across two separate
process runs. Repeatability was therefore perfect in this deterministic setup;
the meaningful consistency difference was agreement across paraphrases.

## Decision

Keep vector and hybrid retrieval experimental. Vector materially improves
paraphrased retrieval over lexical search, but it still sometimes selects an
archive or unverified note first. Hybrid enforces authority well, but its lower
accuracy and recall do not justify adopting its added complexity yet. Retain
lexical search as the simplest baseline, and require a fresh holdout benchmark
before any production decision.

This result is limited: the benchmark is small, the hybrid authority rule was
adjusted after inspecting an initial run, and one expected Xero source is itself
an unverified working analysis. Matching an expected note path does not validate
the factual claim inside that note. Re-run with unseen cases and independently
reviewed expected paths before treating these percentages as general quality
estimates.

## Privacy and reproducibility

Only aggregate comparison metrics and this decision are recorded here. Private
queries, expected note paths, per-query results, model vectors, and the local
SQLite index stay outside Git. Markdown in the Obsidian vault remains canonical;
the retrieval index is disposable and rebuildable. Embeddings ran locally
through oMLX with the cached BGE-M3 model.

The detailed per-query report is local to the machine running the experiment.
See `specs/002-retrieval-quality-experiment/` for the experiment specification
and implementation plan.
