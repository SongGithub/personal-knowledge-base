# Mock Markdown end-to-end proof

**Goal**: Prove the cloud MCP is up end to end using a synthetic KB Markdown file.
**Observed**: 2026-10-18, Australia/Melbourne. **Status**: incomplete. The native
bootstrap, private foundation and protected MCP are deployed through CodeBuild. Google client creation,
real owner binding, per-client grant and authenticated HTTPS retrieval remain
required. Local tests and liveness checks do not satisfy that completion gate.

## Current evidence

| Requirement | Evidence | Result |
|---|---|---|
| Real deployment permissions | Native CloudFormation bootstrap created service/provisioning roles, runtime boundary, private secret, logs, API anchor and CodeBuild project | Actual AWS creation passed |
| Infrastructure deployment through a pipeline | CodeBuild at exact commit `43aa51262e3db1b8a67b2ccea6961fe8d5f9ce72` passed 16 checks and deployed the foundation | Actual foundation `CREATE_COMPLETE` |
| Private storage configuration | Actual Markdown/index/release buckets each have block-public-access, versioning enabled, AES256 encryption, owner-enforced ownership and a deny-non-TLS policy; control table ACTIVE | Actual configuration verified |
| Correct immutable release | Managed Linux build produced 34,031,600-byte ZIP with SHA-256 `eb95e0f84ae8e66d815eb2ef323de89c38c7f66bd529a4ab547c9e12fd9468ca`, matching two independent local builds | Real build passed |
| Application deployment | First attempt failed because the stage provider required an additional scoped tagging action; application rolled back with only deleted Lambda/stage resources. Corrected bootstrap applied; managed retry at `9370906c00d4701dbbb49ed30af28791f91c3b84` succeeded and application reached CREATE_COMPLETE | Actual managed deployment passed |
| PR validation | [Corrected run](https://github.com/SongGithub/personal-knowledge-base/actions/runs/39061097832) passed validation, 21 runtime/operator checks, two IAM lint checks and Linux packaging | Actual GitHub runner passed |
| Mock source/index in real S3 | Actual versioned S3 note matches fixture bytes/SHA; immutable snapshot matches its DynamoDB descriptor SHA and contains one note, marked SyntheticOnly | Actual seeding and object verification passed |
| Deployed HTTP liveness/auth rejection | Independent HTTPS probes returned health 200 and Bearer 401 for anonymous and invalid-token requests | Actual deployed boundary passed |
| Google identity and owner/client grant | Dedicated client form prepared; persistent credential creation awaits owner confirmation | Pending |
| HTTPS Google-authenticated search/fetch | Exact fixture digest/content/revision must be returned through real OAuth and actual storage | Pending; goal incomplete |
| HTTP implementation | Maintained MCP client searched/fetched exact bilingual fixture over a real loopback socket | Local layer passed with simulated AWS |
| Access failures | Invalid/expired/wrong-audience/missing-scope tokens, different owner, revoked grants, traversal and hostile Host/Origin rejected | Synthetic signer/grants only |
| OAuth persistence | Encrypted state recovered by a new adapter instance; expired records rejected without waiting for TTL deletion | Adapter checks passed; real OAuth state still pending |
| Lambda compatibility | Repeated Mangum API Gateway v2 invocations, including legacy `2025-11-25` initialization/tools-list | Local adapter passed |
| Dependencies | 75 locked runtime distributions audited; zero known advisories returned | Passed at audit time; not a security guarantee |

The local HTTP tests use response stubs for S3, a test table and an ephemeral
signer. They do not prove Google, real S3/DynamoDB or Lambda deployment. No actual
private vault, iCloud, home device, oMLX or embedding provider is used by this
synthetic slice. Public evidence excludes account/owner IDs, credentials, private
notes and operator records. The draft [PR #1](https://github.com/SongGithub/personal-knowledge-base/pull/1)
remains unmerged; main is unchanged.

## First deployment and recovery

The AWS-native route uses CodeBuild service trust and a reviewed source commit;
no IAM OIDC provider operation or organisation-policy change is required. The
original GitHub federation restriction remains in force. Details and cost basis
are in [NATIVE-PIPELINE.md](../../infra/NATIVE-PIPELINE.md).

The first build passed its checks and created the foundation, then failed at
stage creation. AWS's live `AWS::ApiGatewayV2::Stage` schema declares
`apigateway:TagResource`/`UntagResource`, matching the actual access denial.
Both bootstrap templates now permit these only on the anchored API. The pinned
validator's action catalogue omits them, so `tools/lint_infra.py` adds exactly
those entries while retaining every check. Regression tests prove a misspelling
still fails W3037. The intermediate [failed validation run](https://github.com/SongGithub/personal-knowledge-base/actions/runs/39060959659)
is preserved; it was corrected rather than rerun unchanged.

The release helper may remove rolled-back application metadata only after
checking that every inventoried resource is an already deleted Lambda/API
resource. It refuses live/retained resources and data resources. The foundation
is never implicitly deleted or recreated. The corrected managed pipeline succeeded
without rebuilding the foundation, seeded the fixed mock data and verified liveness
and the authentication boundary. Its Lambda CodeSha256 independently matched the
release hash above. This recovery required no console operations.

## Reproduce local verification

Install constrained operator/test and infrastructure dependencies in an isolated
environment. The release builder separately installs the hashed Linux runtime
lock, excluding operator tools, credentials, fixtures, private vault and SQLite.

```sh
python3 -m venv /absolute/temporary/path/pkb-cloud
/absolute/temporary/path/pkb-cloud/bin/python -m pip install --only-binary=:all: \
  -r requirements-cloud-test.txt -r infra/requirements.txt
/absolute/temporary/path/pkb-cloud/bin/python tools/lint_infra.py \
  infra/foundation.template.json infra/bootstrap.template.json \
  infra/application.template.json infra/native-pipeline.template.json
/absolute/temporary/path/pkb-cloud/bin/python -m unittest \
  tests.test_cloud_storage tests.test_cloud_auth tests.test_cloud_http \
  tests.test_cloud_lambda tests.test_cloud_seed tests.test_cloud_deploy \
  tests.test_cloud_build tests.test_cloud_native tests.test_cloud_operator \
  tests.test_cloud_lint -v
/absolute/temporary/path/pkb-cloud/bin/python tools/build_cloud_release.py \
  --output /absolute/temporary/path/pkb-cloud-release.zip
```

The current targeted suite has 23 tests. GitHub installs the runtime version
constraints derived from `requirements-cloud.lock`; CodeBuild does likewise.
The first 11-test [GitHub run](https://github.com/SongGithub/personal-knowledge-base/actions/runs/39057931922)
and later 16-test [run](https://github.com/SongGithub/personal-knowledge-base/actions/runs/39060475331)
remain historical evidence for their own revisions.

## Remaining cloud completion gate

1. Deployment, immutable release hash, actual mock S3/index pointer, liveness and
   anonymous/invalid-token rejection are verified. Preserve these checks on the
   next configuration release; they do not prove the Google login.
2. After owner confirmation, create the dedicated Google client with the exact
   deployed `/auth/callback` and one-time localhost owner callback. Use
   `tools/google_owner_subject.py` to obtain a Google-verified stable subject.
   Store the real client secret in the existing Secrets Manager JSON, preserving
   signing/encryption keys, and bind the verified owner through private bootstrap
   configuration. Releasing that configuration refreshes the Lambda environment.
3. Run `tools/verify_cloud_mcp.py` with actual owner OAuth. Its optional, separate
   owner-admin step checks the deployed endpoint/owner and grants the authenticated
   SDK client only 30 minutes of read access to the exact synthetic note. It cannot
   overwrite a broader/revoked/expired existing grant. Ordinary clients receive
   no AWS credentials and login alone does not create a KB grant.
4. Prove anonymous denial, tool discovery, codename search and exact UTF-8
   content/SHA/revision fetch through the real HTTPS endpoint. Record actual
   Google/pipeline/storage results before completing T033.

The application job reports `google_authenticated_read=pending_owner_verification`
until the authenticated verifier passes. A health check cannot complete the goal.

## Implementation limits

This first remote read slice exposes `search_kb` and `fetch_note` only. It serves
an explicitly labelled `lexical-sqlite-v1` contract, with an 8 MiB/1,000-note
snapshot bound. It does not manufacture embeddings or call a local model.
Vector/hybrid requests fail with `embedding_provider_not_configured`. A cloud
embedding adapter and bilingual quality evaluation, writeback, ingestion
orchestration, owner review, private migration and production availability/cost
acceptance remain separate feature work. They are not completed by this mock.

## References

- [FastMCP Google OAuth and encrypted storage](https://gofastmcp.com/integrations/google)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)
- [API Gateway v2 IAM resource/operation mapping](https://docs.aws.amazon.com/service-authorization/latest/reference/list_apigatewayv2.html)
