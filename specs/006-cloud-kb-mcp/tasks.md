# Tasks: Cloud KB MCP and Learning Writeback

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts](contracts/mcp-tools.md).  
**Created**: 2026-10-17.  
**Current authorization**: Prove deployment permissions, deliver infrastructure
through a pipeline, and prove the MCP end to end with mock Markdown. The foundation
and first remote read adapter are authored. The full cloud proof remains active
and incomplete; local test doubles are not accepted as cloud deployment evidence.
Unchecked feature/migration tasks are not claimed completed by the mock slice.

## Phase 1: Setup

- [x] T001 Record scoped, read-only IAM permission evidence and simulation limitations in `specs/006-cloud-kb-mcp/permission-verification.md`.
- [x] T002 Create CloudFormation layout and review/deployment instructions in `infra/README.md` and the OIDC workflow in `.github/workflows/infra.yml`.

## Phase 2: Foundational infrastructure

**Goal**: A reviewable parameterized foundation template with private resources
and bounded runtime permissions. No public endpoint or model invocation yet.

- [x] T003 Define retained, encrypted, versioned private data/index/release buckets and secure-transport policies in `infra/foundation.template.json`.
- [x] T004 Define usage-based control storage, ingestion queue/DLQ and bounded logs in `infra/foundation.template.json`.
- [x] T005 Define separate bounded API/ingestion runtime roles in `infra/foundation.template.json` and scoped GitHub/provisioning trust in `infra/bootstrap.template.json`.
- [x] T006 Validate template parsing and AWS CloudFormation acceptance, recording the exact template digest and limits in `specs/006-cloud-kb-mcp/permission-verification.md`.
- [ ] T007 Apply the reviewed one-time trust bootstrap, configure GitHub role identifiers/activation, then deploy the approved foundation through `.github/workflows/infra.yml` after cost review.
- [x] T008 Establish maintained dependencies and private configuration boundaries for remote adapters in `cloud_kb/config.py` and `requirements-cloud.txt`.

**Activation status**: T007 awaits administrator confirmation of an approved
GitHub OIDC provider/setup; the current identity is denied provider operations.
See [permission-verification.md](permission-verification.md).

## Phase 3: US1 - Authenticated cross-client retrieval (P1)

**Independent acceptance**: Two authorized clients search/fetch 12 bilingual
synthetic cases while home devices are offline; invalid/revoked credentials fail.

- [ ] T009 [US1] Implement Google identity binding, durable OAuth state and per-client grants in `cloud_kb/auth.py`.
- [ ] T010 [US1] Implement private S3 direct fetch and current policy/tombstone checks in `cloud_kb/storage.py`.
- [ ] T011 [US1] Implement pinned snapshot retrieval and compatible query-embedding adapters in `cloud_kb/search.py`.
- [x] T012 [US1] Implement bounded stateless MCP HTTP routing around the core in `cloud_kb/api.py`.
- [x] T013 [US1] Define authenticated application functions, HTTP API integration, named secrets and limits in `infra/application.template.json`.
- [ ] T014 [US1] Record actual per-client authorization/restart/revocation and offline-device acceptance in `specs/006-cloud-kb-mcp/acceptance-results.md`.

## Phase 4: US2 - Controlled learning writeback (P1)

**Independent acceptance**: One client persists learning; another fetches its
revision immediately. Duplicate IDs, concurrent edits and self-approval fail safely.

- [ ] T015 [US2] Implement idempotent operations, conditional note writes and recoverable audit/outbox state in `cloud_kb/writer.py`.
- [ ] T016 [US2] Implement exact-content/base-revision owner review and configured proposal destinations in `cloud_kb/review.py`.
- [ ] T017 [US2] Expose capture/update/status under separate scopes in `cloud_kb/api.py`.
- [ ] T018 [US2] Record persistence/fetch, duplicate, conflict and canonical-review acceptance in `specs/006-cloud-kb-mcp/acceptance-results.md`.

## Phase 5: US3 - Independent ingestion (P1)

**Independent acceptance**: A one-note change reuses all unchanged document
vectors, late/duplicate jobs cannot replace a newer index, and failures retain serving.

- [ ] T019 [US3] Select an approved bilingual embedding contract and optional synthesis provider in `cloud_kb/embeddings.py` and `specs/006-cloud-kb-mcp/model-decision.md`.
- [ ] T020 [US3] Implement source-preserving extraction, policy-bound synthesis proposals and retryable ingestion in `cloud_kb/ingestion.py`.
- [ ] T021 [US3] Implement consistent SQLite backup publication, manifests, fenced activation and safe artifact cleanup in `cloud_kb/indexes.py`.
- [ ] T022 [US3] Configure bounded queue processing, publisher concurrency and failure handling in `infra/application.template.json`.
- [ ] T023 [US3] Record incremental, stale-event, deletion and corrupted-publication acceptance in `specs/006-cloud-kb-mcp/acceptance-results.md`.

## Phase 6: US4 - Affordable operation and migration (P2)

**Independent acceptance**: Reproduce a synthetic release, recover it, measure the
full budget and privately rehearse migration/cutover without losing later writes.

- [x] T024 [US4] Extend the foundation-only OIDC/provisioning scope for the authenticated application resources in `infra/bootstrap.template.json` after reviewing the new access boundary.
- [ ] T025 [US4] Implement inventory, migration, verified export/restore and cutover reconciliation in `tools/cloud_kb_migrate.py`.
- [ ] T026 [US4] Define bounded monitoring, DLQ/availability alarms and a full regional cost worksheet in `infra/operations.template.json` and `specs/006-cloud-kb-mcp/costs.md`.
- [ ] T027 [US4] Record synthetic rollout/restore checks and a private migration signoff reference in `specs/006-cloud-kb-mcp/acceptance-results.md` without committing private evidence.

## Phase 7: Cross-cutting delivery

- [ ] T028 Reconcile observed implementation status, supported clients and remaining limitations in `README.md` and `specs/006-cloud-kb-mcp/quickstart.md`.

## Current goal: cloud proof with mock Markdown

- [x] T029 Add the bilingual fixture and real loopback MCP search/fetch/access-failure checks in `tests/test_cloud_http.py` and `tests/fixtures/cloud-kb/`.
- [x] T030 Exercise repeated API Gateway/Lambda invocations and encrypted OAuth-store reconstruction in `tests/test_cloud_lambda.py` and `tests/test_cloud_auth.py`.
- [x] T031 Build a code-only Lambda release from hashed Linux wheels using `tools/build_cloud_release.py` and add the synthetic checks/build to `.github/workflows/infra.yml`.
- [x] T032 Provide bounded development-only mock seeding and a deployed OAuth client verifier in `tools/seed_mock_kb.py` and `tools/verify_cloud_mcp.py`; record local evidence and gaps in `specs/006-cloud-kb-mcp/mock-proof.md`.
- [ ] T033 Resolve approved OIDC/Google configuration, extend reviewed application deployment permissions, deploy through the pipeline, seed actual cloud mock objects/grant and pass the HTTPS Google-authenticated verifier; record release/run evidence in `specs/006-cloud-kb-mcp/mock-proof.md`.

T009–T011 have partial source implementations. Their complete
Google/live storage/model contracts remain unproven and their markers stay open.
T033 is the completion gate for the current goal; passing T029–T032 alone does
not satisfy it. T024 supplies its application provisioning scope; T007 supplies
the one-time trust bootstrap and foundation.

The 2026-10-18 extension includes the gated application deployment job and
`tools/deploy_cloud_app.py`, with synthetic orchestration tests. T013/T024 denote
authored, validated template/policy work; they do not claim AWS application
provisioning, real Google consent or the T033 proof has occurred.

## Dependencies and incremental delivery

- T001 precedes the conditional IaC work requested by the owner. T002–T006
  deliver the initial authored/validated foundation; T007 is separate execution.
- T008 precedes application stories. US1 supplies shared authentication/storage
  boundaries; US2 and US3 reuse them. Indexing publication integrates with writes
  through the operation/outbox contract. US4 cutover waits for all three.
- MVP serving is US1 with synthetic data. Add controlled writeback, then independent
  refresh, then private migration; do not label foundation resources a working MCP.
- Parallel opportunities after shared contracts are stable: storage vs auth files
  in US1; owner review vs writer UI in US2; model evaluation vs extraction in US3;
  monitoring/cost documentation vs migration-tool development in US4. These are
  planning examples, not authorization to spawn agents or execute later phases now.
- The later mock-proof goal explicitly authorises implementation verification.
  New synthetic adapter checks are recorded in `mock-proof.md`; existing full
  feature acceptance records remain open until their actual scope is exercised.
