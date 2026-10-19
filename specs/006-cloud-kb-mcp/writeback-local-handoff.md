# Writeback local continuation

**Date:** 20 October 2026. **Base:** `33725c1`.

The owner initially requested local completion only: no publication, deployment,
email or Git commit. The subsequent instruction authorises Git commits and
publication to GitHub. The later goal explicitly authorised deployment and fixes
until MCP writeback worked; that deployment and live proof are complete below.
Activity-log activation remains separate. Private deployment records, OAuth
credentials and note contents remain outside this repository.

The initial publication attempt was blocked by the managed session: the
checkout's `.git` was read-only, and the GitHub connector required unavailable
approval. That attempt made no remote changes. The owner subsequently enabled
local Git writes and network access. The reviewed portable commits were restored
on `codex/kb-capture-recovery` and publication resumed using the authenticated
Git CLI, on top of the grant-diagnostics branch for PR #6.

## Earlier stopped attempt

The earlier session recorded a successful application stack update and matching
API/ingestion code digests. Google-authenticated tool discovery exposed capture,
fetch, status, search and update tools. The owner approved reading the KB and
creating new notes only under `Resources/_Review/AI Learning/` for 90 days,
without permission to edit existing notes; the session recorded activation of
that grant. These are saved session observations, not a fresh remote check.

The subsequent live capture failed with `incompatible_embedding_contract`
before creating its note. No successful live write proof was obtained.
Inspection of the retained local release ZIP confirms it used the
`paragraph-1500-v1` embedding contract. The recorded published index used
`paragraph-400-v1`. The current source already uses 400-character chunks; do
not redeploy the retained prototype ZIP.

The clean checkout at continuation contained a newer, merged capture-only
implementation. It accepts an exact destination prefix and returns a flat
receipt. The older prototype accepted a symbolic `learning` destination and
used a different receipt shape. Use the current advertised tool schema after
any later deployment. Existing-note update/review remains outside this slice.

## Local corrections

- Permit lexical text lookup across an embedding-contract change while still
  checking snapshot integrity and agreement between descriptor and metadata.
  Vector/hybrid queries continue to require the configured embedding contract.
- Check for a prior operation before searching for duplicates. Identical retries
  still validate their request digest, including when indexing has caught up or
  search is unavailable. New operations continue to require duplicate checking.
- Share capture-prefix validation between grant provisioning, authorisation and
  the writer. Support `Ideas/` and the approved `Resources/_Review/AI Learning/`
  tree; each client must supply its exact granted prefix. Mirror those two
  trees in the foundation API role and both runtime permissions boundaries.
- Allow explicit grants up to 2,160 hours (90 days). Default remains 24 hours.
  Provisioning preserves active grants and does not create or extend any grant
  locally. A deployment must preserve the original approved expiry.
- Reject rendered Markdown larger than 24,576 UTF-8 bytes before reserving or
  writing anything. Read conflict-recovery objects with a size sentinel rather
  than silently hashing a truncated object. Conditional S3 creation remains
  mandatory, including crash recovery.
- Compare a persisted operation's content digest with the active snapshot for
  `indexed`, `pending` or `superseded`. If that inspection fails, retain the
  persistence receipt and return `not_checked`.
- Distinguish the durable operation record (`operation_audit: recorded`) from
  the separate vault log append (`activity_audit: pending` until confirmed).
  No runtime activity-log write permission was added.
- Retain the real socket HTTP proof and add an ASGI HTTP variant using the same
  exercise, so authentication, MCP protocol and cross-client fetch can be
  checked locally without binding a port.

## Follow-on local activity-log implementation

The owner asked to continue under the same local-only limits. The remaining
append logic now exists in `cloud_kb/activity.py`, integrated with capture
retries and disabled by default. It operates only on the existing
`Wiki/Activity Log.md`; it does not create a replacement log or expose a new
AI approval tool.

- Preserve existing bytes and user metadata; append a dated relative link to
  the unverified note, its content digest and a stable operation marker.
- Use the fetched ETag as the write precondition. Retry concurrent-edit
  conflicts up to three times, retaining the owner's intervening text.
- Read back the saved S3 revision before recording the audit receipt. A log
  write followed by a readback/state-update failure can be reconciled by an
  identical capture retry without appending again or changing the entry date.
- Keep the successful note receipt if auditing fails. Missing, full, invalid
  UTF-8 or conflicting log entries remain unchanged and report a specific
  audit error. `get_change_status` performs no audit writes.
- Require the current audit contract and a log revision before reporting
  `recorded`; legacy operation-only audit flags remain `pending`.
- Leave `PKB_ACTIVITY_LOG_ENABLED` absent/false. Only a separately authorised
  operator may enable it after adding reviewed, exact-path log permissions.
  No infrastructure permission or client grant was broadened for this component.
- Add its synthetic checks to the existing GitHub and CodeBuild test commands;
  neither pipeline was invoked.

## Local evidence

The synthetic proof uses generated credentials, simulated AWS responses and
synthetic Markdown. It verifies a capture under the approved review prefix,
immediate independent-client fetch, identical replay after duplicate discovery,
changed-content rejection, new-operation duplicate detection, replay during a
search outage, and authentication/grant denials. It does not prove live S3,
Google OAuth or asynchronous ingestion.

The normal suite's real HTTP case initially could not bind a loopback port
(`PermissionError: Operation not permitted`). That case remains enabled in the
normal suite and CI. Local results for the permitted cases are recorded below.

- **54 synthetic cloud checks passed** in the initial continuation, including the ASGI MCP proof; the single
  real socket case was excluded from this local run after its bind failed.
- **CloudFormation lint passed** for foundation, bootstrap, application and
  native-pipeline templates using `tools/lint_infra.py`.
- `git diff --check` passed. No cloud release was built or uploaded.

After the activity-log implementation, **65 socket-free synthetic cloud checks
passed**. They include concurrent owner edits, audit/state/readback failures,
permission denial, unchanged operation dates after recovery, disabled-by-default
configuration and read-only status. Python 3.12 source syntax and both CI YAML
files also passed local checks.

After the owner updated session permissions, **all 66 synthetic cloud checks
passed**, including the unchanged real loopback HTTP proof. No case was excluded
from that run. This resolves the local socket restriction; it does not establish
live S3 or Google acceptance.

The targeted socket-free protocol proof is reproducible with:

```sh
python -m unittest tests.test_cloud_http.CloudHTTPTests.test_mock_markdown_over_authenticated_asgi -v
```

## Outstanding

The [live deployment proof](writeback-deployment-proof.md) records the successful
CodeBuild release and connected-client write/read/index loop at source
`e0734e5088c0640dd03723b848d6c4e3459a8563`. It also confirms the original client
scope/expiry and Google binding were preserved. Existing connector arguments
work through explicitly bounded compatibility aliases.

The new-note MCP write goal is complete. Wider feature acceptance still includes:

1. Complete T049's live fetch through a second separately registered AI client.
   The owner-operator S3 read independently proved storage persistence; it is
   not a substitute for that separate OAuth/client interoperability case.
2. Authorise and activate the locally implemented activity-log append, add its
   exact-path backend IAM permission, then verify live append/readback/recovery.
   Leave it disabled until that separate authority is granted. The current
   create-only scope cannot edit an existing log.
3. Exact-revision existing-note updates and the owner review flow remain T016 /
   T017 work. They are not required for this bounded new-note capture proof and
   must not be exposed with the client's existing capture grant.

The local `personal-kb` MCP configuration remains disabled and retained for
rollback. It was inspected, not changed, during this continuation.
