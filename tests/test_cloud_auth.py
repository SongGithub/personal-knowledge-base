"""Synthetic checks for durable broker storage and per-client grant enforcement."""
from decimal import Decimal
import json
import time
import unittest

from cryptography.fernet import Fernet
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from cloud_kb.auth import DynamoOAuthStore


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


class AuthStoreTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
