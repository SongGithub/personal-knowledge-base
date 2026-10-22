# Ordinary-folder creation — Cloud KB 0.4.0

Owner request, 2026-10-22: enable writes across ordinary KB folders after a new
idea capture was rejected. The old full-write option granted broad updates but
creation only in the learning review folder.

## Behaviour

- Full write approvals grant creation and revision-checked updates in Ideas,
  Projects, Areas, Resources, Personal Facts and Templates, including subfolders.
- Learning-only approvals retain their narrow review-folder destination. Read-only
  approvals stay read-only. Deployments never automatically expand client grants.
- Captures validate the destination before checking it against the client's
  prefixes. Both API and writer reject protected paths and scope escapes.
- Access status reports read, capture and update prefixes. Out-of-grant capture
  errors name the caller's allowed folders.
- The API role and both runtime boundaries require `If-None-Match` for creation.
  Existing conditional-update, policy/source protection and no-delete rules remain.

## Verification

- 108 cloud and infrastructure checks passed locally and in the managed release,
  including MCP create/read-back in all six roots and nested folders, narrow-grant
  boundaries, protected destinations, existing updates/conflicts and conditional IAM.
- All CloudFormation templates passed validation; GitHub validation checks passed.
- Deployed source: `b5974454ba3c62216acb8b6d0c5c985a6efff5a2`. Managed build
  `pkb-dev-pipeline:e25753c7-8ddf-4422-8771-3269b6716622` succeeded; bootstrap,
  foundation and application stacks all reached `UPDATE_COMPLETE`.
- Live health reports 0.4.0. Every bundled cloud source matches the reviewed source;
  both active Lambda functions use the same release digest.
- At the owner's explicit request, all five active grants were migrated with
  conditional atomic grant/audit writes. Consistent read-back confirmed full create
  and update prefixes. Expiry, original approval metadata and read prefixes stayed
  unchanged. This was a one-off owner-authorised migration, not an automatic renewal.
- Actual authenticated OpenClaw MCP: creation in Ideas, immediate read-back,
  revision-checked update and replay succeeded. Stale updates and Wiki, Archive and
  source-snapshot creation were denied. Another connected client fetched the saved
  updated revision. A local OAuth lease delayed the first attempt; retry succeeded.
- Persistence was verified independently of indexing. The last immediate check
  reported indexing pending; the optional remote Markdown activity appender remains
  disabled. The private vault activity log was updated locally and the generated
  verification note was copied locally with matching bytes and checked links.
- No original overnight idea was recovered or resaved as part of this change.
  General cloud/iCloud synchronisation was not verified. Private IDs, note content,
  credentials and grant snapshots remain outside the public repository.

AWS conditional-write enforcement follows the
[S3 documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html).
