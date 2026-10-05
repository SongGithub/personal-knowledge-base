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
