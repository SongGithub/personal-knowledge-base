# AWS deployment access

**Date**: 2026-10-17. This guide describes access setup, not an authorization to
create resources or move private data. No credentials belong in this document.

## Recommended arrangement

Use a scoped IAM deployment role through a local AWS CLI profile with temporary
credentials. The owner completes browser sign-in locally; the assistant uses the
agreed profile through the CLI. A role ARN alone cannot authenticate a process:
an already authenticated principal must be trusted and permitted to assume it.

The profile name and chosen region can be shared in the conversation. Keep
private account configuration local; do not paste access keys, session tokens,
root credentials, browser cookies or Google client secrets into chat or Git.

## 1. Repair the CLI before login

The AWS executable found during this documentation update could not start: its
configured Python interpreter was missing. That is a local tool issue, not an
AWS account or IAM failure. Install/repair current AWS CLI v2 through the
[official installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html),
resolve PATH ambiguity, and confirm the selected executable reports version 2:

```sh
type -a aws
aws --version
```

The browser-based `aws login` option below requires CLI >=2.32.0. No installation,
login or profile modification has been performed by this documentation update.

## 2. Choose the existing human sign-in route

### IAM Identity Center already configured

An account administrator assigns a project-scoped permission set to the owner.
Then the owner runs locally:

```sh
aws configure sso --profile kb-deploy
aws sso login --profile kb-deploy
```

Choose the intended account and role/permission set during configuration. Do not
assume the profile has deployment rights just because login succeeds.

### IAM or federated console sign-in without Identity Center

Use browser sign-in with the authorized IAM/federated identity, not the root user:

```sh
aws login --profile kb-session
```

The identity needs AWS's `SignInLocalDevelopmentAccess` permissions in addition
to the permissions needed for its work. The owner chooses the intended console
identity in the browser. This obtains temporary credentials, not a long-lived key.
This route is distinct from Google sign-in to the KB application.

If that session assumes a separate deployment role, configure an AWS role profile
locally after an administrator establishes its trust and permission policies:

```ini
[profile kb-deploy]
source_profile = kb-session
role_arn = arn:aws:iam::<ACCOUNT_ID>:role/<APPROVED_KB_DEPLOY_ROLE>
region = <APPROVED_REGION>
```

These placeholders must be replaced only in private AWS configuration. If the
browser session already has the intended scoped role, its profile can be used
directly instead. Document the selected profile to avoid accidental use of a
default administrator account.

## 3. Confirm identity, then review deployment changes

After the owner signs in, a read-only identity check confirms which account/role
the agreed profile uses:

```sh
aws sts get-caller-identity --profile kb-deploy
```

This confirms identity, not all required deployment permissions. A dry-run/change
set and access review must identify missing permissions without broadening the
role to administrator. Authentication does not select an embedding provider,
approve private-content transfer, set a spending limit or authorize destructive
data migration. Those choices belong in the concrete deployment/migration review.

## 4. Separate permission boundaries

| Identity | Intended permissions |
|---|---|
| Bootstrap administrator | Establish bounded roles, permissions boundaries and trust relationships; perform explicitly reviewed initial setup |
| Local deployer / later CI deployer | Operate only the KB infrastructure stack, upload deployment artifacts and pass the specific provisioning role |
| CloudFormation service role | Provision the approved KB resources and constrained execution roles; no authority to widen its own boundary |
| MCP API function | Access required note/control records, queues, named secrets and logs within its role; application policy narrows each client request further |
| Ingestion function | Read approved source revisions, invoke approved model resources, write derived index artifacts and update ingestion/publication state |
| Owner approval flow | Validate the owner and apply approved proposals through the controlled writer; not a client-delegated AI approval capability |
| AI client | KB OAuth capabilities and path grants only; no deployment role or direct S3/IAM credential |

Permission policy details are generated against actual resource names/ARNs during
implementation. The deployer needs no general account administration. Restrict
`iam:PassRole` to approved ARNs and `iam:PassedToService`, and constrain
CloudFormation role selection with `cloudformation:RoleARN`. Restrict stack
operations too: callers allowed to operate a stack can use its already attached
service role even without a fresh PassRole check. Avoid broad IAM creation,
self-modifying roles and trust/policy changes that escape an enforced boundary.

An unprivileged role cannot bootstrap its own trusted access. An existing
authorized administrator must create or approve initial roles and trust. An IAM
role is scoped through its permissions and trust policy, not merely its name.

## 5. Later continuous deployment

**Implementation follow-up, 2026-10-17**: the
[CloudFormation bootstrap/foundation and GitHub Actions workflow](../../infra/README.md)
are now authored locally. Routine infrastructure delivery uses that pipeline.
The [permission audit](permission-verification.md) verified authentication and
representative deployment actions, but found an organisation restriction on
OIDC provider operations. An authorised administrator must confirm the approved
provider/setup before activation. No stack, provider, role or GitHub configuration
has been applied; the CLI repair remains outstanding.

Use GitHub Actions OIDC to assume a separate deployment role. Constrain audience
to `sts.amazonaws.com`, subject to the exact trusted repository and protected
branch/environment, and apply environment protection where used. Untrusted fork
and PR jobs get no deployment or private corpus access. Keep synthetic CI,
release delivery, private source publication and identity administration separate.

## Sources

- [Temporary credentials and IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [Identity Center CLI setup](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [Browser-based CLI login](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)
- [CLI role profiles](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-role.html)
- [Passing a role to an AWS service](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_passrole.html)
- [CloudFormation service-role boundary](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html)
- [Least-privilege CloudFormation policies](https://docs.aws.amazon.com/prescriptive-guidance/latest/least-privilege-cloudformation/best-practices-identity-based-policies.html)
- [GitHub OIDC roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html#idp_oidc_Create_GitHub)
