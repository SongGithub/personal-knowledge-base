# Ordinary note updates

Owner request, 2026-10-20: write access must support editing existing notes,
including adding a reference to an ordinary Area note. The owner chose **all
ordinary KB folders** for the update scope. Existing read/create approvals must
not acquire update permission silently.

## Contract

- Add `kb:update` and explicit `UpdatePrefixes` to owner-managed grants. The
  browser offers read + create + update for 90 or 365 days. Supported ordinary
  roots: Ideas, Projects, Areas, Resources, Personal Facts and Templates.
- Wiki, AGENTS/policy notes, archived/source snapshots, raw Clippings and notes
  marked canonical/binding/verified/source remain protected (`review_required`
  or `forbidden`). This slice does not implement canonical owner review.
- `fetch_note` returns a top-level `revision` in both structured and JSON text
  responses. It always has in the cloud implementation; the enabled legacy
  local reader lacks it. Disable that local connection, retaining rollback
  configuration, so clients use the authoritative cloud reader.
- `update_note(operation_id, path, expected_revision, old_text, new_text,
  origin, date, evidence_links, inference_labels)` replaces exactly one matching
  passage. Reject stale versions, ambiguous passages, oversized notes, protected
  content/authority changes and out-of-scope paths. Preserve all unrelated bytes,
  custom S3 metadata and recoverable S3 versions; append dated provenance.
- Verify the fetched S3 revision, then condition the PUT on its ETag. An ETag
  guards content, not a version ID: an external identical-byte rewrite during
  the narrow read/PUT race is content-equivalent, not exact version-ID CAS.
  Never claim S3 supports a version-ID conditional PUT.
- Durable operation IDs bind the full request to one owner/client. Identical
  retries return the same receipt; changed requests are rejected. Recover lost
  acknowledgements using operation metadata/current or bounded S3 version reads.
  Do not confuse unknown persistence, a saved note, or pending indexing.
- Runtime write/history-list permissions cover supported ordinary paths. Tool
  code still checks grant/read prefixes and protected note content. No delete,
  source-snapshot overwrite, AGENTS or Wiki edit authority is added.
- Existing S3 notifications drive indexing after updates. Status uses the saved
  digest, and immediate fetch works while indexing is pending. Durable operation
  audit and Markdown activity-log state remain separately reported.

## Sources

- [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
- [PutObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html)

## Acceptance

Implementation, synthetic conflicts/recovery/scope checks, wire revision checks,
browser verification and deployment evidence will be recorded as they complete.
No financial note text or private client identifiers belong in this repository.

- Local cloud suite: 104 checks passed, including 10 updater/wire checks, the
  explicit write-grant/downgrade check and conditional IAM/history-prefix checks.
- Actual authenticated OpenClaw client: cloud fetch returns a revision in both
  structured and JSON text content. The configured legacy local reader omitted
  it; that entry is now disabled, retained for rollback, and MCP caches reloaded.
- Synthetic browser: selecting the new write option saves `kb:update` alongside
  read/capture, ordinary prefixes and the chosen one-year term; no console errors.
- Mutation review detects an inverted revision check. Infrastructure lint
  passed. PyYAML 6.0.3 is now an explicit direct dependency; its existing locked
  Linux wheel/hash is unchanged. No new runtime package was introduced.
- The owner explicitly requested updates for the current client and selected
  all ordinary folders. Deployment may add only that update capability to this
  already registered/granted client, preserving expiry and other approved
  scopes, with an atomic decision audit. Future clients use the owner page.
- Live deployment and a synthetic authenticated cloud update remain pending.
