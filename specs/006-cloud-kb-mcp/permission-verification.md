# AWS permission and infrastructure evidence

## 2026-10-20 custom-domain permission resolution (UPS-57)

The custom-domain blocker was an identity-policy mismatch. The historical
CloudFormation failure explicitly reported that no identity-based policy allowed
`apigateway:POST` on the domain collection. Current role simulations returned
`AllowedByOrganizations=true`; no organisation policy change was needed.
Organisation parent/policy inventory remains unavailable to the local operator,
so this is evidence for these domain operations, not an audit of all SCPs.

Both bootstrap templates now compare the array-valued API Gateway v2 endpoint
and security-policy keys using `ForAllValues:StringEquals`, with `Null=false`
checks. Project/environment tags, role trust and runtime boundaries are retained.
A live retry then exposed the URL-encoded tagging resource used by API Gateway;
the role now permits that exact path for `mcp.midu.com.au` as well.

The changes were applied through reviewed bootstrap CloudFormation change sets
that modified only the execution role's policy; dependent build resources
re-evaluated unchanged role ARNs. Bootstrap reached UPDATE_COMPLETE. Seven
simulations against the applied role allowed Regional/TLS 1.2 creation and
denied mixed endpoint/TLS values, missing keys and incorrect project/environment
tags. Eight infrastructure checks, six native-pipeline checks and template
linting passed.

An isolated temporary CloudFormation stack used the intended execution role
to create the actual hostname with its issued ACM certificate and a `$default`
mapping to the existing HTTP API. Both resources reached CREATE_COMPLETE and
API Gateway reported the domain AVAILABLE. Cleanup reached DELETE_COMPLETE;
the domain is absent, the application remains UPDATE_COMPLETE, and raw endpoint
health returns HTTP 200. The application stack can own the domain during UPS-58.
No DNS, runtime base URL, Google OAuth configuration or private KB data was
changed by this permission task. Raw evidence stays in ignored private operator
files; [the domain guide](../../infra/CUSTOM-DOMAIN.md) records the deployment
contract. UPS-58 remains responsible for hostname activation and client checks.

**Original audit**: 2026-10-17. Authenticated access and representative deployment
policy checks succeeded, while GitHub OIDC provider operations were denied.
**2026-10-18 update**: the permitted native CodeBuild route has created the
bootstrap and foundation. The historical read-only audit below is not the current
deployment state; see the live execution update at the end and [mock proof](mock-proof.md).

## Live read-only observations

- STS verified the configured IAM user in the intended account. Account IDs,
  principal ARNs, credentials and the raw audit report remain outside Git.
- IAM reported attached `AdministratorAccess`, no user permissions boundary,
  no inline user policies and no group memberships. Organisation controls still
  limit this identity.
- CloudFormation accepted both authored templates through `ValidateTemplate`,
  reporting `CAPABILITY_NAMED_IAM`. This checks structure, not resource creation,
  trust, quotas or deployment handlers.
- `DescribeStacks` for an absent probe stack returned `ValidationError`; that
  response is not evidence of a permission denial or an existing stack.

The installed AWS executable could not start because its old Python interpreter
was missing. Checks used a private temporary standard-library SigV4 helper,
restricted to read-only API actions. It parsed the ignored local `.env` without
shell evaluation and did not display credentials. The helper/report are not
repository files or deployment dependencies. No CLI installation, login-profile
modification or credential rotation occurred.

## Policy simulations and their scope

Representative checks used project-shaped resource ARNs, the current IAM user,
no MFA session and `aws:RequestedRegion=ap-southeast-2`. The IAM pass-role probe
supplied `iam:PassedToService=lambda.amazonaws.com`.

| Service | Actions checked | Allowed |
|---|---:|---:|
| CloudFormation | 8 | 8 |
| S3 | 9 | 9 |
| DynamoDB | 6 | 6 |
| SQS | 5 | 5 |
| Lambda | 8 | 8 |
| API Gateway | 4 | 4 |
| IAM runtime-role operations | 7 | 7 |
| CloudWatch Logs | 4 | 4 |
| **Total** | **51** | **51** |

All 51 reported `AllowedByOrganizations=true`. These are representative action
checks, not an exhaustive simulation of every ARN/condition in the final
templates. For example, the original stack probe used `pkb-dev`; the authored
foundation is `pkb-dev-foundation`. Results describe the current human deployment
identity, not the new CI/service roles, which do not exist yet.

An earlier simulation omitted requested-region context and returned misleading
denials; the table records the rerun with explicit context. Supplemental checks
returned allowed for managed-policy lifecycle, runtime-boundary assignment,
DynamoDB TTL/backups and queue metadata operations.

### OIDC bootstrap restriction

These IAM operations returned `explicitDeny` and `AllowedByOrganizations=false`:

- `iam:CreateOpenIDConnectProvider`
- `iam:GetOpenIDConnectProvider`
- `iam:DeleteOpenIDConnectProvider`
- `iam:ListOpenIDConnectProviders`

Denials persisted with `aws:RequestedRegion=us-east-1`, matching the global IAM
endpoint; `CreateRole` and `CreatePolicy` were allowed in that same context.
An actual read-only provider-list request also returned `AccessDenied` (403).
GitHub provider existence and audience configuration therefore remain unknown.
No provider creation was attempted.

An authorised organisation/account administrator must confirm the permitted
federation route. A confirmed compatible provider ARN can be supplied through
`ExistingGitHubOidcProviderArn`; otherwise an administrator with effective
permission must establish the approved provider. Reuse does not prove federation
is currently permitted. No alternative identity or policy change was used to
evade the organisation restriction.

AWS notes that simulations can differ from live enforcement. Context inputs,
resource policies, quotas and service behaviour still require a reviewed
deployment and OIDC run. An explicit organisation deny is not removed by an
administrator policy. See [simulator limits](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html)
and [policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html).

## Artifact validation

| Artifact | Observed check |
|---|---|
| `infra/foundation.template.json` | JSON parsed; 13 resources; AWS `ValidateTemplate` accepted |
| `infra/bootstrap.template.json` | JSON parsed; 4 declared resources, OIDC conditional; AWS `ValidateTemplate` accepted |
| Both templates | `cfn-lint==1.57.2`, Sydney region, warnings treated as failures: exit 0 |
| `.github/workflows/infra.yml` | YAML parsed; PR validation, main-only deployment, activation gate and job-only OIDC permission checked locally |

SHA-256 for the validated versions:

```text
foundation.template.json  484c46cb39e99835c7216dbf679406993660b06b55f57fdb2b76c5680c2bdfff
bootstrap.template.json   f9772c9611fcd6901bb15a157c26545822db75d107eb50a886e7ec3bc8d8b692
infra.yml                 05709f08d43356ffdf0398270437daad7a2dd232c000d9f00082b096b2f6f87d
```

Lint identified an invalid S3 IAM action during preparation. It was corrected
before the successful lint/AWS validation recorded here. Local workflow checks
do not prove GitHub has loaded or executed the workflow.

## Execution status at the original audit

The [infrastructure guide](../../infra/README.md) describes a one-time
CloudFormation trust bootstrap followed by GitHub Actions OIDC deployment. The
workflow is authored locally; it has not been pushed, activated or run.
Repository role identifiers, branch protection and the activation variable have
not been configured by this work.

No change set was created/executed, no stack or IAM role/provider was created,
no account policy was changed, no model was invoked and no private KB content
was uploaded. Application implementation, migration, recovery acceptance and
cost measurement remain outstanding in [tasks.md](tasks.md).

## 2026-10-18 application pipeline follow-up

The OIDC provider-list API was rechecked and still returned AccessDenied (403).
No denied mutation was attempted. The local `.env` contained AWS fields only;
Google web-client credentials were not configured by this check.

The authored bootstrap now anchors one HTTP API identity, scopes provisioning to
that API and the one API Lambda, permits code-only artifact upload, and optionally
permits the exact mock fixture/index pointer. Named auth-secret access is bounded
to the API runtime role; CI/provisioning cannot read its value. This extension
has not been applied to AWS. It does not resolve the provider restriction.

Latest template versions accepted by AWS `ValidateTemplate` and local
`cfn-lint==1.57.2`:

```text
bootstrap.template.json   6c3721fc42adf1abe94fb76cab3f5fd2ccb7c2f3e88d31db261df8e5fe9dfaf6
foundation.template.json  e02acc8320ede726780819ff9e80262045ac843f8d945643e27e3230f88e65b1
application.template.json 7e0c09a3e62f2ac7bff95dcb1be9637a6d9f688a4fdecb445e57995b1e8f44c1
```

Declared resource counts are 5, 13 and 5 respectively. These later hashes
supersede the original two-template authoring evidence above. AWS accepted the
templates without creating a change set or resource. Eleven local synthetic
checks and a hashed Linux release build are recorded in [mock-proof.md](mock-proof.md).
The additional application deployment job is separately gated and remains unrun.
The credential-free [PR validation run](https://github.com/SongGithub/personal-knowledge-base/actions/runs/39057931922)
passed on GitHub's Linux runner; both AWS deployment jobs skipped. Publishing
the draft PR did not apply the bootstrap, activate deployment or upload KB data.

### Native route checks

The current IAM principal's regional simulations also allowed CodeBuild
CreateProject, UpdateProject, StartBuild, BatchGetBuilds, BatchGetProjects,
StopBuild and DeleteProject, plus named Secrets Manager create/put/get/describe
operations. All returned `AllowedByOrganizations=true`. This is permission
evidence for a delivery mode that does not perform the denied provider actions;
it does not change or bypass those controls or prove resource creation succeeds.
Live Lambda account settings reported 400 total/unreserved concurrency before
the mock deployment, sufficient for the declared reserved concurrency of 2.

## 2026-10-18 actual native execution

The scoped native bootstrap reached CREATE_COMPLETE. It created the retained API
anchor, private named auth secret, runtime boundary, separate provisioning/build
roles, private logs and on-demand CodeBuild project. Its first pinned build
passed 16 checks and deployed `pkb-dev-foundation` to CREATE_COMPLETE. Actual S3
metadata confirmed block-public-access, Enabled versioning, AES256 encryption,
BucketOwnerEnforced ownership and deny-non-TLS policies on all three buckets.
The actual control table is ACTIVE. No private vault was read or migrated.

The first application attempt failed with an identity-policy denial for stage
creation's `apigateway:TagResource`, then reached ROLLBACK_COMPLETE. Inventory
showed only DELETE_COMPLETE Lambda/stage resources. The current native bootstrap
update applied scoped tagging actions and application-only recovery permissions;
its corrected managed release is tracked in [mock-proof.md](mock-proof.md).

AWS DescribeType for `AWS::ApiGatewayV2::Stage` declared TagResource in the create
handler and TagResource/UntagResource in the update handler, matching the live
failure. The pinned linter's IAM catalogue lacks those actions. The small
`tools/lint_infra.py` adapter adds exactly those two catalogue entries; W3037 and
all other lint checks remain active. The regression check rejects misspelled
actions. Actual deployment is required to establish live handler acceptance.

The corrected [GitHub validation](https://github.com/SongGithub/personal-knowledge-base/actions/runs/39061097832)
passed 21 runtime/operator checks, two IAM lint checks and Linux packaging.
GitHub AWS jobs remain skipped: the selected release runner is CodeBuild, using
its own service role, not the local access key. No OIDC/provider or organisation
policy change occurred. Google identity and the authenticated mock read remain
pending owner-approved configuration, so the overall goal is incomplete.

Latest validated template SHA-256 (source revision for managed retry):

```text
bootstrap.template.json  b9bdb2cf5e8a3ef268d2a198fd422f9167ffe38ea713d7fae204ca04b5adfe61
native-pipeline.template.json  e243e9eb5dd975cffbde0b25109dd456ae8ea2d1f9918147cd3d6013c5493702
foundation.template.json  e02acc8320ede726780819ff9e80262045ac843f8d945643e27e3230f88e65b1
application.template.json  7e0c09a3e62f2ac7bff95dcb1be9637a6d9f688a4fdecb445e57995b1e8f44c1
```

### Managed release outcome

The corrected native build at `9370906c00d4701dbbb49ed30af28791f91c3b84`
SUCCEEDED. Bootstrap, foundation and application stacks are respectively
UPDATE_COMPLETE, CREATE_COMPLETE and CREATE_COMPLETE. Independent probes confirmed
health 200, anonymous Bearer 401 and invalid-token 401. Actual Lambda CodeSha256
matches the deterministic release; the versioned mock Markdown matches the fixture,
and the S3 SQLite checksum matches the synthetic active descriptor. This proves
actual managed provisioning and the deployed authentication boundary. It does not
prove Google sign-in or authorised tool reads, which still await owner-approved
client configuration. No private KB data was migrated.
