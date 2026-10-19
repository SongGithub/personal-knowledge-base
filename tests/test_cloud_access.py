"""Synthetic owner browser flow; no real Google identity or private KB data."""
from contextlib import asynccontextmanager
from copy import deepcopy
from decimal import Decimal
import json
import re
import secrets
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode, urlsplit

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from cryptography.fernet import Fernet
from fastmcp.exceptions import ToolError
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
import httpx2
from starlette.applications import Starlette
from starlette.routing import Route

from cloud_kb.access import COLLECTION, LOGIN_COOKIE, SESSION_COOKIE, STATE_PREFIX, OwnerAccess
from cloud_kb.auth import DynamoOAuthStore, GrantGate, google_provider
from cloud_kb.config import Settings
from cloud_kb.grants import CAPTURE_PREFIX, GrantDecisions, READ_PREFIXES


ORIGIN = "https://synthetic-kb.invalid"


class Table:
    name = "synthetic-control"

    def __init__(self):
        self.items = {}
        self.meta = SimpleNamespace(client=self)
        self.fail_transaction = False

    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        value = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": deepcopy(value)} if value else {}

    def put_item(self, *, Item):
        self.items[Item["PK"], Item["SK"]] = deepcopy(Item)

    def delete_item(self, *, Key, ReturnValues):
        return {"Attributes": self.items.pop((Key["PK"], Key["SK"]), None)}

    def transact_write_items(self, *, TransactItems, ClientRequestToken):
        assert ClientRequestToken
        for entry in TransactItems:
            put = entry["Put"]
            old = self.items.get((put["Item"]["PK"], put["Item"]["SK"]))
            condition = put["ConditionExpression"]
            valid = old is None
            if condition != "attribute_not_exists(PK)":
                valid = bool(old)
                names = put["ExpressionAttributeNames"]
                values = put["ExpressionAttributeValues"]
                for attr, val in re.findall(r"(#a\d+) = (:v\d+)", condition):
                    valid = valid and old.get(names[attr]) == values[val]
                if "attribute_not_exists(#version)" in condition:
                    valid = valid and "GrantVersion" not in old
            if not valid or self.fail_transaction:
                raise ClientError({"Error": {"Code": "TransactionCanceledException"}}, "TransactWriteItems")
        for entry in TransactItems:
            self.put_item(Item=entry["Put"]["Item"])


class Provider:
    _redirect_path = "/auth/callback"

    def __init__(self):
        self.clients = {"client-one": SimpleNamespace(client_id="client-one", client_name="<script>bad()</script>",
                                                     redirect_uris=["http://127.0.0.1:8989/callback"]),
                        "client-two": SimpleNamespace(client_id="client-two", client_name="Second client",
                                                     redirect_uris=["https://client.invalid/callback"])}
        self.exchange = AsyncMock(return_value={"access_token": "synthetic-google-secret"})
        self.authorization = None

    async def get_client(self, cid):
        return self.clients.get(cid)

    @asynccontextmanager
    async def _upstream_oauth_client(self):
        from authlib.integrations.httpx_client import AsyncOAuth2Client
        async with AsyncOAuth2Client(client_id="synthetic-google", client_secret="synthetic-secret") as oauth:
            oauth.fetch_token = self.exchange
            yield oauth


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.table, self.provider = Table(), Provider()
        self.encryption = Fernet.generate_key()
        self.portal = self.make_portal()
        self.portal.verifier.verify_token = AsyncMock(return_value=SimpleNamespace(
            claims={"sub": "owner", "email_verified": True}, expires_at=time.time() + 300))
        self.app = Starlette(routes=self.portal.routes() + [Route("/auth/callback", self.portal.handle)])
        self.http = httpx2.AsyncClient(transport=httpx2.ASGITransport(self.app), base_url=ORIGIN)

    def make_portal(self):
        store = FernetEncryptionWrapper(key_value=DynamoOAuthStore(self.table), fernet=Fernet(self.encryption))
        return OwnerAccess(provider=self.provider, store=store, table=self.table,
                           owner_sub="owner", base_url=ORIGIN, google_client_id="synthetic-google")

    async def asyncTearDown(self):
        await self.http.aclose()

    async def sign_in(self):
        login = await self.http.get("/access/login?client_id=client-one")
        flags = login.headers["set-cookie"].lower()
        self.assertTrue(all(flag in flags for flag in ("secure", "httponly", "samesite=lax", "path=/")))
        params = parse_qs(urlsplit(login.headers["location"]).query)
        callback = await self.http.get("/auth/callback?" + urlencode({"state": params["state"][0], "code": "synthetic-code"}))
        self.assertEqual(callback.status_code, 303, callback.text)
        replay = await self.http.get("/auth/callback?" + urlencode({"state": params["state"][0], "code": "synthetic-code"}))
        self.assertEqual(replay.status_code, 403)
        return params

    async def form(self, cid="client-one"):
        response = await self.http.get("/access?" + urlencode({"client_id": cid}))
        self.assertEqual(response.status_code, 200)
        nonce = re.search(r'name="nonce" value="([\w-]+)"', response.text)
        self.assertIsNotNone(nonce, response.text)
        return {"nonce": nonce[1], "action": "approve", "mode": "capture", "days": "365"}

    async def post(self, form, **kwargs):
        headers = kwargs.pop("headers", {"Origin": ORIGIN})
        return await self.http.post("/access", data=form, headers=headers, **kwargs)

    async def test_google_state_pkce_secure_cookie_and_durable_session(self):
        params = await self.sign_in()
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["redirect_uri"], [ORIGIN + "/auth/callback"])
        self.assertTrue(params["state"][0].startswith(STATE_PREFIX))
        self.assertEqual(set(params["scope"][0].split()), {"openid", "https://www.googleapis.com/auth/userinfo.email"})
        self.assertEqual(self.portal.verifier.audience, "synthetic-google")
        self.provider.exchange.assert_awaited_once()
        self.assertIn("code_verifier", self.provider.exchange.call_args.kwargs)
        form = await self.form()
        # A new instance decrypts sessions and forms after a cold start.
        self.portal.store = self.make_portal().store
        response = await self.post(form)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("synthetic-google-secret", json.dumps(list(self.table.items.values())))
        self.assertNotIn("synthetic-code", json.dumps(list(self.table.items.values())))
        grant = self.portal.grants.get("client-one")
        self.assertEqual(set(grant["Prefixes"]), set(READ_PREFIXES))
        self.assertEqual(grant["CapturePrefixes"], [CAPTURE_PREFIX])
        self.assertEqual(set(grant["Scopes"]), {"kb:read", "kb:capture"})
        self.assertEqual(grant["ExpiresAt"] - grant["CreatedAt"], 365 * 86400)
        self.assertEqual(len([key for key in self.table.items if key[0].startswith("GRANT_AUDIT#")]), 1)
        # The other client is still ungranted, even with the same owner session.
        self.assertIsNone(self.portal.grants.get("client-two"))

    async def test_read_only_renew_revoke_and_expired_grant_recovery(self):
        await self.sign_in()
        form = await self.form()
        form.update(mode="read", days="90")
        self.assertEqual((await self.post(form)).status_code, 200)
        before = self.portal.grants.get("client-one")
        self.assertEqual(before["Scopes"], ["kb:read"])
        self.assertEqual(before["CapturePrefixes"], [])
        self.assertEqual(before["ExpiresAt"] - before["CreatedAt"], 90 * 86400)
        self.assertEqual((await self.post(await self.form())).status_code, 200)
        renewed = self.portal.grants.get("client-one")
        self.assertGreater(renewed["ExpiresAt"], before["ExpiresAt"])
        form = await self.form()
        form["action"] = "revoke"
        self.assertEqual((await self.post(form)).status_code, 200)
        self.assertTrue(self.portal.grants.get("client-one")["Revoked"])
        self.assertEqual((await self.post(await self.form())).status_code, 200)
        expired = self.portal.grants.get("client-one")
        expired["ExpiresAt"] = int(time.time()) - 1
        self.table.put_item(Item=expired)
        self.assertEqual((await self.post(await self.form())).status_code, 200)

    async def test_no_owner_cookie_or_mcp_bearer_can_approve(self):
        response = await self.http.post("/access", data={"nonce": secrets.token_urlsafe(32)},
                                        headers={"Origin": ORIGIN, "Authorization": "Bearer synthetic-mcp"})
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.portal.grants.get("client-one"))
        response = await self.http.get("/access?client_id=client-one")
        self.assertIn("Sign in with Google", response.text)
        self.assertNotIn("bad()", response.text)

    async def test_state_cookie_and_owner_identity_are_required(self):
        login = await self.http.get("/access/login?client_id=client-one")
        params = parse_qs(urlsplit(login.headers["location"]).query)
        wrong = await self.http.get("/auth/callback?state=" + STATE_PREFIX + secrets.token_urlsafe(32) + "&code=bad")
        self.assertEqual(wrong.status_code, 403)
        self.provider.exchange.assert_not_awaited()
        self.portal.verifier.verify_token.return_value.claims["sub"] = "another-owner"
        response = await self.http.get("/auth/callback?" + urlencode({"state": params["state"][0], "code": "synthetic"}))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(SESSION_COOKIE, self.http.cookies)
        self.assertIsNone(self.portal.grants.get("client-one"))

    async def test_invalid_csrf_origin_duration_and_duplicate_fields(self):
        await self.sign_in()
        form = await self.form()
        self.assertEqual((await self.post(form, headers={"Origin": "https://attacker.invalid"})).status_code, 403)
        self.assertEqual((await self.post({**form, "nonce": secrets.token_urlsafe(32)})).status_code, 403)
        self.assertEqual((await self.post({**form, "days": "366"})).status_code, 400)
        self.assertEqual((await self.post({**form, "mode": "update"})).status_code, 400)
        dup = await self.http.post("/access", content=urlencode(form) + "&days=90",
                                   headers={"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(dup.status_code, 400)
        self.assertIsNone(self.portal.grants.get("client-one"))
        self.assertEqual((await self.post(form)).status_code, 200)
        self.assertEqual((await self.post(form)).status_code, 403)

    async def test_expired_login_and_unverified_or_expired_google_identity_are_denied(self):
        for identity in (None, SimpleNamespace(claims={"sub": "owner", "email_verified": False}, expires_at=time.time() + 300),
                         SimpleNamespace(claims={"sub": "owner", "email_verified": True}, expires_at=time.time() - 1)):
            self.http.cookies.clear()
            self.portal.verifier.verify_token.return_value = identity
            login = await self.http.get("/access/login?client_id=client-one")
            state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
            response = await self.http.get("/auth/callback?" + urlencode({"state": state, "code": "synthetic"}))
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(SESSION_COOKIE, self.http.cookies)
        login = await self.http.get("/access/login?client_id=client-one")
        state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
        key = "login:" + state.removeprefix(STATE_PREFIX)
        pending = await self.portal.load(key)
        pending["expires_at"] = int(time.time()) - 1
        await self.portal.store.put(key, pending, collection=COLLECTION)
        response = await self.http.get("/auth/callback?" + urlencode({"state": state, "code": "synthetic"}))
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.portal.grants.get("client-one"))

    async def test_expired_forms_sessions_and_other_browser(self):
        await self.sign_in()
        form = await self.form()
        expired = await self.portal.load("form:" + form["nonce"])
        expired["expires_at"] = int(time.time()) - 1
        await self.portal.store.put("form:" + form["nonce"], expired, collection=COLLECTION)
        self.assertEqual((await self.post(form)).status_code, 403)
        form = await self.form()
        token = secrets.token_urlsafe(32)
        await self.portal.save("session:" + token, {"owner_sub": "owner"}, 60)
        self.http.cookies.clear()
        self.http.cookies.set(SESSION_COOKIE, token, domain="synthetic-kb.invalid", path="/")
        self.assertEqual((await self.post(form)).status_code, 403)
        await self.portal.store.delete("session:" + token, collection=COLLECTION)
        self.assertEqual((await self.post(form)).status_code, 403)

    async def test_stale_tabs_registration_changes_and_atomic_failure(self):
        await self.sign_in()
        first, second = await self.form(), await self.form()
        self.assertEqual((await self.post(first)).status_code, 200)
        self.assertEqual((await self.post(second)).status_code, 409)
        form = await self.form()
        self.provider.clients["client-one"].redirect_uris = ["https://changed.invalid/callback"]
        self.assertEqual((await self.post(form)).status_code, 409)
        form = await self.form()
        previous = self.portal.grants.get("client-one")
        self.table.fail_transaction = True
        self.assertEqual((await self.post(form)).status_code, 409)
        self.assertEqual(self.portal.grants.get("client-one"), previous)
        self.assertEqual(len([key for key in self.table.items if key[0].startswith("GRANT_AUDIT#")]), 1)

    async def test_headers_escaping_unknown_client_and_logout(self):
        await self.sign_in()
        response = await self.http.get("/access?client_id=client-one")
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", response.text)
        self.assertNotIn("<script>", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["referrer-policy"], "same-origin")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("form-action 'self'", response.headers["content-security-policy"])
        self.assertEqual((await self.http.get("/access?client_id=unknown")).status_code, 404)
        form = await self.form()
        logout = await self.http.post("/access/logout", data={"nonce": form["nonce"]}, headers={"Origin": ORIGIN})
        self.assertEqual(logout.status_code, 200)
        self.assertNotIn(SESSION_COOKIE, self.http.cookies)
        self.assertEqual((await self.post(form)).status_code, 403)

    async def test_real_provider_routes_are_public_but_decisions_still_require_owner(self):
        from cloud_kb.api import create_app
        settings = Settings(ORIGIN, "vault", "index", "table", "owner", "secret",
                            ("https://client.invalid/callback",))
        provider = google_provider(settings, {"google_client_id": "synthetic-google",
                                  "google_client_secret": "synthetic-secret",
                                  "jwt_signing_key": "synthetic-signing-key-long-enough-32",
                                  "storage_encryption_key": Fernet.generate_key().decode()}, self.table)
        app = create_app(auth_provider=provider, gate=GrantGate(self.table, "owner", ORIGIN),
                         notes=None, search=None, base_url=ORIGIN)
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app), base_url=ORIGIN) as http:
            self.assertEqual((await http.get("/access?client_id=client-one")).status_code, 200)
            callback = await http.get("/auth/callback?state=" + STATE_PREFIX + secrets.token_urlsafe(32) + "&code=bad")
            self.assertEqual(callback.status_code, 403)
            denied = await http.post("/access", data={"nonce": "fake"}, headers={"Origin": ORIGIN})
            self.assertEqual(denied.status_code, 403)


class PolicyTests(unittest.TestCase):
    def test_gate_error_and_status_offer_renewal_url(self):
        table = Table()
        token = SimpleNamespace(client_id="client-one", claims={"sub": "owner"}, expires_at=time.time() + 300)
        gate = GrantGate(table, "owner", ORIGIN)
        with self.assertRaises(ToolError) as error:
            gate.capture_prefixes(token)
        self.assertIn(ORIGIN + "/access?client_id=client-one", str(error.exception))
        self.assertTrue(gate.status(token)["access_management"]["renewal_required"])
        grants = GrantDecisions(table, "owner")
        grants.decide("client-one", previous=None, action="approve", mode="capture", days=365)
        self.assertFalse(gate.status(token)["access_management"]["renewal_required"])
        self.assertEqual(gate.capture_prefixes(token), [CAPTURE_PREFIX])
        old = grants.get("client-one")
        grants.decide("client-one", previous=old, action="revoke", mode="capture", days=365)
        with self.assertRaises(ValueError):
            grants.decide("client-one", previous=old, action="approve", mode="capture", days=365)
        with self.assertRaises(ToolError):
            gate.read_prefixes(token)

    def test_factory_adds_portal_without_removing_standard_oauth(self):
        settings = Settings(ORIGIN, "vault", "index", "table", "owner", "secret",
                            ("https://client.invalid/callback",))
        provider = google_provider(settings, {"google_client_id": "synthetic-google",
                                  "google_client_secret": "synthetic-secret",
                                  "jwt_signing_key": "synthetic-signing-key-long-enough-32",
                                  "storage_encryption_key": Fernet.generate_key().decode()}, Table())
        paths = [route.path for route in provider.get_routes("/mcp")]
        self.assertTrue({"/authorize", "/token", "/consent", "/auth/callback", "/access", "/access/login"} <= set(paths))

    def test_real_dynamodb_resource_serializes_atomic_decision(self):
        dynamodb = boto3.resource("dynamodb", region_name="ap-southeast-2",
                                 aws_access_key_id="synthetic", aws_secret_access_key="synthetic")
        table = dynamodb.Table("synthetic-control")
        with Stubber(table.meta.client) as stub:
            stub.add_response("transact_write_items", {})
            result = GrantDecisions(table, "owner").decide("client-one", previous=None,
                                                          action="approve", mode="capture", days=365)
            self.assertEqual(result["CapturePrefixes"], [CAPTURE_PREFIX])
            stub.assert_no_pending_responses()

    def test_legacy_decimal_grants_can_be_renewed_conditionally(self):
        table = Table()
        old = {"PK": "GRANT#owner", "SK": "CLIENT#client-one", "Revoked": False,
               "CreatedAt": Decimal(1), "ExpiresAt": Decimal(int(time.time()) + 60),
               "Scopes": ["kb:read"], "Prefixes": ["Ideas/"]}
        table.put_item(Item=old)
        result = GrantDecisions(table, "owner").decide("client-one", previous=old,
                                                       action="approve", mode="read", days=365)
        self.assertEqual(result["Scopes"], ["kb:read"])
        self.assertIn("GrantVersion", result)


if __name__ == "__main__":
    unittest.main()
