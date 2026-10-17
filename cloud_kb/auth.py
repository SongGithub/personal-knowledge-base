"""Google OAuth broker, durable encrypted state and per-client backend grants."""
import asyncio
import hashlib
import json
import time

from cryptography.fernet import Fernet
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.google import GoogleProvider
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper


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


def google_provider(settings, secret, table):
    return BoundGoogleProvider(
        client_id=secret["google_client_id"], client_secret=secret["google_client_secret"],
        base_url=settings.base_url,
        required_scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
        jwt_signing_key=secret["jwt_signing_key"],
        client_storage=FernetEncryptionWrapper(
            key_value=DynamoOAuthStore(table), fernet=Fernet(secret["storage_encryption_key"].encode()),
        ),
        allowed_client_redirect_uris=list(settings.client_redirect_uris),
        require_authorization_consent=True, enable_cimd=False,
        cache_ttl_seconds=0, fastmcp_access_token_expiry_seconds=300,
    )


class GrantGate:
    def __init__(self, table, owner_sub):
        self.table, self.owner_sub = table, owner_sub

    def read_prefixes(self, token):
        if token is None or token.claims.get("sub") != self.owner_sub or not token.client_id:
            raise ToolError("forbidden")
        if token.expires_at is None or token.expires_at <= time.time():
            raise ToolError("unauthorized")
        grant = self.table.get_item(
            Key={"PK": "GRANT#" + self.owner_sub, "SK": "CLIENT#" + token.client_id},
            ConsistentRead=True,
        ).get("Item", {})
        if (grant.get("Revoked", True) or float(grant.get("ExpiresAt", 0)) <= time.time() or
                "kb:read" not in grant.get("Scopes", [])):
            raise ToolError("forbidden")
        prefixes = grant.get("Prefixes", [])
        if not isinstance(prefixes, list) or not all(isinstance(prefix, str) for prefix in prefixes):
            raise ToolError("forbidden")
        return prefixes
