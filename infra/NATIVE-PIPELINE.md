# AWS-native deployment pipeline

The current account permits CodeBuild project/start/read operations while denying
IAM OIDC provider operations. This delivery mode needs no IAM identity provider
or organisation-policy change. The original GitHub OIDC template remains an
alternative for accounts where that federation setup is approved.

## Trust and release flow

1. An authorised local operator applies `native-pipeline.template.json` once
   through CloudFormation, using temporary/local credentials outside Git.
2. The stack creates a private on-demand CodeBuild project, a service role scoped
   to that exact project's SourceArn/SourceAccount, the bounded provisioning role,
   runtime boundary, named private auth secret, logs and one HTTP API identity.
3. The operator starts a release at an exact approved public Git commit. There is
   no PR webhook, GitHub token, persistent runner or AWS access key in the build.
4. `infra/buildspec.yml` installs constrained dependencies, validates templates,
   runs synthetic checks, deploys the foundation, builds immutable code and applies
   the application stack with the bounded provisioning role.
5. Optional mock seeding writes only the fixed synthetic note and index namespace;
   the publisher refuses a non-synthetic active index. Owner/client read grants
   are provisioned separately. Google-authenticated read remains an acceptance gate.

The native and GitHub bootstrap templates are alternative owners of the same
`pkb-dev-bootstrap` stack/role names. The helper refuses to replace an existing
other delivery mode implicitly. The pipeline cannot edit its own bootstrap role,
secret value, source configuration or organisation policies.

## Initial command

Use a private operator environment with boto3 installed; this does not repair or
depend on the previously broken AWS CLI. Credentials can come from the standard
SDK chain, or explicitly from the owner's ignored local file:

```sh
python tools/bootstrap_native_pipeline.py \
  --env-file /absolute/private/path/.env \
  --source-commit <REVIEWED_40_CHARACTER_COMMIT> \
  --apply --start-build --seed-mock
```

Without `--apply`, the helper prepares a review-only change set. Execute the
named reviewed change set through the normal CloudFormation API/CLI; a review
alone does not provision the resources. The first applied setup generates stable
signing/encryption material privately, with intentionally unconfigured Google
credentials and owner binding. Health/401 checks can pass, but no Google or KB
read can succeed until the owner supplies the real client configuration and grant.
No fake issuer or auth-disable environment flag is installed.

Private stack outputs/build handles are saved to a mode-0600 temporary operator
record. They are not published as Git artifacts. Release success must be read from
the actual CodeBuild/CloudFormation state, then the HTTPS OAuth verifier must pass.

The first real application attempt exposed a missing API Gateway stage tagging
permission and rolled back. Both bootstrap variants now scope the provider's
`TagResource`/`UntagResource` actions to the anchored API. The release helper can
retry only an application in `ROLLBACK_COMPLETE` whose resource inventory consists
entirely of deleted Lambda/API resources. It refuses live resources, retained
resources, buckets and other data resources. Foundation recovery is never implicit.

`tools/lint_infra.py` runs the pinned validator with its IAM action catalogue
extended by exactly those two actions from the live AWS stage provider schema.
Version 1.57.2's bundled catalogue omits them. No rule is suppressed: regression
checks verify that an invented misspelling still fails W3037.

## Owner identity and mock grant

Create a dedicated Google web client after owner approval, with the deployed
origin's `/auth/callback` and the one-time owner callback
`http://localhost:8766/google/callback`. Download its JSON to a private file.
`tools/google_owner_subject.py` performs a loopback PKCE login and uses the
maintained Google verifier to check audience, scopes, expiry and verified email.
It saves only the stable subject/email in a new mode-0600 owner file; authorization
codes and access tokens are not printed or saved. Bind that verified subject in
the private bootstrap parameter and store the client credentials in its existing
Secrets Manager JSON, preserving the signing/encryption keys.

After deploying that real configuration, `tools/verify_cloud_mcp.py` accepts
`--owner-file` and `--aws-env-file` for an explicit owner-admin setup step. It
checks the actual endpoint and deployed owner binding, obtains the MCP client's
identity from the authenticated SDK, then conditionally creates only a 30-minute
`kb:read` grant for the exact synthetic note. Existing broader/revoked/expired
grants are preserved and require owner review. Normal AI clients receive no AWS
credentials and cannot grant themselves access. `--authorization-file` stores
the login URL privately for controlled browser use.

After a write-enabled release, use `tools/grant_mcp_client.py` from an owner
operator session to grant one authenticated client `kb:capture` on an exact
prefix under `Ideas/` or `Resources/_Review/AI Learning/`.
The helper checks the deployed owner binding, expires grants within 90 days,
preserves any still-active grant, and supports the standard AWS SDK chain
(including an SSO profile). Add `--scope kb:read --read-prefix Ideas/` only when
that same client also needs to retrieve its captures. No grant is created by
deployment or Google sign-in alone.

Use only the owner-approved destination and duration. The current learning
approval is for `Resources/_Review/AI Learning/`, with no existing-note edits,
for 90 days from the original activation. Do not extend that expiry when
redeploying. Keep existing read prefixes and do not replace an active grant
merely to match an example command. The foundation API policy and both runtime
boundary templates must support the chosen folder before enabling the corrected
application. See [the local handoff](../specs/006-cloud-kb-mcp/writeback-local-handoff.md).

These helpers require the constrained operator/test dependencies, including
Requests; they are excluded from the code-only Lambda artifact.

## Bounded cost profile

AWS's Sydney price-list entry for Linux x86 `general1.small` is USD 0.005 per
build minute, checked on 2026-10-18. A five-minute build is USD 0.025 before
eligible free allowance and other services. The project uses one concurrent build,
a 15-minute execution timeout, no reserved fleet, privileged Docker, persistent
cache or image server. Idle build compute is not required.

Secrets Manager, S3 versions/code/index storage, DynamoDB/PITR, SQS, logs, Lambda,
HTTP requests and transfer remain separate charges. This is a mock-workload
planning basis, not an account-wide bill or an all-in spending cap. No model
invocation permission is selected by default and no private embeddings are sent.

Sources: [AWS CodeBuild pricing](https://aws.amazon.com/codebuild/pricing/),
[Sydney price list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/CodeBuild/current/ap-southeast-2/index.json),
[supported images](https://docs.aws.amazon.com/codebuild/latest/userguide/ec2-compute-images.html),
[Python runtime support](https://docs.aws.amazon.com/codebuild/latest/userguide/available-runtimes.html).
