# KB infrastructure as code

CloudFormation is the selected implementation for the initial AWS foundation.
Templates are ordinary JSON, accepted directly by AWS; no Terraform state,
container build or continuously running deployment worker is required.

## Delivery pipeline

The current account also supports an [AWS-native CodeBuild delivery mode](NATIVE-PIPELINE.md),
which needs no external IAM OIDC provider. The scoped native bootstrap/buildspec
is being prepared for the mock proof; its live deployment status is recorded in
the mock evidence. The GitHub workflow below remains the credential-free PR
validation path and an optional OIDC deployment path for an approved provider.

`.github/workflows/infra.yml` is the deployment path:

1. Pull requests validate all templates with pinned `cfn-lint`, without AWS
   credentials or an OIDC token. Forked code cannot deploy.
2. Pushes to `main` validate the same commit. Deployment runs only when the
   repository variable `INFRA_DEPLOY_ENABLED` is exactly `true`.
3. GitHub OIDC assumes the bounded deployment role; no AWS access/secret key is
   stored in GitHub. It may operate only the development foundation/application
   stacks and read the bootstrap's identifiers.
4. AWS CLI creates/executes the CloudFormation change set with the separate
   provisioning role, waits for completion and records stack status/commit.
5. Deployments serialize and do not cancel an in-progress stack operation.
6. A separately gated application job builds/uploads immutable code, applies its
   change set, checks liveness and checks bearer-auth rejection. It additionally
   requires `MCP_DEPLOY_ENABLED=true`. Google-authenticated retrieval remains a
   required owner/client acceptance step.

There is no `pull_request_target` workflow and no checkout of untrusted code in
the credentialed job. Action revisions are pinned by commit SHA. Keep `main`
protected and require reviewed changes for infrastructure and workflow files.
The current workflow deploys development in Sydney only. Production needs a
separate reviewed trust/approval policy, not just an input that changes the name.

## Files

| File | Purpose |
|---|---|
| `bootstrap.template.json` | OIDC provider/reuse, deployment/provisioning roles, runtime boundary and retained HTTP API identity anchor |
| `foundation.template.json` | Private KB/index/release storage, control records, ingestion queues, log groups and runtime roles |
| `application.template.json` | Google-protected read-only Lambda and routes/integration/stage on the anchored HTTP API |
| `requirements.txt` | Pinned infrastructure validator used in local/PR checks |
| `../.github/workflows/infra.yml` | Credential-free validation and OIDC deployment from the trusted branch |

The foundation defines separate buckets:

- **DataBucket**: canonical Markdown under `notes/` and source attachments under
  `attachments/`. Canonical authority moves only after the migration cutover.
- **IndexBucket**: private embedding/index snapshots under `indexes/`, including
  completed SQLite backups and manifests. These contain private text/vectors.
- **ReleaseBucket**: code releases only; no corpus, embeddings or credentials.

All buckets block public access, disable ACLs, require TLS, use SSE-S3 encryption,
and retain versioned objects. Only abandoned multipart uploads are expired by
default. Active index snapshots are not deleted by an age-based lifecycle rule.

## One-time trust bootstrap

A new pipeline cannot authorize its own initial AWS OIDC role. The administrator
applies `bootstrap.template.json` once using existing authorized local credentials
or temporary browser/SSO credentials. This is a repeatable CloudFormation setup,
not a set of console-created resources. Subsequent foundation changes go through
the pipeline. The pipeline cannot modify its own bootstrap stack or boundary.
The bootstrap anchors one HTTP API ID so the provisioning role can manage its
children without a wildcard grant over unrelated APIs. The anchor alone has no
MCP routes or knowledge access; the application stack supplies those later.

The local AWS CLI must be version 2 and functional. The executable discovered
during the permission audit was broken; validation used a private temporary
signed-request helper instead. That helper is not a production deployment tool
and is not committed. See the [access guide](../specs/006-cloud-kb-mcp/deployment-access.md).

### Select exact GitHub trust

`GitHubOidcSubject` is mandatory and matched with `StringEquals`; no wildcards.
The workflow uses a branch subject and deliberately has no GitHub environment.
Do not add an environment without changing and reviewing its trust contract.

Repositories created after 2026-07-15 use GitHub's immutable subject format:

```text
repo:OWNER@OWNER_ID/REPOSITORY@REPOSITORY_ID:ref:refs/heads/main
```

Older repositories can use the legacy format or opt in to immutable subjects:

```text
repo:OWNER/REPOSITORY:ref:refs/heads/main
```

Read repository metadata and OIDC customization before filling the exact subject.
Do not print an OIDC JWT or widen trust with `*` to work around a mismatch. This
repository was created after the immutable-format cutover; the observed numeric
identifiers belong in private bootstrap parameters, not a hardcoded trust policy.

Sources: [GitHub subject formats](https://docs.github.com/en/actions/reference/security/oidc),
[AWS OIDC integration](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html).

### Apply bootstrap through CloudFormation

Before applying, check whether this AWS account already has the GitHub OIDC
provider. Reuse its ARN through `ExistingGitHubOidcProviderArn` if present; AWS
does not allow duplicate providers with the same issuer URL. Confirm the existing
provider includes audience `sts.amazonaws.com`. Omit the parameter only when
creating the provider for the first time.

**Current blocker (2026-10-17)**: the audited IAM user is denied OIDC provider
list/get/create/delete operations by an organisation control. The live list call
also failed with AccessDenied, so provider existence is unknown. An authorised
administrator must confirm an approved existing provider or establish the
permitted federation setup before bootstrap can proceed. See the
[permission evidence](../specs/006-cloud-kb-mcp/permission-verification.md).

Create a private parameter file outside Git with the exact GitHub subject and any
existing provider ARN. Then, from the repository root, with the selected profile:

```sh
aws cloudformation create-change-set \
  --profile kb-deploy --region ap-southeast-2 \
  --stack-name pkb-dev-bootstrap \
  --change-set-name kb-bootstrap-initial \
  --change-set-type CREATE \
  --template-body file://infra/bootstrap.template.json \
  --parameters file:///absolute/private/path/bootstrap-parameters.json \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation wait change-set-create-complete \
  --profile kb-deploy --region ap-southeast-2 \
  --stack-name pkb-dev-bootstrap --change-set-name kb-bootstrap-initial

aws cloudformation describe-change-set \
  --profile kb-deploy --region ap-southeast-2 \
  --stack-name pkb-dev-bootstrap --change-set-name kb-bootstrap-initial
```

Review the concrete IAM/trust changes and cost before executing that change set.
For an existing bootstrap use a new named UPDATE change set. The foundation and
workflow defaults are `ProjectName=pkb`, `Environment=dev`, region Sydney; keep
these values aligned with the bootstrap permission scope.

The 2026-10-18 extension adds provisioning for the exact API Lambda, its runtime
role pass-through, the anchored API and code-only release reads. It grants no
general Lambda/API/IAM administration. Broad human admin access is not copied
into CI/runtime roles. `AuthSecretArn` is optional for foundation-only setup;
application activation requires the same exact ARN in bootstrap, foundation and
application. Its runtime-boundary allowance applies only to the API role, not
ingestion. CI/provisioning receives no secret-value read permission.

### Connect the pipeline

After bootstrap finishes, place these non-key configuration values in repository
Actions secrets so ARNs/account identifiers do not appear in public logs:

- `AWS_INFRA_DEPLOY_ROLE_ARN`: bootstrap `GitHubDeploymentRoleArn` output.
- `AWS_CFN_EXECUTION_ROLE_ARN`: bootstrap `CloudFormationExecutionRoleArn` output.
- `AWS_RUNTIME_BOUNDARY_ARN`: bootstrap `RuntimePermissionsBoundaryArn` output.

These are role/policy identifiers, not AWS access keys. Keep Google/OAuth secrets
and private data entirely outside this pipeline. Protect the trusted branch, then
set repository variable `INFRA_DEPLOY_ENABLED=true` after reviewing the initial
foundation and cost. Run the workflow on `main`, or merge a reviewed infra change.

The activation switch is configuration, not a security boundary: exact OIDC trust,
scoped IAM permissions and trusted-branch review are the security boundaries.
Repository settings and bootstrap have not been applied by authoring these files.

### Activate the application stage

After reviewing/applying the extended bootstrap, supply these additional Actions
secrets (identifiers/configuration only; never the Google secret value):

- `AWS_MCP_AUTH_SECRET_ARN`: existing approved Secrets Manager secret ARN,
  matching bootstrap `AuthSecretArn`. The foundation job passes it to its API role.
- `KB_GOOGLE_OWNER_SUB`: verified stable Google owner subject.
- `KB_CLIENT_REDIRECT_URIS`: JSON list of exact approved MCP client callbacks.

Set `MCP_DEPLOY_ENABLED=true` when these are ready. The application job verifies
bootstrap/foundation consistency before uploading code. Releases use SHA-256
names, existence preconditions and pinned S3 VersionIds. Change sets and
completion waits run in the pipeline.

For the mock demonstration only, `MCP_SEED_MOCK=true` additionally requires the
bootstrap parameter `EnableMockSeeding=true`. Optional permissions cover only
the fixed synthetic note, `indexes/mock/` and `INDEX#ACTIVE`. Seeding refuses an
index not marked `SyntheticOnly`. Disable these permissions and the workflow
variable before private cutover. CI cannot create owner/client grants; complete
the approved mock read grant and Google verifier described in the mock proof.

## Runtime and recovery boundaries

- ControlTable is on-demand with optional PITR (enabled by default), TTL for
  explicitly expiring records, and production deletion protection. Expiry and
  revocation are enforced by the application; TTL deletion is asynchronous.
- DynamoDB encrypts at rest using its default AWS-owned key. No customer-managed
  KMS key or continuously provisioned database is introduced.
- API and ingestion roles trust Lambda only, are separated by function, and receive
  the bootstrap runtime boundary in the pipeline. The ingestion role cannot write
  canonical notes or read authorization partitions. Its DynamoDB key prefixes are
  `OP#`, `INDEX#` and `JOB#`; grants/OAuth state use other namespaces.
- The optional model parameter is empty by default: no model invocation permission
  is granted. A selected approved model must be added to both bootstrap boundary
  and foundation policy before use. No model or secret is deployed here.
- Ingestion has a 4-day queue, 14-day DLQ, five delivery attempts and 5,400-second
  visibility timeout for a future worker timeout up to 900 seconds. The worker
  still needs idempotency, a fenced publication lease and bounded concurrency.
- Logs retain 14 days by default. Do not log private passages, tokens or credentials.
- Buckets, table, queues and log groups are retained on deletion/replacement;
  deletion of the stack is not data erasure. Retained resources continue to incur
  storage/backup charges and require explicit reconciliation/import before
  reusing their names. Runtime roles are removed normally on stack deletion.
- Version history and PITR are not a complete backup/export/restore procedure.
  Retention pruning and independent recoverable exports remain later tasks.

The foundation creates no running compute, public endpoint, vector service, NAT
gateway, model server or hosted runner. Storage, PITR, logs and GitHub runner
usage still need a workload-based budget. It is infrastructure preparation, not a
working MCP or a completed migration.

## Validation and current status

The later [mock proof](../specs/006-cloud-kb-mcp/mock-proof.md) adds a stateless
HTTP adapter, Google broker/durable encrypted store, synthetic note, local
verification and Linux release builder. The workflow checks/builds that slice
without credentials and includes a separately gated application deployment job.
The scope extension is authored, not applied to AWS. The real cloud/Google proof
has not passed. This does not activate an unauthenticated fallback.

Templates are checked with AWS `ValidateTemplate` and local pinned lint. The
dated evidence identifies validated versions; local checks use:

```sh
python3 -m pip install -r infra/requirements.txt
cfn-lint --non-zero-exit-code warning --regions ap-southeast-2 \
  --template infra/foundation.template.json infra/bootstrap.template.json infra/application.template.json
```

See [permission evidence](../specs/006-cloud-kb-mcp/permission-verification.md) for
scope and limitations. Template validation does not prove all resource handlers,
quotas, OIDC federation or the eventual pipeline deployment work. No change set
has been executed and no KB content has been uploaded.
