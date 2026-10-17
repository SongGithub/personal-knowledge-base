# Mock Markdown end-to-end proof

**Goal**: Prove the cloud MCP is up end to end using a synthetic KB Markdown file.
**Observed**: 2026-10-17; pipeline extension 2026-10-18. **Status**: incomplete. Local HTTP and Lambda adapter
checks passed; there is no deployed cloud service or successful Google login yet.
The goal has not been reduced to the local checks below.

## Current evidence

| Requirement | Evidence | Result |
|---|---|---|
| MCP client speaks HTTP to the implementation | Maintained FastMCP client connected over a real temporary loopback socket, discovered tools, searched and fetched the exact bilingual fixture | Local layer passed |
| Correct Markdown/revision returned | Fetched UTF-8 content and SHA-256 matched `tests/fixtures/cloud-kb/Resources/MCP Demo/Mock orchard.md`; returned revision matched the simulated S3 response | Passed with simulated AWS |
| Authentication and grants cannot be skipped | Missing/invalid/expired/wrong-audience/missing-scope tokens, different owner, ungranted/traversal paths, revoked grant and hostile Host/Origin were rejected | Passed with synthetic signer/grants |
| OAuth state is durable and encrypted | A new adapter instance recovered encrypted state from the test table; expired records were rejected independently of physical TTL deletion | Adapter checks passed; real DynamoDB not exercised |
| Lambda cold/warm compatibility | Repeated real Mangum invocations with API Gateway v2 events, including a legacy `2025-11-25` initialize/tools-list sequence | Local adapter passed |
| Mock publisher preserves existing authority | Conditional immutable object writes; refused an active index without `SyntheticOnly=true` before any write | Local checks passed; not run on AWS |
| Cloud-compatible release artifact | Hashed Linux CPython 3.12 x86_64 wheels installed and code-only ZIP built; 77.3 MiB unpacked; no fixture/vault/credential/index files included | Packaging passed; Linux runtime execution pending |
| Dependency review | 75 locked runtime distributions audited; zero known advisories returned | Passed at the time of audit; not a security guarantee |
| Reviewable infrastructure | Latest bootstrap/foundation/application accepted by AWS `ValidateTemplate` and pinned lint; 5/13/5 declared resources | Structure passed; no resources created |
| Infrastructure deployment through pipeline | Local workflow extended with synthetic checks/build; live GitHub workflow list was empty; foundation stack was absent | Pending |
| Actual private S3 fixture/index and DynamoDB records | No uploads/seed operations performed | Pending |
| Google identity and actual owner/client grant | Google OAuth web-client/secret/owner binding and registered callbacks not configured | Pending |
| Deployed HTTPS client search/fetch | No deployed URL exists to probe | Pending |

The local HTTP run used SDK response stubs for S3, a test table and an ephemeral
RSA signer. It did **not** call Google, real S3/DynamoDB, home devices, the private
vault, oMLX or an embedding provider. Test doubles cannot prove those integrations.
The HTTP test server is stopped after verification; no persistent local service
is claimed to be running.

## Reproduce the local checks

Use an isolated Python environment and install public binary dependencies:

```sh
python3 -m venv /absolute/temporary/path/pkb-cloud
/absolute/temporary/path/pkb-cloud/bin/python -m pip install --only-binary=:all: -r requirements-cloud-test.txt
/absolute/temporary/path/pkb-cloud/bin/python -m unittest \
  tests.test_cloud_storage tests.test_cloud_auth tests.test_cloud_http \
  tests.test_cloud_lambda tests.test_cloud_seed tests.test_cloud_deploy -v
/absolute/temporary/path/pkb-cloud/bin/python tools/build_cloud_release.py \
  --output /absolute/temporary/path/pkb-cloud-release.zip
```

The observed development checks ran on macOS Python 3.14. The release lock targets
Linux Python 3.12; successfully building its wheels does not prove execution on
Lambda. The ZIP explicitly includes `cloud_kb/*.py` and installed dependencies;
it does not copy the repository, `.env`, fixture, private vault or SQLite data.

The latest targeted run passed 11 checks, including immutable code-upload replay,
configuration mismatch rejection before upload, and first application deployment
orchestration. Its AWS and HTTP deployment responses were simulated. The real
GitHub runner and cloud integration remain separate evidence, not inferred from
those tests.

## Remaining deployment work

1. Resolve the organisation-controlled GitHub OIDC provider route through an
   authorised administrator. Read-only revalidation still returned AccessDenied
   for provider listing. See [permission-verification.md](permission-verification.md).
   No denied action, identity change or policy workaround was attempted.
2. Apply the reviewed trust bootstrap and activate the foundation workflow.
   The authored extension now includes the anchored API and application role scope.
3. Review/apply that scope extension for the application stack, code-only release
   upload and named auth secret. Runtime policy **and** permissions boundary
   permit only that secret for the API role. The deployed roles do not exist yet;
   source authoring does not grant access.
4. Configure an owner-approved Secrets Manager JSON value containing
   `google_client_id`, `google_client_secret`, stable `jwt_signing_key` and
   `storage_encryption_key` (Fernet key). Supply its ARN, the stable Google owner
   subject and exact client callbacks through private deployment configuration.
   No secret values or real owner/client identifiers belong in Git or public logs.
5. Build/upload the code-only release and deploy `infra/application.template.json`
   through the gated application job (`MCP_DEPLOY_ENABLED=true`). Register the
   anchored API's exact `/auth/callback` with Google.
   Confirm the budget/quota constraints, including reserved Lambda concurrency.
6. Publish the fixed synthetic note/index with the pipeline's `MCP_SEED_MOCK=true`
   option after bootstrap `EnableMockSeeding=true`; it invokes `tools/seed_mock_kb.py`.
   This command has not been run against AWS.
   It refuses production names and does not read the actual private vault.
7. Complete owner OAuth and provision the explicitly approved read grant in the
   control table: `PK=GRANT#<verified owner sub>`, `SK=CLIENT#<verified MCP client>`,
   `Revoked=false`, future `ExpiresAt`, `Scopes=["kb:read"]`, and
   `Prefixes=["Resources/MCP Demo/"]`. No login-only automatic grant is enabled.
8. Run `tools/verify_cloud_mcp.py --url https://<deployed-host>/mcp` using owner
   OAuth. It must reject unauthenticated access, discover both tools, search the
   codename and fetch the exact source digest/content/revision over HTTPS.
   Record the actual pipeline run/release and observed result before completion.

The application job checks real liveness and an unauthenticated bearer challenge,
but reports `google_authenticated_read=pending_owner_verification` until step 8.
It cannot report that Google read succeeded from a health check alone.

## Implementation limits

This first remote read slice exposes `search_kb` and `fetch_note` only. It serves
the explicitly labelled `lexical-sqlite-v1` contract, with an 8 MiB/1,000-note
snapshot bound. It does not manufacture embeddings or call a local model.
Requests for vector/hybrid search fail with `embedding_provider_not_configured`.
An approved cloud embedding adapter and bilingual quality evaluation remain
required for semantic retrieval. Writeback, ingestion orchestration, owner review,
private migration and production availability/cost acceptance remain future work.
Existing feature success criteria have not been marked passed by this mock slice.

## Upstream references

- [FastMCP Google OAuth broker and durable encrypted storage](https://gofastmcp.com/integrations/google)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [API Gateway v2 IAM resource and condition support](https://docs.aws.amazon.com/service-authorization/latest/reference/list_apigatewayv2.html)
