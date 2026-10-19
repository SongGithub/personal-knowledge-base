# Setup and acceptance guide

**Status**: Updated 2026-10-19. The AWS-native bootstrap, private foundation
and protected MCP have been deployed; the single-client Google-authenticated mock search/fetch proof passed. Migration
tools and full-feature acceptance scenarios below remain future work. See
[deployment-access.md](deployment-access.md) for the login alternatives.

The [foundation templates and infrastructure pipeline](../../infra/README.md)
include a working AWS-native CodeBuild route. It uses service roles and exact
source commits without IAM OIDC provider operations. GitHub Actions provides PR
validation; its OIDC deployment mode remains an alternative requiring an approved
provider. The native SDK bootstrap does not depend on the broken local AWS CLI.
See [permission-verification.md](permission-verification.md).

For the current mock goal, see [mock-proof.md](mock-proof.md): local HTTP/Lambda
checks and the deployed Google-authenticated search/fetch verifier passed.
The first remote read adapter is lexical-only; semantic retrieval and writeback
are not implemented by that slice.

## Prerequisites

- Review [spec.md](spec.md), [plan.md](plan.md), [data-model.md](data-model.md)
  and the [tool contract](contracts/mcp-tools.md).
- Select private account/region, bounded bootstrap/deploy/runtime roles, a Google
  OAuth application and owner binding. Configure exact supported client callbacks.
- Choose permitted existing capture/proposal destinations and an owner approval flow.
- Approve the embedding provider/model and data boundary after quality/cost review;
  use only synthetic content before private-data approval.
- Review regional cost, retention, logs and any proposed paid dependency before
  resource creation. No continuously paid model/vector cluster is assumed.

## Obtain temporary deployment access

Use one existing human sign-in route, not both as a required sequence:

```sh
# Existing IAM Identity Center setup:
aws configure sso --profile kb-deploy
aws sso login --profile kb-deploy

# Alternative for an IAM/federated console identity, CLI >=2.32.0:
aws login --profile kb-session
```

For the second route, configure a private role profile as documented in the
access guide. Confirm the selected deployment account/role without displaying
credentials:

```sh
aws sts get-caller-identity --profile kb-deploy
```

## Future synthetic acceptance sequence

These procedures become executable when application implementation and operator
tooling are available. The foundation alone does not provide the service. Record
observed results separately from proposed targets.

1. **Deploy and restart**: Review a synthetic change set; deploy the identified
   release through scoped temporary access. Restart/recycle workers and confirm
   OAuth signing/grants survive. An unrelated deploy action must be denied.
2. **Two-client Google linking**: Authorize two distinct clients as the configured
   owner. Run the same 12 bilingual search/fetch cases. Exercise another account,
   invalid audience, expired token, missing scope and revoked grant; expect zero
   private disclosure and revocation within five minutes.
3. **Offline home devices**: Keep the Mac, NAS and Obsidian offline for 24 hours.
   Demonstrate retrieval, query embeddings, durable capture and background refresh
   without home-network calls. Record cold/warm latency, not an assumed SLA.
4. **Learning loop**: Client A captures a synthetic learning with provenance and
   operation ID. Client B immediately fetches its committed revision, then searches
   it after indexing. A persistence receipt is distinct from indexing completion.
5. **Write safety and approval**: Retry an identical operation, reuse its ID with
   different content, and race two expected-revision updates. Only intended
   mutations persist. Submit a canonical proposal; the AI cannot approve it.
   Changing its base/content invalidates a prior owner approval.
6. **Incremental indexing**: In a 100-note fixture, change one note, then delete
   another. Reuse all unchanged document embeddings. Deliver duplicate/out-of-order
   events and corrupt an unpublished artifact; preserve a valid active snapshot,
   reject obsolete publication and disclose freshness. Rebuilding an index must
   neither lose grants nor make a saved note unfetchable.
7. **Recovery and cost**: Fail a release and confirm previous compatible code
   resumes within the proposed five-minute target without reverting accepted
   notes. Restore a recoverable export. Measure compute, snapshots, operation
   history, model tokens, logs, secrets and retention against the cost worksheet.

## Private migration rehearsal and cutover (later)

Before uploading actual knowledge, confirm the approved provider/data boundary,
target storage policy, migration plan and source authority. Inventory a complete
source snapshot, including cloud placeholders that must be downloaded. Preserve
folder names, content digests, links, attachments and source provenance. Verify
100% of the manifest and representative bilingual retrieval privately.

Freeze old writers only during a reviewed cutover window, reconcile final
changes and designate one authoritative cloud namespace. Preserve a recoverable
source export. Exercise rollback with writes accepted after cutover; export or
reconcile them before restoring another authority. A copied index, successful
deployment or file checksum alone does not prove a completed migration.

## Honest status reporting

- `planned`: specified, no implementation evidence.
- `deployed`: identified cloud release exists and authenticated readiness passed.
- `persisted`: exact Markdown revision is durably stored.
- `pending_review`: proposed canonical mutation has not been approved/applied.
- `indexing_pending` / `indexing_failed`: saved content exists but search is behind.
- `indexed`: selected published snapshot includes the named revision.
- `migrated`: source completeness and authority cutover are verified; no competing writer.

The single-client synthetic read proof is recorded in `mock-proof.md`. The broader
service/migration acceptance sequence above remains unexecuted; it requires the
remaining feature implementations and separate measured acceptance.
