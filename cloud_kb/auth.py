"""Google OAuth broker, durable encrypted state and per-client backend grants."""
import asyncio
import hashlib
import json
import time
from urllib.parse import urlencode

from cryptography.fernet import Fernet
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.google import GoogleProvider
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from cloud_kb.storage import validate_capture_prefix, validate_update_prefix


class DynamoOAuthStore:
    """AsyncKeyValue protocol mapped to the foundation PK/SK table, no scans."""
    def __init__(self, table):
        self.table = table

    @staticmethod
    def _key(key, collection):
        return {"PK": "OAUTH#" + hashlib.sha256((collection or "default").encode()).hexdigest(),
                "SK": hashlib.sha256(key.encode()).hexdigest()}

    async def ttl(self, key, *, collection=None):
        response = await asyncio.to_thread(self.table.get_item, Key=self._key(key, collection), ConsistentRead=True)
        item = response.get("Item")
        if not item:
            return None, None
        remaining = float(item["ExpiresAt"]) - time.time() if "ExpiresAt" in item else None
        if remaining is not None and remaining <= 0:
            return None, None
        return json.loads(item["Payload"]), remaining

    async def get(self, key, *, collection=None):
        return (await self.ttl(key, collection=collection))[0]

    async def put(self, key, value, *, collection=None, ttl=None):
        item = {**self._key(key, collection), "Payload": json.dumps(dict(value))}
        if ttl is not None:
            item["ExpiresAt"] = int(time.time() + float(ttl))
        await asyncio.to_thread(self.table.put_item, Item=item)

    async def delete(self, key, *, collection=None):
        response = await asyncio.to_thread(self.table.delete_item, Key=self._key(key, collection), ReturnValues="ALL_OLD")
        return bool(response.get("Attributes"))

    async def get_many(self, keys, *, collection=None):
        return [await self.get(key, collection=collection) for key in keys]

    async def ttl_many(self, keys, *, collection=None):
        return [await self.ttl(key, collection=collection) for key in keys]

    async def put_many(self, keys, values, *, collection=None, ttl=None):
        if len(keys) != len(values):
            raise ValueError("Mismatched OAuth storage keys/values")
        for key, value in zip(keys, values):
            await self.put(key, value, collection=collection, ttl=ttl)

    async def delete_many(self, keys, *, collection=None):
        return sum([await self.delete(key, collection=collection) for key in keys])


class BoundGoogleProvider(GoogleProvider):
    """Preserve the verified downstream MCP client identity for grant checks."""
    async def verify_token(self, token):
        verified = await super().verify_token(token)
        if verified is None:
            return None
        # Super verified this service's signed reference token and its upstream
        # Google token. Do not accept a client identity from request arguments.
        payload = self.jwt_issuer.verify_token(token)
        client_id = payload.get("client_id")
        if not client_id:
            return None
        return verified.model_copy(update={"client_id": client_id})

    def get_routes(self, mcp_path=None):
        routes = super().get_routes(mcp_path)
        access = getattr(self, "owner_access", None)
        return routes + access.routes() if access is not None else routes

    async def _handle_idp_callback(self, request):
        from cloud_kb.access import STATE_PREFIX
        if request.query_params.get("state", "").startswith(STATE_PREFIX):
            return await self.owner_access.handle(request)
        return await super()._handle_idp_callback(request)


def google_provider(settings, secret, table):
    from cloud_kb.access import OwnerAccess
    store = FernetEncryptionWrapper(
        key_value=DynamoOAuthStore(table), fernet=Fernet(secret["storage_encryption_key"].encode()),
    )
    provider = BoundGoogleProvider(
        client_id=secret["google_client_id"], client_secret=secret["google_client_secret"],
        base_url=settings.base_url,
        required_scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
        jwt_signing_key=secret["jwt_signing_key"],
        client_storage=store,
        allowed_client_redirect_uris=list(settings.client_redirect_uris),
        require_authorization_consent=True, enable_cimd=False,
        cache_ttl_seconds=0, fastmcp_access_token_expiry_seconds=300,
    )
    provider.owner_access = OwnerAccess(provider=provider, store=store, table=table,
                                      owner_sub=settings.owner_sub, base_url=settings.base_url,
                                      google_client_id=secret["google_client_id"])
    return provider


class GrantGate:
    """Deny access unless the verified owner holds a live grant for this client."""

    def __init__(self, table, owner_sub, base_url=None):
        self.table, self.owner_sub, self.base_url = table, owner_sub, base_url

    def access_url(self, client_id):
        if self.base_url and client_id:
            return self.base_url.rstrip("/") + "/access?" + urlencode({"client_id": client_id})
        return None

    def recovery(self, client_id):
        url = self.access_url(client_id)
        return "; owner approval/renewal: " + url if url else ""

    @staticmethod
    def _subject(token):
        # FastMCP exposes the verified upstream identity as both
        # AccessToken.subject and claims["sub"]. Accept either one so a library
        # change cannot turn every request into an unexplained "forbidden".
        return (token.claims or {}).get("sub") or getattr(token, "subject", None)

    def _grant(self, token):
        if token is None:
            raise ToolError("forbidden: unauthenticated")
        if not token.client_id:
            raise ToolError("forbidden: missing_client_id")
        subject = self._subject(token)
        if not subject:
            raise ToolError("forbidden: identity_unavailable")
        if subject != self.owner_sub:
            raise ToolError("forbidden: owner_mismatch")
        if token.expires_at is None or token.expires_at <= time.time():
            raise ToolError("unauthorized")
        grant = self.table.get_item(
            Key={"PK": "GRANT#" + self.owner_sub, "SK": "CLIENT#" + token.client_id},
            ConsistentRead=True,
        ).get("Item")
        if not grant:
            # OAuth consent proves identity, not KB access. A client that
            # re-registers gets a new client_id, so grants do not carry over.
            raise ToolError(
                "forbidden: grant_required; no KB grant exists for OAuth client "
                + token.client_id + self.recovery(token.client_id))
        if grant.get("Revoked", True):
            raise ToolError(
                "forbidden: grant_revoked; the KB grant for OAuth client "
                + token.client_id + " is revoked" + self.recovery(token.client_id))
        if float(grant.get("ExpiresAt", 0)) <= time.time():
            raise ToolError(
                "forbidden: grant_expired; the KB grant for OAuth client "
                + token.client_id + " has expired" + self.recovery(token.client_id))
        return grant

    def status(self, token):
        """Describe this caller's verified identity and grant without reading notes."""
        claims = (token.claims or {}) if token is not None else {}
        subject = self._subject(token) if token is not None else None
        result = {
            "authenticated": token is not None,
            "client_id": getattr(token, "client_id", None),
            "owner": bool(subject) and subject == self.owner_sub,
            "identity": {"subject_present": bool(subject), "email": claims.get("email")},
            "grant": {"present": False, "revoked": None, "expires_at": None, "scopes": []},
        }
        # Only the owner can hold a grant, so never probe the table for other
        # callers and never disclose whether some other client is granted.
        if not result["client_id"] or not result["owner"]:
            return result
        if self.base_url:
            result["access_management"] = {"url": self.access_url(result["client_id"]),
                                           "default_days": 365, "available_days": [90, 365],
                                           "renewal_required": True}
        grant = self.table.get_item(
            Key={"PK": "GRANT#" + self.owner_sub, "SK": "CLIENT#" + token.client_id},
            ConsistentRead=True,
        ).get("Item")
        if grant:
            result["grant"] = {
                "present": True,
                "revoked": bool(grant.get("Revoked", True)),
                "expires_at": int(float(grant["ExpiresAt"])) if "ExpiresAt" in grant else None,
                "scopes": sorted(grant.get("Scopes", [])),
            }
            if self.base_url:
                result["access_management"]["renewal_required"] = (
                    bool(grant.get("Revoked", True)) or
                    float(grant.get("ExpiresAt", 0)) <= time.time() + 30 * 86400)
        return result

    def read_prefixes(self, token):
        grant = self._grant(token)
        if "kb:read" not in grant.get("Scopes", []):
            raise ToolError(
                "forbidden: missing_scope; the KB grant for OAuth client "
                + token.client_id + " does not include kb:read" + self.recovery(token.client_id))
        prefixes = grant.get("Prefixes", [])
        if not isinstance(prefixes, list) or not all(isinstance(prefix, str) for prefix in prefixes):
            raise ToolError(
                "forbidden: malformed_grant; the KB grant for OAuth client "
                + token.client_id + " has invalid read prefixes")
        return prefixes

    def capture_prefixes(self, token):
        grant = self._grant(token)
        if "kb:capture" not in grant.get("Scopes", []):
            raise ToolError(
                "forbidden: missing_scope; the KB grant for OAuth client "
                + token.client_id + " does not include kb:capture" + self.recovery(token.client_id))
        prefixes = grant.get("CapturePrefixes", [])
        if not isinstance(prefixes, list) or not prefixes:
            raise ToolError(
                "forbidden: malformed_grant; the KB grant for OAuth client "
                + token.client_id + " has invalid capture prefixes")
        try:
            for prefix in prefixes:
                validate_capture_prefix(prefix)
        except ValueError:
            raise ToolError(
                "forbidden: malformed_grant; the KB grant for OAuth client "
                + token.client_id + " has invalid capture prefixes") from None
        return prefixes

    def update_prefixes(self, token):
        grant = self._grant(token)
        if "kb:update" not in grant.get("Scopes", []):
            raise ToolError("forbidden: missing_scope; kb:update requires owner approval" + self.recovery(token.client_id))
        prefixes = grant.get("UpdatePrefixes", [])
        try:
            if not isinstance(prefixes, list) or not prefixes:
                raise ValueError()
            for prefix in prefixes:
                validate_update_prefix(prefix)
        except ValueError:
            raise ToolError("forbidden: malformed_grant; invalid update prefixes") from None
        return prefixes

    def operation_identity(self, token, scope="kb:capture"):
        grant = self._grant(token)
        required = {"kb:capture", "kb:update"} if scope == "any-write" else {scope}
        if not required.intersection(grant.get("Scopes", [])):
            raise ToolError(
                "forbidden: missing_scope; the KB grant for OAuth client "
                + token.client_id + " does not include " + scope + self.recovery(token.client_id))
        return self.owner_sub, token.client_id
