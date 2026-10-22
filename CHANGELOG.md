# Changelog

## Unreleased

### Fixed

- Allow the scoped deployment role to create the MCP custom domain using API
  Gateway v2's array-valued IAM conditions and exact encoded tagging path.

## Cloud KB 0.4.0 — 2026-10-22

- Full write grants now permit new notes throughout Ideas, Projects, Areas,
  Resources, Personal Facts and Templates, including subfolders. Previously,
  these grants could update ordinary notes but create only in the learning
  review folder. Learning-only grants retain their narrower destination.
- Access status reports the caller's read, capture and update folders. Capture
  errors identify allowed destinations when a folder is outside the grant.
- AWS permissions require conditional creation or revision-checked updates.
  Wiki, policy and source-snapshot protections remain in place.
- Existing client grants require an explicit owner-authorised migration or
  browser approval of the full write option; deployments do not widen grants
  or extend their expiry automatically.

## Cloud KB 0.3.0

### Added

- Explicit ordinary-note update grants in the owner access page, with the same
  90/365-day renewal options. Previous create-only grants do not upgrade silently.
- `update_note` replaces a unique passage using a cloud fetch revision, with
  conditional writes, provenance, version history and idempotent retry recovery.
- Ordinary folders can be edited while canonical/policy/verified notes and source
  snapshots remain protected. File deletion is unavailable.

### Fixed

- An old indexed version of an updated note reports indexing pending while the
  latest saved content awaits indexing. Persistence remains a separate result.
- Cloud fetch revision is checked in JSON text and structured MCP responses.
- Allow bounded MCP/OAuth request bursts: live OpenClaw connection setup and
  tool calls exceeded the previous two-requests-per-second stage target.

## Cloud KB 0.2.1

### Fixed

- Start Google owner sign-in with the pinned FastMCP token-only upstream client;
  generate the standard Google authorization URL and PKCE challenge directly.
  Live rollout verification caught this before real owner approval was accepted.

## Cloud KB 0.2.0

### Added

- Owner Google sign-in page for approving, renewing and revoking access to an
  exact registered MCP client, without an AWS operator.
- One-year grants by default, with a 90-day option and explicit renewal.
- Recovery links on grant failures and an advance renewal indicator in
  `get_access_status`.
- Durable encrypted browser sessions, one-use approval forms and atomic
  conditional grant/audit records. Existing grants keep their current expiry.

New-note capture remains limited to `Resources/_Review/AI Learning/` on the
owner page. It does not grant existing-note editing or deletion.
