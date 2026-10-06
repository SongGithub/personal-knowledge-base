# Tasks: Shared Local KB Retrieval

**Input**: [spec.md](spec.md), [plan.md](plan.md)

**Status**: Complete, 2026-10-06. Verified by `python3 -m unittest discover -s tests`
(14 tests, all passing).

**Format**: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story from [spec.md](spec.md)

## Phase 1: Setup

- [x] T001 Record owner approval of the constitution 0.4.0 amendment for this
  feature by requesting implementation; whole-constitution ratification
  remains pending.
- [x] T002 Write the implementation plan and constitution check in
  [plan.md](plan.md).

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The vendor-neutral retrieval core that every user story depends on.

- [x] T003 [P] Refactor retrieval in `retrieval_experiment.py` into a
  vendor-neutral core with stable search and note-fetch operations.
- [x] T004 [P] Keep authority tiers and deterministic path tie-breaks separate
  from similarity in `retrieval_experiment.py`.
- [x] T005 Keep the SQLite index local and rebuildable, outside the vault and
  repository, in `kb_mcp_server.py`.

## Phase 3: User Story 1 - Owner runs a local retrieval service (P1) 🎯 MVP

**Goal**: The owner runs a local service over the configured vault and index
without changing canonical Markdown.

**Independent test**: Build the index, search through the service, and confirm
no Markdown file changed.

- [x] T006 [US1] Implement the vendor-neutral `KBService` facade in
  `kb_mcp_server.py`.
- [x] T007 [US1] Open the index read-only (`mode=ro`) and never rebuild the
  index or embeddings during a request in `kb_mcp_server.py`.
- [x] T008 [US1] Report a missing or stale index with the documented rebuild
  action instead of scanning a different vault in `kb_mcp_server.py`.
- [x] T009 [P] [US1] Reject a vault or index location inside the public
  repository in `kb_mcp_server.py`.

**Checkpoint**: The owner can query the local index without touching Markdown.

## Phase 4: User Story 2 - Client searches and fetches notes (P2)

**Goal**: Any supported client searches and fetches through one stable,
documented interface and receives paths, authority tiers, and excerpts.

**Independent test**: Run the same query through the CLI and the MCP adapter and
compare ordered paths, tiers, and excerpts.

- [x] T010 [US2] Define the `search_kb` and `fetch_note` tool schemas with
  read-only annotations in `kb_mcp_server.py`.
- [x] T011 [US2] Return vault-relative path, authority tier, excerpt, and
  provenance from search in `kb_mcp_server.py`.
- [x] T012 [US2] Implement safe vault-relative note fetch and reject traversal,
  absolute, and non-Markdown paths in `kb_mcp_server.py`.
- [x] T013 [US2] Reject unknown tool names and unknown arguments in
  `kb_mcp_server.py`.
- [x] T014 [P] [US2] Add CLI/service parity, excerpt, and traversal tests in
  `tests/test_kb_mcp_server.py`.

**Checkpoint**: CLI and MCP return the same ordered results for one query.

## Phase 5: User Story 3 - Connect or replace a client adapter (P3)

**Goal**: An adapter can be connected or replaced without changing the index
schema, ranking policy, or vault format.

**Independent test**: Remove the adapter and confirm the index and ranking still
work unchanged.

- [x] T015 [US3] Keep MCP protocol handling in `MCPProtocol` as an adapter
  around `KBService` in `kb_mcp_server.py`.
- [x] T016 [US3] Serve stdio JSON-RPC without leaking non-protocol output in
  `kb_mcp_server.py`.
- [x] T017 [P] [US3] Test initialize, tools/list, and notification handling in
  `tests/test_kb_mcp_server.py`.

## Phase 6: User Story 4 - Local content and hosted-client disclosure (P3)

**Goal**: Retrieval stays local for local clients; hosted-client excerpt
disclosure is explicit before enabling a hosted adapter.

**Independent test**: Confirm the service sends nothing off-loopback and that
the guide states what a hosted client receives.

- [x] T018 [US4] Restrict embeddings to a loopback endpoint in
  `retrieval_experiment.py`.
- [x] T019 [US4] Expose only read-only tools; no arbitrary SQL, filesystem, or
  write tools in `kb_mcp_server.py`.
- [x] T020 [US4] Document hosted-client disclosure and keep the ChatGPT adapter
  out of the retrieval core in `docs/openclaw-kb-connection.md`.

## Phase 7: Polish and verification

- [x] T021 [P] Document OpenClaw setup, probe, policy, rebuild, and
  troubleshooting in `docs/openclaw-kb-connection.md`.
- [x] T022 [P] Keep private paths, contents, indexes, embeddings, and real
  benchmark cases out of Git via `.gitignore`.
- [x] T023 Verify the live OpenClaw connection against synthetic data, and
  confirm private data and the index remain local and ignored.
- [x] T024 Run `python3 -m unittest discover -s tests` and record the result.

## Dependencies & Execution Order

- Setup (Phase 1) has no dependencies.
- Foundational (Phase 2) depends on Setup and blocks every user story.
- US1 (P1) is the MVP. US2-US4 depend on Phase 2 and the US1 service facade.
- Polish (Phase 7) depends on all user stories.

## Notes

- Markdown stays canonical; the SQLite index is disposable and rebuildable.
- ChatGPT connectivity remains a separate, unimplemented adapter.
- Tests and committed fixtures are synthetic only.
