"""Google owner browser approval, renewal and revocation; never an MCP tool."""
import asyncio
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from html import escape
import hashlib
import logging
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode

from fastmcp.server.auth.providers.google import GoogleTokenVerifier
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from cloud_kb.grants import CAPTURE_PREFIX, GRANT_DAYS, GrantDecisions, digest
from cloud_kb.storage import CAPTURE_ROOTS, UPDATE_ROOTS


SESSION_COOKIE = "__Host-kb-owner"
LOGIN_COOKIE = "__Host-kb-login"
STATE_PREFIX = "kb-access."
COLLECTION = "kb-owner-access-v1"
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]
SESSION_SECONDS = 900
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")
CLIENT_RE = re.compile(r"[A-Za-z0-9._:-]{1,256}\Z")
logger = logging.getLogger(__name__)


class AccessError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def page(title, body, status=200):
    # All interpolated metadata must be escaped at the call site. No JavaScript,
    # external assets, analytics, credentials in URLs or private KB text.
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · KB access</title><style>
body{{font:17px/1.55 system-ui,sans-serif;color:#172b35;background:#f2f5f3;margin:0}}
main{{max-width:660px;margin:6vh auto;background:white;padding:32px;border-radius:16px}}
h1{{line-height:1.2}}h2{{font-size:1.15rem;margin-top:28px}}
code{{overflow-wrap:anywhere}}label{{display:block;margin:16px 0}}
select,input,button{{font:inherit;padding:10px;max-width:100%;box-sizing:border-box}}
button{{background:#155c48;color:white;border:0;border-radius:6px;cursor:pointer}}
button[value=revoke]{{background:#8b3333;margin-left:12px}}
.muted{{color:#53656c}}a{{color:#155c48}}li{{margin:6px 0}}
@media(max-width:720px){{main{{margin:12px;padding:22px}}}}
</style><main><p class="muted">Personal knowledge base</p>
<h1>{escape(title)}</h1>{body}</main></html>"""
    return HTMLResponse(html, status_code=status, headers={
        "Cache-Control": "no-store", "Pragma": "no-cache",
        # no-referrer turns Origin into "null" on browser form POSTs. Keep
        # same-origin form provenance while suppressing cross-origin referrers.
        "Referrer-Policy": "same-origin", "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY", "Strict-Transport-Security": "max-age=31536000",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                                   "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    })


def redirect(url):
    response = RedirectResponse(url, status_code=303)
    response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    return response


def cookie(response, name, value, seconds):
    response.set_cookie(name, value, max_age=seconds, secure=True,
                        httponly=True, samesite="lax", path="/")


def one(values, name):
    result = values.getlist(name)
    if len(result) != 1:
        raise AccessError("Invalid request. Open the access link again.")
    return result[0]


def client_id(value):
    if not isinstance(value, str) or not CLIENT_RE.fullmatch(value):
        raise AccessError("A valid OAuth client ID is required.")
    return value


def registration(client):
    """Only public registration metadata; the client secret is never rendered."""
    return {"id": client.client_id, "name": client.client_name,
            "redirects": [str(uri) for uri in client.redirect_uris]}


class OwnerAccess:
    def __init__(self, *, provider, store, table, owner_sub, base_url, google_client_id):
        self.provider, self.store = provider, store
        self.grants = GrantDecisions(table, owner_sub)
        self.owner_sub, self.base_url = owner_sub, base_url.rstrip("/")
        self.callback_uri = self.base_url + provider._redirect_path
        self.google_client_id = google_client_id
        self.verifier = GoogleTokenVerifier(required_scopes=SCOPES, audience=google_client_id,
                                            cache_ttl_seconds=0, timeout_seconds=6)

    def routes(self):
        return [Route("/access", self.handle, methods=["GET", "POST"]),
                Route("/access/login", self.handle, methods=["GET"]),
                Route("/access/logout", self.handle, methods=["POST"])]

    async def save(self, key, value, seconds):
        await self.store.put(key, {**value, "expires_at": int(time.time()) + seconds},
                             collection=COLLECTION, ttl=seconds)

    async def load(self, key):
        value = await self.store.get(key, collection=COLLECTION)
        return value if value and value.get("expires_at", 0) > time.time() else None

    async def consume(self, key):
        if not await self.store.delete(key, collection=COLLECTION):
            raise AccessError("This request was already used. Open the access page again.", 409)

    async def session(self, request):
        token = request.cookies.get(SESSION_COOKIE, "")
        if not TOKEN_RE.fullmatch(token):
            return None
        value = await self.load("session:" + token)
        if value and value.get("owner_sub") == self.owner_sub:
            return token
        return None

    async def handle(self, request):
        try:
            if request.url.path == "/access/login":
                return await self.login(request)
            if request.url.path == self.provider._redirect_path:
                return await self.callback(request)
            if request.method == "POST":
                return await self.decide(request)
            return await self.show(request)
        except AccessError as error:
            return page("Access request needs attention", f"<p>{escape(error.message)}</p>", error.status)
        except Exception as error:
            # Provider exception text may contain an OAuth code or credential.
            logger.warning("Owner access unavailable (%s)", type(error).__name__)
            return page("Access temporarily unavailable",
                        "<p>No access change was confirmed. Reopen the access link and try again.</p>", 503)

    async def get_client(self, cid):
        client = await self.provider.get_client(cid)
        if client is None:
            raise AccessError("This OAuth client is no longer registered. Reconnect it and use its new access link.", 404)
        return registration(client)

    async def login(self, request):
        cid = client_id(one(request.query_params, "client_id"))
        # Registration details are shown only after owner sign-in. The login
        # request cannot mutate a grant, even if initiated from another site.
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        await self.save("login:" + state, {"client_id": cid, "verifier": verifier}, 600)
        # FastMCP's pinned upstream client supports token exchange only. Build
        # Google's standard authorization URL without a legacy httpx client.
        challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "response_type": "code", "client_id": self.google_client_id,
            "state": STATE_PREFIX + state, "redirect_uri": self.callback_uri,
            "scope": " ".join(SCOPES), "code_challenge": challenge,
            "code_challenge_method": "S256", "prompt": "select_account", "access_type": "online",
        })
        response = redirect(url)
        cookie(response, LOGIN_COOKIE, state, 600)
        return response

    async def callback(self, request):
        state = one(request.query_params, "state")
        value = state.removeprefix(STATE_PREFIX)
        if (not state.startswith(STATE_PREFIX) or not TOKEN_RE.fullmatch(value) or
                not secrets.compare_digest(value, request.cookies.get(LOGIN_COOKIE, ""))):
            raise AccessError("Google sign-in did not match this browser. Start again.", 403)
        pending = await self.load("login:" + value)
        if not pending:
            raise AccessError("Google sign-in expired. Open the access link again.", 403)
        code = one(request.query_params, "code")
        if not code or len(code) > 4096:
            raise AccessError("Google sign-in was not completed.")
        await self.consume("login:" + value)
        async with self.provider._upstream_oauth_client() as oauth:
            tokens = await oauth.fetch_token(
                url="https://oauth2.googleapis.com/token", code=code,
                redirect_uri=self.callback_uri, code_verifier=pending["verifier"])
        verified = await self.verifier.verify_token(tokens["access_token"])
        if (verified is None or verified.claims.get("sub") != self.owner_sub or
                verified.expires_at is None or verified.expires_at <= time.time() or
                verified.claims.get("email_verified") not in (True, "true")):
            raise AccessError("Only the configured Google owner can manage KB access.", 403)
        # No Google access/refresh token is retained in this owner session.
        session = secrets.token_urlsafe(32)
        await self.save("session:" + session, {"owner_sub": self.owner_sub}, SESSION_SECONDS)
        previous = request.cookies.get(SESSION_COOKIE, "")
        if TOKEN_RE.fullmatch(previous):
            await self.store.delete("session:" + previous, collection=COLLECTION)
        response = redirect(self.url(pending["client_id"]))
        cookie(response, SESSION_COOKIE, session, SESSION_SECONDS)
        response.delete_cookie(LOGIN_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        return response

    def url(self, cid):
        return self.base_url + "/access?" + urlencode({"client_id": cid})

    async def show(self, request):
        if "client_id" not in request.query_params:
            return page("Manage client access", '<p>Use the access link supplied by your KB connector, '
                        'or enter its OAuth client ID.</p><form action="/access" method="get">'
                        '<label>OAuth client ID <input name="client_id" required maxlength="256"></label>'
                        '<button>Continue</button></form>')
        cid = client_id(one(request.query_params, "client_id"))
        session = await self.session(request)
        if not session:
            link = "/access/login?" + urlencode({"client_id": cid})
            return page("Approve KB access", '<p>Sign in as the KB owner to review this client’s access.</p>'
                        f'<p>OAuth client ID: <code>{escape(cid)}</code></p>'
                        f'<p><a href="{escape(link, quote=True)}">Sign in with Google</a></p>'
                        '<p class="muted">Signing in does not grant access. You will choose the permissions next.</p>')
        client = await self.get_client(cid)
        grant = await asyncio.to_thread(self.grants.get, cid)
        nonce = secrets.token_urlsafe(32)
        await self.save("form:" + nonce, {"session": digest(session), "client_id": cid,
                        "registration": digest(client), "grant": digest(grant)}, 600)
        current = "No grant yet."
        if grant:
            expiry = datetime.fromtimestamp(int(grant.get("ExpiresAt", 0)), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            state = "Revoked" if grant.get("Revoked", True) else (
                "Expired" if int(grant.get("ExpiresAt", 0)) <= time.time() else "Active")
            current = f"{state}. Expires {expiry}. Scopes: {', '.join(grant.get('Scopes', []))}."
        callbacks = "".join(f"<li><code>{escape(uri)}</code></li>" for uri in client["redirects"])
        selected = "write" if grant and "kb:update" in grant.get("Scopes", []) else (
            "capture" if grant and "kb:capture" in grant.get("Scopes", []) else "read")
        choices = [("read", "Read only"), ("capture", "Read and create learning notes"),
                   ("write", "Read, create and update ordinary notes")]
        options = "".join('<option value="' + value + '"' + (" selected" if value == selected else "") +
                          '>' + label + '</option>' for value, label in choices)
        revoke = '<button name="action" value="revoke">Revoke access</button>' if grant else ""
        return page("Review client access", f"<h2>{escape(client['name'] or 'Unnamed client')}</h2>"
                    f"<p>OAuth client ID: <code>{escape(cid)}</code></p>"
                    '<p class="muted">The client supplies its name. Check its ID and callback before approving.</p>'
                    f"<ul>{callbacks}</ul><p>{escape(current)}</p>"
                    '<h2>Permissions</h2><ul><li>Read all configured KB folders.</li>'
                    f'<li>The learning-only option creates notes in <code>{escape(CAPTURE_PREFIX)}</code>.</li>'
                    '<li>The create and update option also allows new notes in: ' + escape(", ".join(CAPTURE_ROOTS)) + ' and their subfolders.</li>'
                    '<li>Optional ordinary-note updates in: ' + escape(", ".join(UPDATE_ROOTS)) + '.</li>'
                    '<li>Updates require a fetched revision and an exact passage match. '
                    'Wiki, policies, verified notes and source snapshots remain protected.</li>'
                    '<li>No permission to delete files.</li></ul>'
                    '<form method="post" action="/access">'
                    f'<input type="hidden" name="nonce" value="{nonce}">'
                    f'<label>Access <select name="mode">{options}</select></label>'
                    '<label>Valid for <select name="days"><option value="365" selected>1 year (365 days)</option>'
                    '<option value="90">90 days</option></select> from approval</label>'
                    f'<button name="action" value="approve">Approve / renew access</button>{revoke}</form>'
                    '<p class="muted">You can renew or revoke using this link. Grants do not renew automatically.</p>'
                    '<form method="post" action="/access/logout">'
                    f'<input type="hidden" name="nonce" value="{nonce}"><button>Sign out</button></form>')

    async def decide(self, request):
        if request.headers.get("origin") != self.base_url:
            raise AccessError("The access form must be submitted from this site.", 403)
        session = await self.session(request)
        if not session:
            raise AccessError("Your owner session expired. Reopen the access link and sign in.", 403)
        if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/x-www-form-urlencoded":
            raise AccessError("Invalid access form.")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 2048:
                raise AccessError("Access form is too large.", 413)
        try:
            form = parse_qs(raw.decode("utf-8"), strict_parsing=True, max_num_fields=4)
        except (ValueError, UnicodeError):
            raise AccessError("Invalid access form.") from None
        if any(len(values) != 1 for values in form.values()):
            raise AccessError("Invalid access form.")
        form = {key: values[0] for key, values in form.items()}
        nonce = form.get("nonce", "")
        if not TOKEN_RE.fullmatch(nonce):
            raise AccessError("Invalid access form.", 403)
        pending = await self.load("form:" + nonce)
        if not pending or not secrets.compare_digest(pending["session"], digest(session)):
            raise AccessError("Access form expired or belongs to another browser. Reopen the access link.", 403)
        if request.url.path == "/access/logout":
            if set(form) != {"nonce"}:
                raise AccessError("Invalid access form.")
            await self.consume("form:" + nonce)
            await self.store.delete("session:" + session, collection=COLLECTION)
            response = page("Signed out", "<p>Your KB owner session has ended.</p>")
            response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
            return response
        if (set(form) != {"nonce", "action", "mode", "days"} or
                form["action"] not in {"approve", "revoke"} or
                form["mode"] not in {"read", "capture", "write"} or form["days"] not in {str(day) for day in GRANT_DAYS}):
            raise AccessError("Choose one of the displayed access options.")
        cid = pending["client_id"]
        client = await self.get_client(cid)
        previous = await asyncio.to_thread(self.grants.get, cid)
        if digest(client) != pending["registration"] or digest(previous) != pending["grant"]:
            raise AccessError("This client or its access changed. Reopen the access link before deciding.", 409)
        await self.consume("form:" + nonce)
        try:
            result = await asyncio.to_thread(self.grants.decide, cid, previous=previous,
                                            action=form["action"], mode=form["mode"], days=int(form["days"]))
        except ValueError:
            raise AccessError("Access changed while you were deciding. Reopen the access link.", 409) from None
        title = "Access revoked" if result["Revoked"] else "Access approved"
        message = ("This client can no longer read or create KB notes." if result["Revoked"] else
                   "Return to your AI client and retry the KB operation.")
        return page(title, f'<p>The decision has been saved. {message}</p>'
                    f'<p><a href="{escape(self.url(cid), quote=True)}">Review, renew or revoke this client</a></p>')
