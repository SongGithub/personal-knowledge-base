"""Synthetic checks for durable broker storage and per-client grant enforcement."""
from decimal import Decimal
import json
import time
import unittest

from cryptography.fernet import Fernet
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from fastmcp.exceptions import ToolError

from cloud_kb.auth import DynamoOAuthStore, GrantGate


class Table:
    def __init__(self):
        self.items = {}

    def put_item(self, *, Item):
        self.items[Item["PK"], Item["SK"]] = Item

    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        return {"Item": self.items[Key["PK"], Key["SK"]]} if (Key["PK"], Key["SK"]) in self.items else {}

    def delete_item(self, *, Key, ReturnValues):
        return {"Attributes": self.items.pop((Key["PK"], Key["SK"]), None)}


class GrantTable:
    def __init__(self, grant):
        self.grant = grant

    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        return {"Item": self.grant} if Key == {"PK": "GRANT#owner", "SK": "CLIENT#client"} else {}


class Token:
    claims = {"sub": "owner"}
    subject = None
    client_id = "client"
    expires_at = time.time() + 60


class OtherOwnerToken(Token):
    claims = {"sub": "another-owner"}


class EmailToken(Token):
    claims = {"sub": "owner", "email": "owner@example.invalid"}


class SubjectOnlyToken(Token):
    claims = {}
    subject = "owner"


class NoIdentityToken(Token):
    claims = {}
    subject = None


class EmptyTable:
    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        return {}


class AuthStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_scope_and_prefix_are_separate_from_read_access(self):
        grant = {"Revoked": False, "ExpiresAt": int(time.time()) + 60,
                 "Scopes": ["kb:capture"], "CapturePrefixes": ["Ideas/"]}
        gate = GrantGate(GrantTable(grant), "owner")
        self.assertEqual(gate.capture_prefixes(Token()), ["Ideas/"])
        with self.assertRaises(ToolError) as raised:
            gate.read_prefixes(Token())
        self.assertIn("missing_scope", str(raised.exception))
        grant["CapturePrefixes"] = ["Wiki/"]
        with self.assertRaises(ToolError) as raised:
            gate.capture_prefixes(Token())
        self.assertIn("malformed_grant", str(raised.exception))

    async def test_encrypted_state_survives_adapter_restart(self):
        table = Table()
        encryption = Fernet.generate_key()
        def store():
            return FernetEncryptionWrapper(key_value=DynamoOAuthStore(table), fernet=Fernet(encryption))
        first = store()
        await first.put("synthetic-token-key", {"token": "synthetic-secret"}, collection="tokens", ttl=120)
        self.assertNotIn("synthetic-secret", json.dumps(list(table.items.values())))
        self.assertEqual(await store().get("synthetic-token-key", collection="tokens"), {"token": "synthetic-secret"})
        self.assertIsNone(await store().get("synthetic-token-key", collection="other"))
        for item in table.items.values():
            item["ExpiresAt"] = Decimal(int(time.time()) - 1)
        self.assertIsNone(await store().get("synthetic-token-key", collection="tokens"))

    async def test_bulk_storage_and_delete(self):
        store = DynamoOAuthStore(Table())
        await store.put_many(["one", "two"], [{"x": 1}, {"x": 2}], collection="clients")
        self.assertEqual(await store.get_many(["two", "missing", "one"], collection="clients"), [{"x": 2}, None, {"x": 1}])
        self.assertEqual(await store.delete_many(["one", "missing"], collection="clients"), 1)


class GrantDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def grant(**overrides):
        grant = {"Revoked": False, "ExpiresAt": int(time.time()) + 60,
                 "Scopes": ["kb:read"], "Prefixes": ["Ideas/"]}
        grant.update(overrides)
        return grant

    async def test_missing_grant_names_the_client_instead_of_generic_forbidden(self):
        gate = GrantGate(EmptyTable(), "owner")
        with self.assertRaises(ToolError) as raised:
            gate.read_prefixes(Token())
        message = str(raised.exception)
        self.assertIn("grant_required", message)
        self.assertIn("client", message)

    async def test_owner_mismatch_is_reported_separately(self):
        gate = GrantGate(GrantTable(self.grant()), "owner")
        with self.assertRaises(ToolError) as raised:
            gate.read_prefixes(OtherOwnerToken())
        self.assertEqual(str(raised.exception), "forbidden: owner_mismatch")

    async def test_revoked_and_expired_grants_are_distinguished(self):
        revoked = GrantGate(GrantTable(self.grant(Revoked=True)), "owner")
        with self.assertRaises(ToolError) as raised:
            revoked.read_prefixes(Token())
        self.assertIn("grant_revoked", str(raised.exception))

        expired = GrantGate(GrantTable(self.grant(ExpiresAt=int(time.time()) - 1)), "owner")
        with self.assertRaises(ToolError) as raised:
            expired.read_prefixes(Token())
        self.assertIn("grant_expired", str(raised.exception))

    async def test_identity_falls_back_to_the_verified_subject(self):
        gate = GrantGate(GrantTable(self.grant()), "owner")
        self.assertEqual(gate.read_prefixes(SubjectOnlyToken()), ["Ideas/"])

    async def test_missing_verified_subject_is_reported(self):
        gate = GrantGate(GrantTable(self.grant()), "owner")
        with self.assertRaises(ToolError) as raised:
            gate.read_prefixes(NoIdentityToken())
        self.assertEqual(str(raised.exception), "forbidden: identity_unavailable")

    async def test_status_reports_identity_and_grant_without_requiring_access(self):
        grant = self.grant(Scopes=["kb:capture", "kb:read"])
        gate = GrantGate(GrantTable(grant), "owner")
        status = gate.status(EmailToken())
        self.assertTrue(status["authenticated"])
        self.assertEqual(status["client_id"], "client")
        self.assertTrue(status["owner"])
        self.assertEqual(status["identity"], {"subject_present": True,
                                              "email": "owner@example.invalid"})
        self.assertEqual(status["grant"], {"present": True, "revoked": False,
                                           "expires_at": grant["ExpiresAt"],
                                           "scopes": ["kb:capture", "kb:read"]})

        missing = GrantGate(EmptyTable(), "owner").status(Token())
        self.assertEqual(missing["grant"], {"present": False, "revoked": None,
                                            "expires_at": None, "scopes": []})

    async def test_status_does_not_probe_the_table_for_other_owners(self):
        class Untouchable:
            def get_item(self, **_):
                raise AssertionError("non-owner status must not query grants")

        status = GrantGate(Untouchable(), "owner").status(OtherOwnerToken())
        self.assertFalse(status["owner"])
        self.assertFalse(status["grant"]["present"])


if __name__ == "__main__":
    unittest.main()
