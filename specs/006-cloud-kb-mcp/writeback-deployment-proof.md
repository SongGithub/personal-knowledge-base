# Live MCP writeback proof

**Date:** 20 October 2026. **Environment:** development, AWS Sydney.

The owner requested deployment and fixes until the MCP write function worked.
The connected Google-authenticated MCP client successfully created a synthetic
learning, fetched its exact revision, retried safely and retrieved the newly
indexed note. Private credentials, owner/client identifiers, note bodies and
storage receipts remain outside this repository.

## Release

- Pinned source: `e0734e5088c0640dd03723b848d6c4e3459a8563`, published on
  `codex/kb-capture-recovery` in PR #7. It integrates the grant diagnostics from
  PR #6 and the existing pipeline/stack/retrieval fixes from PR #4.
- CodeBuild `6cb5f30e-9855-4876-85d9-ae08ce01fd83` completed `SUCCEEDED`.
  All 78 synthetic checks and infrastructure lint passed in the managed build.
- The live synthetic Bedrock quality and default-winner gates both passed.
  Across 33 cases, lexical reached 22 top-one / 26 top-three, vector 28 / 33,
  and hybrid 29 / 33. Hybrid remained the selected default. No gate was lowered.
- Bootstrap, foundation and application stacks reached `UPDATE_COMPLETE`.
  The source pin and runtime boundary were reviewed before execution; the
  existing custom-domain configuration remained disabled.
- Release SHA-256:
  `cc356b1cc778afbd3151e8dc79d57028553117763df82a13ab8499e23f856fe6`.
  Both Lambda code hashes match that artifact. Every deployed `cloud_kb` source
  file matches the pinned checkout; the embedding contract is `paragraph-400-v1`.
- Google owner binding, auth secret, callbacks, endpoint, client read/capture
  prefixes and original 90-day grant expiry were preserved. No client grant was
  extended and no existing-note update permission was enabled.

## Observed end-to-end checks

| Check | Actual result |
| --- | --- |
| Google-authenticated connector | Existing login remained usable after deployment |
| Existing connector request schema | `learning`, `date`, `evidence_links` and the symbolic destination were accepted under the exact review-folder grant |
| Capture | New unverified Markdown persisted under `Resources/_Review/AI Learning/` with provenance and a durable operation record |
| Immediate MCP fetch | Exact saved revision and SHA-256 matched; content was complete and included the synthetic marker |
| Independent S3 read | Exact object version, full expected UTF-8 body and SHA-256 matched; object reports `AES256` encryption |
| Identical retry | Same path, revision and digest returned with `replayed: true`; S3 had exactly one object version |
| Changed-content retry | Rejected with `operation_id_reused` |
| Canonical destination | `Wiki/` capture rejected with `forbidden` |
| Background ingestion | Status progressed from `pending` to `indexed` |
| Lexical and hybrid search | Both returned current evidence with matching indexed/current digests; hybrid ranked the new note first |
| Anonymous access | HTTPS tool request remained rejected with 401 |
| Existing rules | Authenticated fetch of the vault rules retained its previous digest |

No direct S3 write or manual index injection substituted for the MCP capture.
The existing S3 event, queue and ingestion worker published the new snapshot.
The observed post-build Lambda metrics reported 16 API invocations and one
ingestion invocation, with zero Lambda errors or throttles. CloudWatch metrics
can arrive late; this is a bounded post-deployment observation.

## Boundaries and remaining acceptance

- Activity-log appending remains disabled: the receipt correctly reports
  `activity_audit: pending` and `activity_audit_reason: not_enabled`. Separate
  owner authorisation and exact-path backend permission are required to enable
  edits to the existing log. The durable operation audit is recorded.
- The independent storage read used the owner operator's S3 access. A second
  separately registered AI client's live fetch has not been exercised; that
  part of T049 remains open. Synthetic cross-client HTTP checks pass.
- Existing-note updates, canonical owner review, offline-device acceptance,
  migration/restore and the wider operational tasks remain separately tracked.
  This proof establishes the approved new-note MCP write flow.
