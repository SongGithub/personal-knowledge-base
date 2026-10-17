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
