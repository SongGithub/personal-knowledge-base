# AWS permission and infrastructure evidence

**Observed**: 2026-10-17. **Result**: authenticated access and representative
deployment-policy checks succeeded; GitHub OIDC bootstrap is blocked for the
current principal. No resources were provisioned. This is preparation evidence,
not proof of a successful stack or working cloud MCP.

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
