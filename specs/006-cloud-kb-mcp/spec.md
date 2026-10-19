# Feature Specification: Cloud KB MCP and Learning Writeback

**Feature context**: `006-cloud-kb-mcp`; independent of the current Git branch.  
**Created**: 2026-10-17  
**Status**: Draft requirements and design for review; not deployed or migrated.  
**Input**: Give compatible AI clients shared authenticated knowledge access and
learning writeback using the owner's Google identity. Prefer managed
availability and low recurring cost for occasional use, accepting cold starts.
The current vault is cloud-synced; the owner accepts migration to private cloud
storage if useful. Obsidian is not used for viewing/editing and must not be a
production dependency. Explain ingestion, embeddings, persistent indexing and
temporary deployment access.

## Decisions, provenance and scope

Owner statements recorded on 2026-10-17: occasional use; latency can be traded
for lower cost; managed availability matters; Google identity is required;
multiple authorized AI clients should read and write learning; the existing
cloud-synced knowledge may migrate; Obsidian is not a required interface.

The assistant proposes AWS usage-based hosting, an authoritative S3 store and
independent embedding generation in [plan.md](plan.md). These are recorded
design choices, not completed implementation, an approved bill, migration
cutover or consent to send private content to an unspecified embedding provider.
The existing cloud-synced store remains authoritative until cutover is verified.

This feature supersedes the historical feature 005 NAS-hosting proposal, which
remains separate unpublished planning work. The local retrieval experiment and
[003](../003-shared-kb-retrieval/spec.md) remain historical implementation
evidence. This feature adds a separate authenticated write boundary; read grants
do not acquire write privileges. Public demonstrations use synthetic notes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Retrieve from different AI clients (Priority: P1)

The owner signs in with Google and grants each compatible client access to
search and fetch private evidence, including while home machines are offline.

**Why this priority**: Shared knowledge must be useful and private across clients.

**Independent Test**: Two clients retrieve a synthetic corpus with home devices
offline; unrelated, expired and revoked identities are denied.

**Acceptance Scenarios**:

1. **Given** an approved owner/client grant, **when** either client searches and
   fetches a result, **then** it receives permitted evidence with source identity,
   authority tier and revision/freshness information.
2. **Given** another Google account, invalid audience, missing scope or revoked
   grant, **when** a request is made, **then** no private paths or content leak.
3. **Given** the Mac, NAS and Obsidian are offline for 24 hours, **when** retrieval
   runs, **then** it requires no calls to those devices.
4. **Given** an incompatible client surface, **when** setup is attempted, **then**
   it is reported unsupported rather than claiming universal client access.

### User Story 2 - Write learning and retrieve it elsewhere (Priority: P1)

An authorized AI captures useful learning with provenance; another client can
fetch the saved revision immediately and search it after indexing completes.

**Why this priority**: Knowledge should compound across conversations and vendors.

**Independent Test**: Client A saves a synthetic learning; client B fetches and
then searches it; retries, stale updates and unauthorized changes are exercised.

**Acceptance Scenarios**:

1. **Given** a capture grant and configured permitted destination, **when** a
   learning is saved, **then** its receipt identifies durable Markdown, revision,
   origin, date and separate persistence/indexing states.
2. **Given** indexing is pending or failed, **when** the saved path is fetched,
   **then** the authorized saved revision remains readable independently.
3. **Given** the same operation ID and identical request, **when** retried,
   **then** it returns the same logical change; changed content under that ID is
   rejected and an update against an old revision cannot overwrite new content.
4. **Given** a proposed canonical Wiki or navigation change, **when** an AI
   submits it, **then** it waits for the owner's approval of exact revisions and
   content; the proposing AI cannot approve it.

### User Story 3 - Ingest without opening an app (Priority: P1)

Sources and learning are processed in the background. Search uses a prepared
index; opening a client does not trigger corpus-wide indexing.

**Why this priority**: The owner wants knowledge access without desktop startup work.

**Independent Test**: Add/change/delete synthetic notes; interrupt processing and
deliver duplicate or out-of-order events; retain a usable prior index.

**Acceptance Scenarios**:

1. **Given** one changed note and a compatible model, **when** indexing runs,
   **then** unchanged document embeddings are reused and progress is observable.
2. **Given** a new source needing synthesis, **when** it is ingested, **then**
   source preservation, proposed learning and embedding/indexing have distinct
   statuses; generating vectors alone is not reported as knowledge synthesis.
3. **Given** a failed job or incompatible index, **when** search runs, **then**
   it uses the last valid index with explicit freshness or returns a clear error.
4. **Given** a deletion or reduced access, **when** old index candidates appear,
   **then** current authorization and source existence checks prevent disclosure.

### User Story 4 - Operate affordably and recover safely (Priority: P2)

The owner can operate and migrate the service with predictable spending,
temporary deployment authority, reversible data changes and independent releases.

**Why this priority**: Occasional use must not require continuously paid servers.

**Independent Test**: Reproduce a synthetic deployment, verify idle resource
settings, exercise rollback/restore and confirm restricted deployment permissions.

**Acceptance Scenarios**:

1. **Given** no traffic or ingestion work, **when** the system is idle, **then**
   it has no required continuously billed application/model instances; persistent
   storage, logs and secrets remain explicitly accounted for.
2. **Given** an authenticated temporary deployer, **when** deploying this project,
   **then** only approved resources and service roles are accessible; credentials
   do not enter chat, Git, images or public CI artifacts.
3. **Given** a migration rehearsal, **when** sources, links, attachments, versions
   and representative retrieval are verified, **then** a reviewable cutover and
   rollback record can designate exactly one authoritative writer.
4. **Given** a bad release or interrupted index publication, **when** recovered,
   **then** prior compatible serving data remains usable and accepted writes are
   neither lost nor falsely reported indexed.

### Edge Cases

- A write response is lost after the note was persisted; replay must reconcile it.
- Two clients update the same note, rename it, or retry an approval after its base changed.
- A duplicate event arrives after a newer note revision was indexed.
- A deleted or newly restricted note exists in a cached search snapshot.
- The model, dimensions, tokenizer, normalization or chunking contract changes.
- An embedding provider is unavailable, throttled, unapproved or withdrawn.
- An upload contains a partial source, traversal path, forged authority or prompt injection.
- OAuth signing keys rotate, grants are revoked, or the service restarts during consent.
- A database snapshot is incomplete, a job times out, or two publishers race.
- Migration changes cloud authority while another process still writes to the old store.
- Deployment credentials expire or a CI event comes from an untrusted fork.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: One owner-configured private Markdown store MUST be authoritative;
  knowledge MUST remain exportable with the existing folders, links, source
  evidence and attachments. Obsidian, iCloud and home devices MUST NOT be required
  by the target production read/write and embedding paths after cutover.
- **FR-002**: Compatible authorized clients MUST share bounded search/fetch and
  permitted learning capture/update operations, without receiving infrastructure
  credentials or unrestricted filesystem/database access.
- **FR-003**: Google-backed authentication MUST validate the stable owner subject;
  successful login alone MUST NOT grant knowledge access. Each call MUST enforce
  client scopes, path policy, expiry and revocation in the backend.
- **FR-004**: Owner binding, client grants, revocations and authorization secrets
  MUST be durable and independent of disposable search indexes. Rebuilding an
  index MUST NOT change permissions. Revocation MUST apply within five minutes.
- **FR-005**: Writes MUST include origin/date, evidence links and explicit AI
  inference labels where applicable. Capture destinations MUST follow the owner's
  taxonomy and be configured before use; duplicate search MUST precede creation.
- **FR-006**: Mutations MUST enforce operation IDs, expected revisions, recoverable
  history and bounded permitted destinations. A successful persistence receipt
  MUST denote durable Markdown, not merely an enqueue acknowledgment.
- **FR-007**: Canonical Wiki/navigation changes MUST require owner approval bound
  to exact proposed content and base revisions. AI credentials MUST NOT approve
  their own changes. Approved mutations MUST have a reconcilable activity record.
- **FR-008**: Saved authorized notes MUST be fetchable while indexing is pending.
  Persistence, synthesis review, indexing and failure MUST be separately visible.
- **FR-009**: Ingestion MUST distinguish source extraction, optional synthesis,
  owner review and embedding/index publication. Imported sources MUST be preserved;
  embedding generation MUST NOT be described as fact verification or synthesis.
- **FR-010**: Index refresh MUST run independently of client startup and reuse
  unchanged embeddings under a versioned compatibility contract. Contract changes
  MUST build and validate a replacement before activation.
- **FR-011**: Indexes MUST be reproducible derived artifacts. Publication MUST
  activate only a complete validated snapshot; readers MUST never observe a
  partially written database or combine incompatible embedding contracts.
- **FR-012**: Search MUST expose freshness and recheck access/existence against
  current policy/content. Old cached results MUST NOT bypass deletions or grants.
- **FR-013**: Production query embeddings and ingestion MUST work without the Mac.
  External private-content model calls MUST wait for provider/model approval and
  a recorded data boundary. Model replacement MUST compare bilingual retrieval
  quality and use compatible document/query embeddings.
- **FR-013a**: Cloud `search_kb` MUST accept `lexical`, `vector`, and `hybrid`,
  default to `hybrid`, and preserve the local tokenizer/chunker, lexical scoring,
  reciprocal-rank fusion weights and near-tie authority rule unless a measured
  bilingual comparison justifies a documented change. The initial cloud index
  MUST cover the migrated S3 Markdown corpus before production parity is claimed.
  Query embedding runs during semantic MCP searches; document embedding runs
  during independent initial/incremental ingestion. Index and query must pin the
  same embedding contract. A changed model requires a separate full re-embedding.
- **FR-013b**: Pull-request CI MUST check deterministic tokenization, vector
  validation, incremental reuse, deletion safety and fusion on synthetic data.
  The trusted deployment pipeline MUST invoke the selected real embedding model
  on a versioned synthetic English/Chinese benchmark and stop deployment if its
  documented quality floor fails. CI MUST NOT load the private KB or publish
  private paths, text, vectors or benchmark queries.
- **FR-014**: Deployment MUST use reviewable declarative configuration and scoped
  temporary credentials, with separate human/deployer, provisioning, runtime and
  application identities. Code release MUST NOT bundle private knowledge.
- **FR-015**: Public examples, Git and untrusted CI MUST contain synthetic data
  only. All private corpus data, vectors, identifiers and credentials MUST remain
  in protected runtime/private storage and out of public logs/artifacts.
- **FR-016**: Idle cost, usage assumptions, storage, model calls, logging, secrets
  and recovery costs MUST be reported separately. Cold starts are acceptable
  within client timeouts; no continuously paid model/application instance is
  required by default. Availability claims MUST cover dependencies and distinguish
  regional resilience from region-wide disaster recovery.
- **FR-017**: Migration MUST be rehearsed and verified before cutover, preserve
  original sources and links, prevent competing authorities, and include a
  recoverable export and explicit rollback/reconciliation of post-cutover writes.

### Key Entities

- **Knowledge object/revision**: Path, content, digest, authority and immutable revision.
- **Learning change**: Client operation, origin, evidence, base revision, proposal,
  approval, persistence, audit and indexing statuses.
- **Owner/client grant**: Verified subject, client identity, scopes, paths, expiry,
  revocation and separately held owner-approval authority.
- **Embedding contract**: Model version, input processing, dimensions and normalization.
- **Index snapshot**: Identifiable derived chunks/vectors, source revisions,
  compatibility contract, checksum and publication time.
- **Migration/release record**: Source manifest, target verification, authority
  designation, release identity and recovery procedure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Two distinct authorized AI clients complete the same 12 bilingual
  synthetic retrieval scenarios with home devices offline for 24 hours; every
  result has permitted source/revision evidence.
- **SC-002**: Client B fetches every successful synthetic learning saved by client A
  immediately after its persistence receipt; a 20-change fixture becomes searchable
  within five minutes under normal provider availability. Failures remain visible.
- **SC-003**: All defined invalid-identity, revoked, stale-revision, duplicate and
  unapproved-canonical-change cases prevent disclosure or unintended mutation;
  revoked grants stop working within five minutes.
- **SC-004**: In a 100-note fixture, changing one note recomputes no unchanged
  document embeddings; corruption/interruption preserves a usable prior index.
- **SC-005**: Proposed acceptance targets are 95th-percentile warm retrieval below
  five seconds and cold retrieval below 25 seconds on the declared small workload,
  including query embeddings. These are targets, not observed results.
- **SC-006**: A monthly regional availability objective of 99.9% is documented and
  measured end to end after deployment; cold responses within the response budget
  count as available. Provider SLAs and a short rehearsal do not prove this objective.
- **SC-007**: A migration rehearsal reconciles 100% of the frozen source manifest,
  attachments and resolvable local links; rollback preserves accepted later writes.
- **SC-008**: A cost worksheet for the declared occasional workload has no required
  continuously paid application/model instances and states total projected charges
  and exclusions before deployment. A failed release recovers within five minutes
  in the synthetic rehearsal without losing durable accepted changes.

## Assumptions and dependencies

- One owner; client compatibility is demonstrated per surface. Enterprise tenants,
  HA/IoT integration and bidirectional desktop editing are outside this feature.
- Numeric latency, availability, indexing and budget examples are proposed
  engineering targets, not additional owner statements or verified guarantees.
- The current cloud-synced vault is not assumed absent when its local copy is
  unavailable. Migration selects an explicit source snapshot and authority cutover.
- A maintained MCP authorization implementation, approved cloud account/region,
  owner Google application, permitted capture destination and embedding provider
  configuration are prerequisites to production, not secrets committed here.
- Knowledge ingestion initially accepts Markdown/text and existing attachments.
  Broad OCR, audiovisual transcription and autonomous source verification are
  separate features. Historical public read-only demos remain read-only.
