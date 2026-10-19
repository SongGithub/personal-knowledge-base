# Data model and invariants

**Status**: Proposed, 2026-10-17. Names below are logical records; private account,
bucket, subject and path policy values are runtime configuration.

## KnowledgeObject and KnowledgeRevision

- Stable logical object ID, vault-relative path, object kind and authority tier.
- S3 object version ID, opaque write-precondition ETag, independent SHA-256 digest,
  content type, origin, created/updated dates and policy revision.
- Source references, inference labels and attachment/link mapping.
- Deletion/tombstone or rename state; previous revisions stay recoverable but are
  not automatically visible to clients. Reject non-normalized/traversal paths.

Markdown object bodies are authoritative after cutover. A path mapping preserves
the current folders and links. Object keys do not establish permission by
themselves; current policy and the caller's grant are checked on every request.

## Principal, ClientGrant and ApprovalAuthority

- Principal: validated issuer + stable subject, owner binding and active status.
- ClientGrant: principal, client ID, audience, capabilities, permitted path rules,
  validity interval, consent/policy revision and revocation state/time.
- ApprovalAuthority: separately authenticated owner session, CSRF protection,
  exact proposal ID/digest and base revisions being approved.

Store these durably outside index artifacts. Missing policy fails closed.
Google OIDC credentials, signing material and broker encryption keys are secrets,
not fields exposed through MCP or copied to the SQLite snapshot.

The initial control table uses string `PK` and `SK` keys. Ingestion access is
restricted to partition namespaces `OP#`, `INDEX#` and `JOB#`; OAuth/grant/owner
records must use distinct namespaces and are not readable by the ingestion role.
`ExpiresAt` is an epoch-seconds TTL field only for records explicitly eligible
for expiry; durable audit/history records must not silently inherit a session TTL.

## LearningOperation and Proposal

- Key: principal/client/operation ID; store a request digest to detect ID reuse.
- Tool, destination/object ID, expected base revision, content/proposal digest,
  origin/evidence, submission date and policy evaluation result.
- State dimensions: validation, owner review, Markdown persistence, activity audit,
  ingestion/indexing and terminal failure; expose dimensions rather than one
  misleading `complete` flag.
- Persistence receipt: committed path + revision, timestamp and operation ID.
- Owner review: `not_required | pending | approved | rejected | stale`.
- Index state: `not_queued | pending | running | indexed | failed | superseded`.

Reserve the operation before mutation, reconcile conditional S3 writes with
operation state after crashes, and replay an identical request to the same
logical change. A proposal or queued job is not a persisted Markdown receipt.
No single transaction is assumed across S3, DynamoDB and the Markdown activity
log. Audit/outbox progress is idempotent and recoverable.

## IngestionJob

- Job ID, operation ID, logical source, object revision, content digest and task type.
- Extraction/synthesis/index stages, attempt count, retry timing, error category,
  selected model/processing contract and dead-letter status.
- Source revisions and current policy are rechecked before processing/promotion;
  late work is superseded instead of replacing a newer version.

An optional synthesis stage creates an inspectable proposal with evidence.
Embedding produces vectors, not a verified source or an approved Wiki change.

## EmbeddingContract

- Provider, immutable model/version identifier and query/document input modes.
- Tokenization/preprocessing, chunker version, dimensions, pooling, normalization
  and output numeric representation.
- Compatibility ID, approval record, benchmark version and comparison result.

Same dimension count is insufficient to establish compatibility. A contract
change builds a separate namespace, and query routing selects the matching
encoder before reading its index.

## IndexSnapshot and ActiveIndex

- Snapshot ID, build/publish times, source manifest of exact revisions/digests,
  embedding contract, authority-rule and schema versions.
- Artifact keys/versions, size and checksum for SQLite and manifest; counts and
  validation result; operation high-water marks and pending changes.
- SQLite tables initially mirror existing `notes`, `chunks` and `metadata`:
  paths/tiers/source hashes; ordered text chunks and vector BLOBs; model/schema/
  source/processing metadata. Extend with exact source revisions as needed.
- ActiveIndex: namespace, active validated snapshot/contract, generation,
  publisher lease/fencing token and predecessor.

Only a complete consistent SQLite backup can be published. A conditional pointer
change activates it. Workers pin/cache by snapshot version; policy/deletion
checks still use current control state. Snapshot freshness and the current note
revision are different fields. No writer mutates an index cached by a reader.

## MigrationRecord and ReleaseRecord

- Migration: selected source authority, frozen manifest, source/destination hashes,
  completeness and link verification, model comparison, cutover time, blocked old
  writers, rollback export and reconciliation of later accepted operations.
- Release: code/template digest, configuration compatibility, deployment identity,
  change-set/readiness/rollback result; references data namespaces but contains no
  private corpus or grants.

Authority does not change until the reviewed cutover succeeds. Release rollback
must not roll back canonical data or erase grants/accepted writes.
