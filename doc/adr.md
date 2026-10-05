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

This is the rerun after the vault update: 116 notes, 512 chunks, seven logical
cases, 22 paraphrases, and three repetitions per paraphrase.

| Metric | Lexical | Vector | Hybrid |
|---|---:|---:|---:|
| Top-1 accuracy | 31.8% | **72.7%** | 68.2% |
| Top-3 recall | 50.0% | **95.5%** | 81.8% |
| Top-5 recall | 54.5% | **95.5%** | 86.4% |
| Same top-1 for identical repeated queries | 100% | 100% | 100% |
| Ranking variance across repeats | 0.0 | 0.0 | 0.0 |
| Paraphrase agreement | 0% | **57.1%** | 42.9% |
| Canonical top-1 on applicable cases | 55.6% | 77.8% | **100%** |
| Wrong archive override | 33.3% | 22.2% | **0%** |
| Unverified/draft top-1 | 9.1% | 13.6% | 9.1% |
| Median retrieval latency | **1.0 ms** | 16.8 ms | 18.0 ms |
| P95 retrieval latency | **2.2 ms** | 21.7 ms | 22.5 ms |

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

## Proposed architecture: vendor-neutral shared retrieval

- **Date:** 2026-10-05
- **Status:** Proposed; implementation not started

The owner wants ChatGPT, Codex, and OpenClaw to access the same KB. Keep
Markdown canonical and keep a local, rebuildable SQLite index behind one
vendor-neutral retrieval core. Clients call a read-only interface; they never
open the SQLite file or implement separate authority ranking. Use MCP as the
first assistant-tool protocol adapter, starting with local stdio for OpenClaw.
Keep ChatGPT connectivity, authentication, and any tunnel in a separate
client-specific adapter. The retrieval core and database schema must not depend
on OpenAI.

The ChatGPT adapter remains future work. When used with a hosted model, only
requested result excerpts should cross into that provider's conversation
context, with that data boundary disclosed. The full vault and index remain
local. The proposed constitution amendment and implementation requirements are
in [`specs/003-shared-kb-retrieval/`](../specs/003-shared-kb-retrieval/spec.md).
The [OpenClaw connection guide](../docs/openclaw-kb-connection.md) documents the
planned configuration and clearly marks the not-yet-implemented server command.
