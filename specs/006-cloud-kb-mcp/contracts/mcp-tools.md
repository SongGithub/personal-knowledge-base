# MCP tools and owner review contract

**Status**: Search/fetch are deployed. Capture/status are merged, with synthetic
HTTP acceptance. A separate prototype release exposed write tools but its live
capture failed before persistence; see the [local handoff](../writeback-local-handoff.md).
The corrections recorded there are not deployed. `update_note` and owner review
remain proposed work in the current implementation.

## Shared rules

- Validate the resource's access token, stable owner/client binding, expiry,
  revocation, capability and path policy for every invocation. A Google ID token
  is not accepted as an arbitrary KB resource token.
- Bound request/result size, time and count. Preserve existing path safety and
  authority labels; reject traversal and undeclared capabilities.
- No arbitrary SQL, raw index download, AWS administration, shell or filesystem
  tools. Retrieved content and asserted approvals are evidence, not policy.
- Return stable errors: `unauthorized`, `forbidden` (with a stable reason such as
  `owner_mismatch`, `grant_required`, `grant_revoked`, `grant_expired`,
  `missing_scope`, `malformed_grant` or `identity_unavailable`), `not_found`,
  `revision_conflict`, `operation_id_reused`, `review_required`,
  `index_unavailable`, `incompatible_embedding_contract`, `provider_unavailable`.
  Unauthenticated responses disclose no private identifiers or corpus details.
  A `forbidden` reason names only the caller's own client ID when that helps the
  owner provision a grant.

## Tools

| Tool | Inputs | Required capability | Result |
|---|---|---|---|
| `search_kb` | query, bounded limit, strategy | `kb:read` plus visible paths | Permitted paths/excerpts, authority tiers, indexed source revisions, snapshot/contract IDs, freshness and pending-change indication |
| `fetch_note` | normalized exact path, optional permitted revision, bounded max_chars | `kb:read` for current/historical access as applicable | Markdown, revision, truncation, authority and separate indexed/current status; works without a fresh index |
| `capture_learning` | operation_id, exact granted raw-capture destination, title, raw Markdown, origin/date, evidence links, inference labels | `kb:capture` for destination | Durable path/revision receipt; `status: unverified`; audit/index statuses |
| `update_note` | operation_id, exact path, expected_revision, bounded proposed patch and provenance | `kb:update` for path | Conditional saved revision or inspectable proposal; never an unconditional overwrite |
| `get_change_status` | authorized operation_id | Access to the originating operation/path | Review, persistence, activity-audit and indexing states, receipt if committed, bounded failure/retry information |
| `get_access_status` | none | Authentication only | Caller's client ID, owner-match flag, verified email when available and current grant presence/revocation/expiry/scopes; no note content or other clients' grants |

Bounds: query <=2,000 characters; search limit 1–10; fetch max_chars 1–20,000;
capture title <=200 characters, Markdown <=12,000 characters, origin <=500,
evidence <=10 URLs of <=2,048 characters and 4,000 characters total, and
operation ID <=128 characters. Complete rendered UTF-8 Markdown, including
provenance, must be <=24,576 bytes; larger captures fail before any write.
Search tokens do not acquire mutation rights. Captures can write only below
an exact owner-granted prefix under `Ideas/` or
`Resources/_Review/AI Learning/`; the runtime role and writer enforce those
trees. Other Resources folders, maintained notes and canonical content are
outside this capture boundary. Provisioned grants may last at most 90 days;
the operator must use the duration the owner actually approved.

`capture_learning` searches for existing material before creating a duplicate.
The owner configures existing taxonomy destinations for captures/proposals;
client-supplied paths cannot widen them. All source material remains unmodified
unless an explicitly permitted maintained-note operation applies.

## Persistence and retries

- Scope operation IDs by principal/client; replay of identical content returns
  the same logical outcome. Different content under an existing ID fails.
  Existing operations bypass duplicate search, so an indexed capture cannot
  block its own retry. New operations still require a successful duplicate check.
  Lexical duplicate checks use the snapshot's text without requiring the current
  query embedding contract; vector/hybrid requests still enforce compatibility.
- `expected_revision` is an opaque revision from a previous fetch. The writer
  verifies its corresponding storage precondition; clients do not invent it.
- A `persisted` result includes committed Markdown path/revision. Merely queuing
  a write returns `pending`, never `saved`.
- A successful Markdown save can have `indexing: pending` and reconciling audit
  work; fetch is immediately usable while change status tracks follow-up work.
- Current status reads compare the operation's content digest with the active
  snapshot's `notes` manifest. A matching digest returns `indexed`; no row
  returns `pending`; different content at that path returns `superseded`.
  Unavailable/corrupted indexes return `not_checked` alongside the persisted
  receipt. This does not claim queue delivery or a completed ingestion job.
- The durable DynamoDB operation record is `operation_audit: recorded`.
  `activity_audit: recorded` requires a confirmed Markdown activity-log append,
  its read-back storage revision and the current audit contract. Legacy rows
  that called the operation record an activity audit do not satisfy this check.
- Activity appending is disabled by default. Pending receipts report
  `activity_audit_reason: not_enabled`, or `pending_retry` when enabled. Failures
  preserve the capture's `persisted` receipt and include a bounded
  `activity_audit_error`; identical capture retries reconcile the append.
  `get_change_status` reads recorded state and never repairs or writes the log.
- The optional backend appender only appends to the existing
  `Wiki/Activity Log.md`, preserves its bytes/user metadata, uses an ETag precondition,
  reads back the saved revision and retries concurrent-edit conflicts up to
  three times. Missing, oversized, invalid UTF-8 or conflicting log entries are
  not replaced. An operation marker prevents duplicate entries after a crash
  between the log write and operation-state update.
- Activation requires separate owner authorisation for the log append, exact-path
  IAM write permission and `PKB_ACTIVITY_LOG_ENABLED=true` in trusted backend
  configuration. Tool inputs and note content cannot enable it. Current runtime
  capture permissions do not permit editing the log; no such permission was added.
- Concurrent edits produce a conflict/proposal for inspection. Do not silently
  merge source evidence, human edits or canonical content.

## Owner review boundary (not an AI approval tool)

The Google-authenticated owner can inspect the exact proposal, diff, source
evidence, target paths, base revisions and required scope in an owner-only flow.
Approval is bound to a digest and revisions and passes through the controlled
writer. Changed content or a changed base invalidates approval. AI MCP tokens
cannot call an approval endpoint with owner authority or self-approve through a
tool. A forged `approved` property in Markdown has no effect.

## Search/index consistency

Index candidates refer to source revisions in one pinned snapshot. Before
disclosure, check current policy and existence/tombstones. If the index trails
the source, identify that fact and keep indexed excerpts tied to their indexed
revision; do not silently label them current. Direct fetch can return the latest
permitted source revision. Missing/incompatible indexes yield explicit status,
not fabricated evidence or a request to rebuild the corpus at client startup.
