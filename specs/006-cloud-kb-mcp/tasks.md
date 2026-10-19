# Tasks: Cloud KB MCP and Learning Writeback

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts](contracts/mcp-tools.md).  
**Created**: 2026-10-17.  
**Current authorization**: Prove deployment permissions, deliver infrastructure
through a pipeline, and prove the MCP end to end with mock Markdown. The foundation
and protected mock MCP are deployed through CodeBuild. The single-client Google-authenticated mock read proof passed on 2026-10-19;
local test doubles are not accepted as cloud deployment evidence.
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
- [x] T007 Apply the reviewed one-time trust bootstrap and deploy the approved foundation through the permitted pipeline after cost review. The AWS-native CodeBuild route was used; GitHub OIDC activation remains optional and unconfigured.
- [x] T008 Establish maintained dependencies and private configuration boundaries for remote adapters in `cloud_kb/config.py` and `requirements-cloud.txt`.

**Activation status**: The native bootstrap and CodeBuild-deployed foundation
exist. IAM OIDC provider operations remain denied and were not needed for this
delivery route. See [permission-verification.md](permission-verification.md).

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

- [x] T015 [US2] Implement an idempotent new-note capture operation with conditional S3 creation, durable status, provenance, retry recovery and S3-triggered indexing in `cloud_kb/writer.py`.
- [ ] T016 [US2] Implement exact-content/base-revision owner review and configured proposal destinations in `cloud_kb/review.py`.
- [ ] T017 [US2] Expose capture/update/status under separate scopes in `cloud_kb/api.py`.
- [ ] T018 [US2] Record deployed persistence/fetch, duplicate, conflict and canonical-review acceptance in `specs/006-cloud-kb-mcp/acceptance-results.md`.

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
- [x] T031 Build a code-only Lambda release from hashed Linux wheels using `tools/build_cloud_release.py`, verify reproducible ZIP content in `tests/test_cloud_build.py`, and add synthetic checks/build to `.github/workflows/infra.yml`.
- [x] T032 Provide bounded development-only mock seeding and a deployed OAuth client verifier in `tools/seed_mock_kb.py` and `tools/verify_cloud_mcp.py`; record local evidence and gaps in `specs/006-cloud-kb-mcp/mock-proof.md`.
- [x] T033 Configure approved Google identity/client access, deploy through the permitted pipeline, seed actual cloud mock objects/grant and pass the HTTPS Google-authenticated verifier; record release/run evidence in `specs/006-cloud-kb-mcp/mock-proof.md`.

- [x] T034 Define an AWS-native CodeBuild alternative with exact service trust and source commit in `infra/native-pipeline.template.json`, `infra/buildspec.yml` and `tools/bootstrap_native_pipeline.py`; no IAM identity-provider operation is required.
- [x] T035 Apply the approved native bootstrap, run the pinned managed build and verify actual stack/build/HTTP/mock-storage state. Google configuration, verifier consent and authenticated retrieval passed under T033.

T009–T011 have partial source implementations. Their complete
two-client, full storage-policy and model contracts remain unproven; their markers stay open.
T033 is the completion gate for the current goal; passing T029–T032 alone does
not satisfy it. T024 supplies its application provisioning scope; T007 supplies
the one-time trust bootstrap and foundation.

The current native route may satisfy T007/T033 without GitHub OIDC when the
organisation permits CodeBuild instead. It must still satisfy the full Google,
actual storage and authenticated read proof; replacing the deployment runner
does not reduce those requirements.

The 2026-10-18 extension includes the gated application deployment job and
`tools/deploy_cloud_app.py`, with synthetic orchestration tests. T013/T024 denote
authored, validated template/policy work. T035 records the actual managed AWS
provisioning; real Google consent and the T033 proof passed on 2026-10-19.

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

- [x] T036 Create the owner-approved dedicated Google client, verify the stable owner identity, store credentials in AWS Secrets Manager and deploy the real owner binding through CodeBuild (2026-10-19). T033 was subsequently completed by the separate authenticated verifier.

## Current goal: cloud retrieval parity with the local MCP

- [x] T037 [US1] Implement a versioned cloud snapshot reader with the local lexical, vector and hybrid ranking contract and default hybrid in `cloud_kb/search.py` and `cloud_kb/api.py`.
- [x] T038 [US3] Implement the approved Bedrock document/query embedding adapter and explicit compatibility metadata in `cloud_kb/embeddings.py` and `specs/006-cloud-kb-mcp/model-decision.md`.
- [x] T039 [US3] Implement S3 Markdown inventory, changed-chunk reuse, deletion reconciliation, consistent SQLite publication and conditional active-pointer update in `cloud_kb/ingestion.py`.
- [x] T040 [US3] Connect S3 notifications, SQS, ingestion Lambda/role and scoped Bedrock invocation through `infra/foundation.template.json` and `infra/application.template.json` (deployed 2026-10-19).
- [x] T041 [US3] Add a one-time private bulk index build through the reviewed pipeline and synthetic bilingual parity checks, then activate only after user-approved provider/data boundary and record evidence in `specs/006-cloud-kb-mcp/acceptance-results.md` (deployed 2026-10-19).
- [ ] T042 [US1] Exercise deployed authenticated lexical/vector/hybrid search and fetch, freshness/deletion safety and Mac-independent serving; record actual client and bilingual results in `specs/006-cloud-kb-mcp/acceptance-results.md`.
- [x] T043 [US3] Add deterministic hybrid/index checks to `.github/workflows/infra.yml` and a real synthetic bilingual Bedrock quality gate before deployment in `infra/buildspec.yml` and `tools/benchmark_cloud_embeddings.py`.
- [x] T044 [US1] Compare lexical, pure-vector and default hybrid on a versioned bilingual/exact synthetic fixture when model or ranking configuration changes. Run deterministic comparison checks in GitHub PR CI and the real model/default-winner gate in trusted CodeBuild; record the observed fixture winner in `model-decision.md`.
- [ ] T045 [US1] Choose and verify the deployed default after the v2 fixture found vector ahead of hybrid on top-one retrieval. Keep the default-winner gate enforced for subsequent model/ranking releases.
- [x] T046 [US1] Extend the live comparison to 33 synthetic queries across paraphrase, near-collision, exact identifier and cross-language retrieval; verify authorization filtering, stale/deleted sources, corrupted snapshots, provider-outage lexical access and deployed-index latency. Record aggregate evidence and the provisional default recommendation in `model-decision.md` (2026-10-19).
- [ ] T047 [US1] Build a private, owner-judged 20–30-query relevance set, fix the cross-language fusion miss, and rerun the live default-winner gate before changing the deployed strategy. Add a no-answer/abstention contract if it is required for client behavior.
- [x] T048 [US2] Add synthetic `capture_learning` and `get_change_status` MCP tools with a separate `kb:capture` scope; persist raw, unverified Markdown only under granted `Ideas/` prefixes and restrict runtime S3 PutObject permission to that tree.
- [ ] T049 [US2] Deploy writeback through CodeBuild, authorize a named client with a bounded owner grant, and verify real S3 persistence, immediate cross-client fetch, background indexing, retry behavior and denial of writes outside the exact approved capture prefix, including canonical content.
- [x] T050 [US2] Correct local capture retry handling, lexical checks across embedding-contract changes, complete UTF-8 size bounds, snapshot-based change status, and support for the approved `Resources/_Review/AI Learning/` prefix and up-to-90-day grants. Record synthetic evidence and release boundaries in `writeback-local-handoff.md` (2026-10-20; not deployed).
- [ ] T051 [US2] Implement an authorised, recoverable `Wiki/Activity Log.md` append. Until then, report `activity_audit: pending` separately from the recorded DynamoDB operation. Existing capture-only approval does not authorise editing that log.
- [x] T052 [US2] Implement the disabled-by-default local activity-log component, conditional append/readback, idempotent capture retry recovery and read-only status reporting. Add synthetic conflict/crash/denial/configuration checks to both CI runners. T051 remains open for separate authorisation, exact-path IAM, activation and live acceptance.

T037–T042 refine T011 and T019–T023. Complete their parent markers only when
their full original scope, including approval and deployed acceptance, is met.
