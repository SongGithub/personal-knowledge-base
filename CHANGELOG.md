# Changelog

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
