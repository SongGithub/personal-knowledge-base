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

## Remaining acceptance

- T042 stays open until the deployed HTTPS MCP is exercised through Google OAuth for all three strategies and fetch, plus freshness/deletion and offline-Mac checks. The earlier Google-authenticated mock proof applied to the prior synthetic lexical snapshot; it does not prove the new hybrid release.
- The original feature's two-client, writeback, migration, alarm and cost acceptance tasks remain open. This release is read-only and does not establish cloud writeback or a source-of-truth cutover.

## Failure and correction record

- A mocked deployment test initially inherited CodeBuild's ingestion setting; the test was isolated and the gate rerun.
- CloudFormation initially lacked tagging permission for its event source mapping. The execution role now permits mapping tags only with this project's requested tags, and the stack update completed.
- A 1,500-character chunk exceeded the embedding model input window on a private note. The chunker now uses 400-character pieces with provider-side `END` truncation as a safeguard. The expanded live synthetic gate passed before the successful release.
