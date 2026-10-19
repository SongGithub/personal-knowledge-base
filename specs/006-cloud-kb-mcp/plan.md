# Implementation Plan: Cloud KB MCP and Learning Writeback

**Git branch at authoring**: `feat/incremental-kb-indexing` (pre-existing work
preserved; no branch switch).  
**Feature context**: `006-cloud-kb-mcp` | **Date**: 2026-10-17 |
**Spec**: [spec.md](spec.md)  
**Status**: Draft application design; foundation CloudFormation and the OIDC
deployment workflow are authored as the first implementation slice. See
[tasks.md](tasks.md) and [permission-verification.md](permission-verification.md).
No cloud resources have been created or private data migrated.

**Mock-proof follow-up**: `cloud_kb/` now contains the first read-only HTTP/Lambda
slice, with Google broker and encrypted DynamoDB storage adapters. Local synthetic
verification passed; [mock-proof.md](mock-proof.md) distinguishes that evidence
from the still-unperformed cloud/Google acceptance. Search is lexical-only until
the approved semantic adapter is implemented. The application template is authored
with a separately gated application job and exact anchored API permissions. The
extension has not been applied to AWS.

## Summary

Use private S3 objects as authoritative Markdown after a verified cutover. Serve
bounded authenticated MCP tools through API Gateway HTTP API and on-demand
Python Lambda. Use Google OIDC for the owner's identity, a maintained MCP OAuth
authorization component for client grants, and backend enforcement for every
tool/path. DynamoDB holds durable grants, operations and index publication state;
SQS drives recoverable background ingestion. Store completed SQLite embedding
index snapshots in S3 and cache a selected snapshot locally in each search worker.

Production query/document embeddings use an approved on-demand cloud model.
Local oMLX remains an optional experiment/batch worker, never a required serving
dependency. Source synthesis is a separate optional model step with evidence and
human review, not a property of embeddings. Obsidian and iCloud are migration
inputs/optional clients rather than target runtime requirements.

## Technical Context

**Language/Version**: Python 3.12 proposed; reuse `retrieval_experiment.py` and the
vendor-neutral facade in `kb_mcp_server.py` without silently relaxing their
existing local-only boundaries.  
**Primary Dependencies**: boto3, NumPy, SQLite, maintained MCP SDK/Google-backed
OAuth broker; FastMCP Google integration is a candidate to validate and pin.
The remote adapter must use durable broker state rather than default memory.  
**Storage**: S3 Standard/versioning for notes, attachments and index artifacts;
DynamoDB on-demand for grants, operations and publication metadata; SQS and DLQ
for ingestion. Secrets Manager for named OAuth/signing secrets.  
**Validation**: Foundation templates passed AWS validation and pinned lint;
permission evidence is recorded separately. Application unit/contract/integration
and bilingual retrieval acceptance checks remain future work.  
**Target Platform**: AWS Lambda Event Functions on Linux; initially one regional
deployment, provisionally Sydney (`ap-southeast-2`), subject to account/model
availability and regional pricing review.  
**Project Type**: Remote MCP service, asynchronous ingestion worker, owner review
boundary and migration/export tooling around the existing retrieval core.  
**Performance Goals**: Proposed warm p95 <5 s and cold p95 <25 s for the declared
small workload; 20 changed notes indexed within five minutes when dependencies
are healthy; monthly end-to-end regional SLO 99.9%, not a service guarantee.  
**Constraints**: No required warm/provisioned application/model instances; private
data outside Git/images; independently executable short MCP calls; provider
approval and quality comparison before embedding private data.  
**Scale/Scope**: One owner, multiple client grants; planning example 10,000 HTTP
requests/month and a small index that fits worker memory and ephemeral storage.
Actual corpus/index size and ingestion token count must be measured privately.

## Constitution Check

Pre-design and post-design review against draft constitution 0.7.0:

| Principle | Design result / gate |
|---|---|
| Private by default | Private account storage, bounded evidence disclosure; no source/image bundling. Actual migration remains unperformed. |
| Evidence | Preserve sources, origin/date, inference labels and reference revisions. |
| Human control | Configured routine capture; exact canonical proposals approved only by the owner. |
| Portability | Ordinary Markdown/folders; rebuildable index; storage and model adapters around the core. |
| Small increments | Separate auth/transport, read, write, index and migration slices; no always-on vector cluster. |
| Taxonomy | Preserve current top-level folders; configure a permitted existing capture destination before enabling writes. |
| Cloud amendment | This is the requested design documentation. Provider/model data approval, cost acceptance and verified cutover remain pre-deployment gates, not implied completed approvals. |

There is no requirement to modify the actual vault's rules or navigation in this
documentation task. Before migration, reconcile those rules with the owner's
approved authority cutover and enforce them in the writer. No implementation
may bypass a remaining gate because the plan exists.

## Architecture and request lifecycle

1. AI client discovers MCP/OAuth endpoints and signs in via Google. Bind the
   configured stable owner subject; issue a separate scoped client grant.
2. The HTTP adapter validates the service's audience-bound access token and
   checks current grants, revocation and path/tool policy. Google tokens are not
   passed through as KB access tokens. Application sign-in grants no AWS IAM role.
3. Search pins an active index descriptor and uses its immutable SQLite snapshot
   from S3, cached in `/tmp`/memory. Embed the question using the descriptor's
   exact approved contract. Filter results against current policy, tombstones and
   permitted source revisions; expose indexed and current freshness separately.
4. Fetch reads an authorized Markdown revision directly from S3 without depending
   on index freshness. A retired/deleted object is not exposed through old
   revisions unless policy explicitly permits historical access.
5. A capture/update reserves an idempotent operation, checks destination policy
   and base revision, conditionally writes Markdown, reconciles its audit/outbox
   record and returns the durable note revision with indexing pending.
6. Approved mutations enqueue ingestion. A serialized publisher reads changed
   object revisions, chunks them, calls the approved embedding API, builds a
   consistent SQLite backup, validates it and publishes a new descriptor.
7. Unapproved canonical changes remain proposals in a configured existing
   taxonomy destination. The human approval flow validates the owner separately,
   binds exact content/base revisions and invokes the same controlled writer.

MCP transport must support actual ChatGPT, Codex and OpenClaw client versions.
Use stateless request/response operation where compatible; validate protocol
negotiation/legacy handshake behavior and Google OAuth discovery, PKCE, client
registration, callback, refresh, revocation and restart behavior before claiming
interop. HTTP API's integration timeout constrains synchronous work; long
synthesis/indexing uses queued jobs and operation status. A normal Docker image
containing the current stdio executable is not a remote Lambda adapter.

## Storage and publication design

Proposed key layout (names and bucket identities are runtime parameters):

```text
notes/<existing-vault-relative-Markdown-path>
attachments/<existing-relative-path>
indexes/<snapshot-id>/index.sqlite
indexes/<snapshot-id>/manifest.json
```

Keep aliases/attachment resolution and existing folder names through an explicit
path mapping; do not duplicate `.md` suffixes or introduce a new vault taxonomy.
Application control records and grants live in DynamoDB, not in the index.

- S3 conditional writes reject stale note updates; VersionId identifies stored
  revisions and ETag is an opaque write precondition, not a universal checksum.
- Object versioning is recoverable history, not a substitute for an independently
  recoverable export and restore procedure. Bound old index/object retention.
- There is no multi-object S3 transaction. Operation/outbox state reconciles note,
  activity-record and queue progress after partial failure. Concurrent appends to
  the existing Markdown activity log require serialization and revision checks.
  Its narrowly configured automatic append permission grants no general Wiki edits.
- Queue deliveries may duplicate or arrive late. Check current source revision;
  obsolete work cannot overwrite newer data. Serialize publication, use a fenced
  lease and conditional active-pointer update; never publish merely because a job
  still holds an old local snapshot.
- SQLite is created/read on a worker filesystem. Publish a closed/checkpointed
  consistent backup and checksum; never upload a live database while omitting
  required journal/WAL data. Never mount an S3 key as a shared mutable database.
- A snapshot records exact source revisions and embedding/chunking contracts.
  Failed publication retains the prior pointer. Caches are disposable and version
  checked; a cold worker downloads a complete selected artifact before serving.
- For initial scale, retain local vector math and lexical scoring. Reassess the
  index design when measured snapshot download, memory, corpus scanning or refresh
  cost breaches the agreed budget; a managed vector database is not assumed free.

## Ingestion, synthesis and embedding migration

The current implementation reads local Markdown, sends text to loopback oMLX
and writes chunks/vectors/metadata to a separate `index.sqlite`. Its incremental
builder already reuses unchanged vectors; its serving freshness check scans the
local source tree and refuses stale indexes. Add remote adapters and direct
fetch rather than carrying that global stale-index failure into cloud writeback.

Target ingestion reads S3 object bodies, in memory or temporary working storage;
it does not require an iCloud mount or a durable local vault. Extraction and
source preservation precede optional LLM synthesis/proposals. Only approved
knowledge changes are promoted under the configured policy; embedding and index
work has its own retry/status lifecycle.

Candidate production inference is Bedrock on-demand embeddings. Select and pin
a Chinese/English-capable model only after a representative quality/cost
comparison and explicit private-content provider approval. Do not select an
English-optimized default solely for price. A new model normally requires a full
document re-embedding and a new snapshot namespace; dimensions alone do not prove
compatibility. Both query and document paths must use compatible model/version,
input types, tokenization, pooling and normalization.

### Cloud hybrid-search execution (2026-10-19 design update)

The S3 copy is source data, not a searchable index. The deployed mock snapshot
uses `lexical-sqlite-v1`, contains only the synthetic fixture, and rejects
`vector`/`hybrid`. Treat that as a migration baseline, not cloud parity.

For the initial bulk build, an AWS worker inventories `notes/*.md`, reads only
current private S3 objects, computes SHA-256 and source VersionId, applies the
local `paragraph-400-v1` chunker and authority rules, and generates embeddings
for each chunk. On subsequent S3 create/delete notifications, SQS invokes the
worker; it reconciles current S3 state rather than trusting event order, reuses
vectors for unchanged path+digest+embedding contract, and removes deleted notes.
The queue/worker must coalesce or serialize index publication to avoid competing
SQLite writers. A full rebuild is required when the model or chunking contract
changes. Bulk builds that exceed Lambda's measured limits use an on-demand
CodeBuild/Batch job, with the same publisher and no permanent compute instance.

The worker writes `notes(path,tier,sha256,source_revision)`,
`chunks(path,ordinal,text,vector)` and versioned metadata to a private SQLite
working file. It checkpoints/backups, validates row/vector counts and integrity,
uploads an immutable checksum-addressed snapshot plus manifest to the private
index bucket, then conditionally advances the DynamoDB active pointer. The
previous snapshot remains usable until that last step succeeds. No Markdown,
vector or private manifest enters Git, a Lambda ZIP or public CI artifacts.

For each `search_kb` invocation, the MCP Lambda validates the grant and pins one
active descriptor. `lexical` performs the local BM25-style token scoring,
including Chinese bigrams and filename terms. `vector` embeds the query with the
matching cloud model, then scores the stored normalized vectors by dot product
(cosine). `hybrid` combines both rankings using the local 0.25 lexical / 0.75
vector reciprocal-rank fusion and near-tie authority ordering. The first live
synthetic comparison found that the local fusion pushed a correct cross-language
vector top hit below rank three. The cloud rule therefore preserves vector rank
one within the hybrid top three while leaving the fused top hit untouched; this
is a measured quality adjustment, not an identical-ranking claim. Query embedding
is one managed inference call per semantic search; document embedding happens
only on initial or changed-note ingestion. Before returning any candidate,
recheck current grant, source existence/revision and policy. Fetch remains a
direct S3 read independent of index freshness.

The first candidate is Cohere Embed Multilingual v3 through Bedrock in Sydney:
`search_document` for chunks and `search_query` for queries. This is a candidate,
not consent to send private text. Pin the exact model ID, dimensions, input modes,
normalization, chunker, vector representation and region in `EmbeddingContract`.
Compare it on bilingual synthetic cases and approved private evaluation queries
against the local MCP before activating the private index. Cohere Embed v4 from
Sydney currently uses global cross-region routing, so its data boundary differs;
do not silently substitute it. Exact local bge-m3 rankings would require serving
the same encoder in the cloud instead of switching embedding spaces.

The published cloud index must cover the S3 Markdown corpus before calling this
like-for-like. Explicit acceptance requires lexical/vector/hybrid, default
hybrid, English/Chinese queries, source/authority metadata, safe direct fetch,
incremental refresh, deletion/revocation protection, and operation while the
Mac is offline. Record actual differences in ranking; function parity is not a
promise of identical scores from different embedding models.

Local oMLX can instead poll approved work, download changed objects and publish
derived artifacts, but this hybrid option delays indexing while the Mac is
offline and does not solve query-time embedding availability. It is an optional
cost/privacy experiment, not the selected production availability path.

## Migration, cost and deployment sequence

1. Privately inventory the current authoritative cloud-synced corpus and index
   size; record complete downloads, revisions, attachments and resolvable links.
2. Implement/validate auth and read-only cloud serving using synthetic data.
3. Add policy-bound capture, expected-revision updates, human approval and
   recoverable audit/outbox behavior; then independent incremental indexing.
4. Review region, provider/model, full recurring-cost worksheet and a synthetic
   infrastructure change set. Authenticate through a scoped temporary profile;
   deployment access does not imply approval to transfer private content.
5. Rehearse migration against a private staging destination. Verify 100% of the
   frozen manifest and retrieval/link behavior. At cutover freeze old writers,
   reconcile final changes and designate one authoritative S3 namespace.
6. Keep a recoverable source export. A rollback must export/reconcile accepted
   post-cutover writes before re-enabling another writer. Do not blindly restore
   an old pointer and discard new knowledge.

Planning allowance: approximately USD 1–5/month for a small core service, not a
quote, approved spending limit or all-in estimate. Count regional compute and
HTTP requests, S3 data/requests/versions, DynamoDB including operation history,
SQS, secrets, logs, egress and backups. Add query/document embeddings, initial
re-embedding and optional synthesis separately. Account-wide free grants may be
shared/exhausted. Avoid required provisioned concurrency, paid warmers, NAT
gateways, load balancers and continuously provisioned databases/models by default;
any necessary networking/security exception needs an explicit revised estimate.

Use plain CloudFormation for the initial foundation, delivered through GitHub
Actions OIDC from the trusted branch. An administrator applies a separate
CloudFormation bootstrap for initial trust; routine infrastructure releases use
the pipeline rather than console operations. SAM can be considered for the later
application stack if useful. Separate
the bootstrap, deployer, provisioning and per-function runtime roles, constrain
PassRole and keep application OAuth unrelated to AWS deployment authority.
See [deployment-access.md](deployment-access.md). Later trusted CI uses OIDC;
untrusted PR jobs get synthetic fixtures and no deployment/data credentials.

## Project Structure

### Documentation (this feature)

```text
specs/006-cloud-kb-mcp/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── deployment-access.md
├── permission-verification.md
├── tasks.md
├── quickstart.md
├── contracts/mcp-tools.md
└── checklists/requirements.md
```

`tasks.md` records implementation slices and actual completion. Foundation
authoring/validation is separate from bootstrap, pipeline activation, deployment,
application readiness and migration.

### Source Code (existing and proposed)

```text
retrieval_experiment.py        existing local retrieval experiment
kb_mcp_server.py              existing read-only stdio adapter
tests/                        existing synthetic/unit checks
cloud_kb/                     proposed remote adapters, writer and workers
infra/                        authored CloudFormation foundation/bootstrap; later application stack
tools/                        proposed migration/export and operator commands
```

Keep the existing local contract usable. Cloud model/storage adapters have their
own explicit data permissions instead of weakening loopback-only local code.

## Complexity Tracking

No unapproved implementation exception is treated as accepted. OAuth with durable
state, concurrent write safety and snapshot publication are necessary complexity
for remote private writeback. Obsidian sync, a shared mutable filesystem,
multi-region active-active writes and always-on vector/model clusters are outside
the initial design. Validate the small-snapshot assumption before committing to it.
