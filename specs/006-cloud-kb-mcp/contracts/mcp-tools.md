# MCP tools and owner review contract

**Status**: Proposed contract, 2026-10-17; not currently exposed by the local
read-only server. Protocol/SDK versions and client authorization compatibility
must be pinned and exercised during implementation.

## Shared rules

- Validate the resource's access token, stable owner/client binding, expiry,
  revocation, capability and path policy for every invocation. A Google ID token
  is not accepted as an arbitrary KB resource token.
- Bound request/result size, time and count. Preserve existing path safety and
  authority labels; reject traversal and undeclared capabilities.
- No arbitrary SQL, raw index download, AWS administration, shell or filesystem
  tools. Retrieved content and asserted approvals are evidence, not policy.
- Return stable errors: `unauthorized`, `forbidden`, `not_found`,
  `revision_conflict`, `operation_id_reused`, `review_required`,
  `index_unavailable`, `incompatible_embedding_contract`, `provider_unavailable`.
  Unauthenticated responses disclose no private identifiers or corpus details.

## Tools

| Tool | Inputs | Required capability | Result |
|---|---|---|---|
| `search_kb` | query, bounded limit, strategy | `kb:read` plus visible paths | Permitted paths/excerpts, authority tiers, indexed source revisions, snapshot/contract IDs, freshness and pending-change indication |
| `fetch_note` | normalized exact path, optional permitted revision, bounded max_chars | `kb:read` for current/historical access as applicable | Markdown, revision, truncation, authority and separate indexed/current status; works without a fresh index |
| `capture_learning` | operation_id, configured destination, learning text, origin/date, evidence links, inference labels | `kb:capture` for destination | Durable path/revision receipt, or clearly labeled review proposal; audit/index statuses |
| `update_note` | operation_id, exact path, expected_revision, bounded proposed patch and provenance | `kb:update` for path | Conditional saved revision or inspectable proposal; never an unconditional overwrite |
| `get_change_status` | authorized operation_id | Access to the originating operation/path | Review, persistence, activity-audit and indexing states, receipt if committed, bounded failure/retry information |

Suggested existing bounds to retain: query <=2,000 characters; search limit 1–10;
fetch max_chars 1–20,000. Mutation and attachment bounds are configurable and must
be fixed before tools are enabled. Search tokens do not acquire mutation rights.

`capture_learning` searches for existing material before creating a duplicate.
The owner configures existing taxonomy destinations for captures/proposals;
client-supplied paths cannot widen them. All source material remains unmodified
unless an explicitly permitted maintained-note operation applies.

## Persistence and retries

- Scope operation IDs by principal/client; replay of identical content returns
  the same logical outcome. Different content under an existing ID fails.
- `expected_revision` is an opaque revision from a previous fetch. The writer
  verifies its corresponding storage precondition; clients do not invent it.
- A `persisted` result includes committed Markdown path/revision. Merely queuing
  a write returns `pending`, never `saved`.
- A successful Markdown save can have `indexing: pending` and reconciling audit
  work; fetch is immediately usable while change status tracks follow-up work.
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
