# Feature Specification: Local Retrieval Quality Experiment

**Status**: Draft experiment, 2026-10-05. **Constitution**: 0.3.0 draft amendment.

## Need

Current keyword retrieval missed a relevant original private-school report. Semantic
retrieval may improve paraphrases across English and Chinese, but it could elevate
similar archived or unverified material over canonical knowledge. Measure both
accuracy and repeatability before deciding whether to adopt it.

## User stories and acceptance

1. Run lexical, vector, and hybrid retrieval over the same read-only Markdown
   snapshot. The index is entirely local, persistent, disposable, and rebuildable.
2. Assign note authority independently of similarity: explicit canonical/binding,
   verified support, ordinary, archive/source, draft/unverified. Allow a private
   authority manifest to resolve ambiguous notes without editing the vault.
3. Evaluate logical questions with multiple paraphrases, expected note paths,
   repeats, and separate runs. Report per-query top five and aggregate top-1,
   top-3/top-5 recall, same-top-1 rate, ranking variance, paraphrase agreement,
   canonical top-1, wrong archive override, unverified/draft top-1, and latency.
4. Generate only synthetic examples in Git. Real cases, paths, answers, indexes,
   embeddings, and reports stay in a local ignored directory outside the repo.

## Boundaries

- Markdown is the source of truth; the experiment never edits it.
- No hosted vector database, external embedding API, MCP, or answer generator.
- A downloaded multilingual model may run locally. Model identity and digest are
  recorded in the private report. Network access is only for model acquisition.
- Deterministic ranking and path tie breaks; report warm/cold and repeated runs.
- A result is relevant only if its note path matches an expected path. Authority
  errors are separately scored even when a lower-authority note is relevant.

## Exit decision

Adopt hybrid only if it materially improves paraphrased/vague top-1 or recall
without increasing archive override or draft top-1, and remains stable across
repeats and processes. Otherwise retain lexical or keep semantic retrieval
experimental. Do not silently change this threshold after seeing results.

## Incremental indexing requirements (added 2026-10-07)

The persistent local index must be refreshed incrementally rather than rebuilt
whenever a single note changes.

- **II-001**: Indexing MUST reconcile the persistent index against the vault per
  note. A matching whole-vault hash MUST NOT be the only path that avoids work,
  and a differing whole-vault hash MUST NOT by itself trigger a full rebuild.
- **II-002**: Unchanged notes MUST keep their existing chunks and vectors
  exactly; the embedding function MUST NOT be called for them.
- **II-003**: Added, changed, and deleted notes MUST be reconciled independently.
  Only chunks of added or changed notes may be re-embedded, and deleted notes
  MUST have their note and chunk rows removed.
- **II-004**: Authority-only changes (a private authority manifest or an
  authority-rule change with unchanged content) MUST update tiers without
  re-embedding.
- **II-005**: A full rebuild happens only when index compatibility changes
  (embedding model, chunker version, or index schema version) or when the index
  is corrupt or has missing vectors. Model, chunker, authority rules and index
  schema version MUST be recorded in index metadata.
- **II-006**: Indexing MUST report reconciliation statistics that clearly
  distinguish a no-op, an incremental update, an authority-only refresh, and a
  full rebuild, including added, changed, deleted and unchanged note counts and
  the number of chunks embedded.
- **II-007**: The whole-vault source hash MAY be retained for provenance and
  freshness detection.
