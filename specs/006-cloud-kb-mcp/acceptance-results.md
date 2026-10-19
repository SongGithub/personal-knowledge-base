# Cloud retrieval parity acceptance evidence

Date: 2026-10-19. Environment: development, AWS ap-southeast-2.
This file records aggregate checks only; private note paths and content remain outside Git.

## Release and quality gate

- CodeBuild release pinned to commit `46037fabb56ca21749ada1303bc7fb89915de326` succeeded. The pipeline ran 26 synthetic unit tests and infrastructure lint before deployment.
- The live Bedrock Cohere Embed Multilingual v3 gate used only synthetic English and Chinese text. Hybrid top-1 was 12/14; top-3 was 14/14; both cross-language cases were in the top three. A long synthetic Chinese document was also fully embedded through the production chunker.
- GitHub PR checks for CloudFormation and synthetic HTTP/Lambda adapters passed. GitHub deployment jobs were intentionally skipped on the draft PR; the pinned AWS CodeBuild pipeline performed deployment.

## Deployed private snapshot

- The foundation and application CloudFormation stacks both reached `UPDATE_COMPLETE`; CodeBuild reached `SUCCEEDED`.
- The active pointer is `hybrid-sqlite-v1`, with the `bedrock-cohere-multilingual-v3-f32-unit-paragraph-400-v1` embedding contract and `SyntheticOnly=false`.
- The active SQLite snapshot contains 152 Markdown notes and 2,457 chunks. Its SHA-256 matches the active descriptor; every stored vector has 4,096 bytes (1,024 float32 dimensions).
- Both the Markdown and index buckets have all four S3 public access blocks enabled and default SSE-S3 encryption (`AES256`). The active snapshot object itself reports `AES256` encryption.
- A direct production-code search over the active snapshot with a synthetic query found the synthetic fixture using lexical, vector and hybrid strategies; each returned current S3 evidence. Direct fetch matched the fixture SHA-256. No private note path or excerpt was printed.
- The deployed HTTPS MCP passed Google OAuth verification after this release: unauthenticated tool access was denied; the authenticated verifier found current synthetic evidence through lexical, vector and hybrid tools; and `fetch_note` matched the fixture SHA-256. The verifier's DynamoDB grant was checked to have only `kb:read`, the exact synthetic note path, `SyntheticOnly=true`, and a 30-minute expiry.

## Remaining acceptance

- T042 stays open for live freshness/deletion and offline-Mac checks. The OAuth tool checks above prove the new hybrid release for one synthetic-only client; they do not grant that client access to private notes.
- The original feature's two-client, writeback, migration, alarm and cost acceptance tasks remain open. This release is read-only and does not establish cloud writeback or a source-of-truth cutover.

## Initial writeback branch evidence

- The `codex/kb-writeback` change adds `capture_learning` and `get_change_status`; it writes raw Markdown under a separately granted `Ideas/` prefix, marks the note `unverified`, and relies on the existing S3 `ObjectCreated` event for asynchronous indexing.
- Synthetic tests exercise conditional S3 creation, same-operation replay, changed-content operation-ID rejection, retry after a storage failure, separate `kb:capture` authorization, synthetic MCP HTTP persistence, and an independently authorized second client fetching the new note.
- The API role's S3 `PutObject` permission and both runtime-permissions-boundary templates are narrowed to `notes/Ideas/*`; read access remains separately scoped by the per-client grant.
- At the time of those branch checks, no write grant or write-enabled release had been deployed. A later prototype rollout exposed write tools and received a bounded grant, but its capture failed before persistence. The [local continuation handoff](writeback-local-handoff.md) records the failure and corrections; T049 remains open. Current remote state was not rechecked during that local-only continuation.

## Failure and correction record

- The 20 October local-only continuation implemented a disabled-by-default,
  recoverable activity-log append, with conditional writes, saved-revision
  readback and capture-retry reconciliation. The socket-free synthetic suite
  passed 65 checks. No live activity-log permission was added, no pipeline was
  invoked and no deployment or live write proof was completed; see the
  [handoff](writeback-local-handoff.md).
- After the owner enabled local Git writes and network access, the complete
  synthetic cloud suite passed all 66 checks, including the real loopback HTTP
  case. This resolves the earlier sandbox restriction without excluding tests.

- A mocked deployment test initially inherited CodeBuild's ingestion setting; the test was isolated and the gate rerun.
- CloudFormation initially lacked tagging permission for its event source mapping. The execution role now permits mapping tags only with this project's requested tags, and the stack update completed.
- A 1,500-character chunk exceeded the embedding model input window on a private note. The chunker now uses 400-character pieces with provider-side `END` truncation as a safeguard. The expanded live synthetic gate passed before the successful release.
