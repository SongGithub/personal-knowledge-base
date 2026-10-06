# Feature Specification: Shared Local KB Retrieval

**Status**: Approved for implementation, 2026-10-05. **Constitution**: 0.4.0
draft amendment (owner-approved for this feature; overall constitution
ratification remains pending).

## Need

The user wants ChatGPT, Codex, and OpenClaw to find the same knowledge in the
private Obsidian `KB` vault. They need one authority-aware retrieval policy and
local index, without making the retrieval engine dependent on a single AI
vendor. The current retrieval experiment is a CLI, not a server, and does not
yet expose a supported client interface.

## User stories and acceptance

1. As the vault owner, I can run a local retrieval service that reads the
   configured Markdown vault and rebuildable SQLite index without changing
   canonical Markdown.
2. As any supported assistant client, I can search and fetch notes through the
   same stable, documented retrieval interface and receive paths, authority
   tiers, and relevant excerpts.
3. As the vault owner, I can connect or replace a client adapter without
   changing the index schema, ranking policy, or canonical vault format.
4. As the vault owner, I can keep all content local for local clients. For a
   hosted client, I can see that requested excerpts enter that provider's
   conversation context before enabling the connection.

### Acceptance scenarios

- Given a configured local vault and a built index, when OpenClaw searches a
  query, then it uses the same deterministic authority-aware ranking as the
  local CLI and returns note-relative paths and excerpts.
- Given that the index is absent or out of date, when a client requests
  search, then the service reports the condition and the documented refresh
  action. A normal refresh is incremental and re-embeds only added or changed
  notes; a compatibility-breaking change (embedding model, chunker, or index
  schema) or a corrupt index requires a full rebuild. The service does not
  silently scan a different vault or create a hosted index.
- Given a canonical note and a semantically similar archive note, when they
  compete for a result, then the service applies the specified authority policy
  and deterministic path tie-break.
- Given a hosted client adapter, when a search result is returned, then only
  the requested result excerpts are sent to that client; the full vault and
  SQLite file are not uploaded by the retrieval service.
- Given an adapter for one vendor is removed, when another supported adapter
  connects, then the index and retrieval policy remain usable without migration.

## Requirements

- **FR-001**: Markdown in the configurable Obsidian vault MUST remain the
  canonical source of truth. The service and clients MUST NOT edit it during
  retrieval.
- **FR-002**: The service MUST use a disposable, rebuildable SQLite index on
  local storage outside the vault and repository. It MUST NOT require a hosted
  vector database or network-mounted SQLite file.
- **FR-003**: The retrieval core MUST expose stable search and note-fetch
  operations independent of any AI vendor. MCP is the preferred open tool
  protocol adapter for assistant clients; its protocol implementation MUST be
  replaceable without changing retrieval logic.
- **FR-004**: The first client adapter MUST support OpenClaw using a local
  process/stdio MCP connection. It MUST not require OpenClaw to open SQLite
  directly or know its schema.
- **FR-005**: Search MUST use the same documented lexical, vector, and authority
  behavior for every client. Authority MUST be separate from similarity, with
  canonical/binding, verified, ordinary, archive/source, and
  draft/unverified tiers and deterministic tie-breaking.
- **FR-006**: Search results MUST include vault-relative note paths, excerpts,
  authority tier, and enough provenance to let the client cite the source.
  Note fetch MUST accept only a vault-relative path and reject traversal beyond
  the configured vault.
- **FR-007**: The service MUST expose only read-only retrieval operations by
  default. It MUST NOT expose arbitrary SQL, filesystem access, or write tools.
- **FR-008**: Indexing and embeddings MUST remain local. External embedding
  endpoints MUST NOT receive private content without explicit approval.
- **FR-009**: Client connectivity MUST be isolated in adapters. ChatGPT-specific
  authentication, tunneling, or connector setup MUST NOT be embedded in the
  retrieval core or SQLite schema.
- **FR-010**: A hosted client connection MUST disclose that requested note
  excerpts are sent into that provider's conversation context. The full vault
  and index MUST remain local unless the owner separately chooses otherwise.
- **FR-011**: OpenClaw instructions MUST document setup, least-privilege tool
  exposure, a live connection check, rebuild/troubleshooting steps, and the
  current service availability status. They MUST not include a private vault
  path or credentials.
- **FR-012**: The public repository MUST contain only code, specifications, and
  synthetic fixtures. Private paths, note contents, index files, embeddings,
  and real benchmark cases/reports MUST stay outside Git.
- **FR-013**: The index refresh path MUST be incremental. Unchanged notes MUST
  keep their existing vectors, and only added or changed notes MUST be
  re-embedded; a full rebuild MUST be limited to a compatibility change
  (embedding model, chunker, or index schema) or a corrupt index. The service
  MUST continue to use the same SQLite index and retrieval policy.

## Out of scope

- Hosted vector databases or hosted indexing.
- Arbitrary client access to the SQLite file.
- Editing or generating canonical notes through the retrieval interface.
- Publicly exposing an unauthenticated HTTP endpoint.
- Implementing a ChatGPT-specific adapter in the retrieval core.

## Success criteria

- OpenClaw can pass a live health/probe check and retrieve a synthetic fixture
  through the local MCP adapter without direct SQLite access.
- Equivalent queries through the CLI and MCP adapter return the same ordered
  paths, tiers, and excerpts.
- A traversal attempt through note fetch is rejected; write and arbitrary SQL
  operations are not exposed.
- Removing or changing the OpenClaw adapter does not require rebuilding or
  migrating the retrieval database.
- The OpenClaw guide accurately distinguishes planned service behavior from
  commands that are currently available.
