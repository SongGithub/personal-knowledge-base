# Owner self-service KB access

Owner request, 2026-10-20: missing or expired client grants must be recoverable
by the owner without an operator editing DynamoDB. The owner approved a one-year
default, automated security/browser checks and deployment in this conversation.

## Contract

- Missing, revoked, expired or insufficient grants give an HTTPS owner approval
  URL bound to the exact OAuth client ID. `get_access_status` also reports this
  URL and expiry, including an advance renewal indication.
- `/access?client_id=...` offers Google owner sign-in and an explicit decision
  for the registered client. Show its ID, self-reported name and callbacks.
  A matching display name never transfers an existing grant to a new ID.
- The owner chooses read-only or read plus new-note capture, for 90 or 365 days
  from approval. Default: 365 days. Capture is restricted to
  `Resources/_Review/AI Learning/`; existing-note edits are never granted here.
  Existing grants retain their expiry until the owner explicitly renews.
- Renewal and revocation use the same page. Expired/revoked clients may request
  recovery but cannot approve themselves. An MCP access token conveys no owner
  approval authority. No automatic extension or copying to another client.
- Reuse the existing Google callback, credentials and stable owner binding;
  require browser-bound state, PKCE, verified Google audience/subject/expiry,
  short encrypted sessions, CSRF protection, escaped HTML and no-store headers.
- Decisions bind the displayed registration and grant revision. One-use forms
  and conditional atomic grant/audit writes reject stale/replayed decisions.
  Grant data remain outside disposable search indexes and public artifacts.
- Service instances may restart between every step; all transient state is
  encrypted in the existing durable OAuth store with explicit expiry checks.
- Retry the original MCP operation after approval, preserving its operation ID.
  New client registrations require a new owner decision; no operator is needed.

## Delivery evidence

- Local cloud suite: **92 checks passed**, including 14 owner-access checks.
  Coverage includes Google state/PKCE, wrong owner/unverified/expired identity,
  session and form expiry, cross-browser CSRF, duplicate fields, bounded grant
  duration, missing browser session despite an MCP bearer token, replay, stale
  tabs, registration changes, atomic failure, renewal, revocation and recovery.
- Mutation review: inverting the Origin check caused the security test to fail;
  the original implementation was restored and the complete suite passed.
- Infrastructure lint passed. `pip-audit` checked all 75 locked runtime packages:
  zero known vulnerabilities, no skipped packages; no dependencies changed.
- Real browser, synthetic in-memory control store: approve a one-year capture
  grant, reopen and verify expiry/scopes, renew and revoke all passed. Console:
  no warnings/errors. This exposed and fixed a browser form Origin issue:
  page `Referrer-Policy: same-origin` preserves same-site POST provenance while
  suppressing cross-origin referrers. Origin/CSRF checks remain enforced.
- This simulated Google flow is not evidence of a real owner login or approval.
  Deployment and real owner sign-in evidence remain pending below.

## Sources

- [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)
- [Google web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)
- Pinned FastMCP 4.1.0 `GoogleTokenVerifier`, `OAuthProxy.get_routes` and upstream
  OAuth client implementation; the standard MCP OAuth flow stays enabled.
