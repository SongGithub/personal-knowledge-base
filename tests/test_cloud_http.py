"""Real loopback HTTP/MCP proof with simulated AWS and a synthetic signer.

These checks do not claim AWS deployment or Google sign-in has succeeded.
"""
import asyncio
from contextlib import closing
import hashlib
from io import BytesIO
from pathlib import Path
import socket
import sqlite3
import threading
import time
import unittest

import boto3
from botocore.response import StreamingBody
from botocore.stub import Stubber
from fastmcp import Client
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from fastmcp.exceptions import ToolError
import httpx2
import uvicorn

from cloud_kb.api import create_app
from cloud_kb.auth import GrantGate
from cloud_kb.search import CONTRACT, SnapshotSearch
from cloud_kb.storage import S3Notes


PATH = "Resources/MCP Demo/Mock orchard.md"
FIXTURE = Path(__file__).parent / "fixtures/cloud-kb" / PATH


class SyntheticTable:
    """Explicit test double, never selected by production configuration."""
    def __init__(self, descriptor):
        self.descriptor = descriptor
        self.revoked = False

    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        if Key == {"PK": "INDEX#ACTIVE", "SK": "SNAPSHOT"}:
            return {"Item": self.descriptor}
        if Key == {"PK": "GRANT#synthetic-owner", "SK": "CLIENT#synthetic-client"}:
            return {"Item": {"Revoked": self.revoked, "ExpiresAt": int(time.time()) + 300,
                             "Scopes": ["kb:read"], "Prefixes": ["Resources/MCP Demo/"]}}
        return {}


def response(raw):
    return {"Body": StreamingBody(BytesIO(raw), len(raw)), "ContentLength": len(raw),
            "VersionId": "mock-v1", "ETag": '"synthetic"'}


class CloudHTTPTests(unittest.TestCase):
    def test_mock_markdown_over_authenticated_http(self):
        raw = FIXTURE.read_bytes()
        source_digest = hashlib.sha256(raw).hexdigest()
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE notes(path TEXT PRIMARY KEY,sha256 TEXT,content TEXT)")
            db.execute("INSERT INTO notes VALUES(?,?,?)", (PATH, source_digest, raw.decode()))
            db.commit()
            snapshot = db.serialize()
        descriptor = {"Contract": CONTRACT, "Key": "indexes/mock/index.sqlite",
                      "Sha256": hashlib.sha256(snapshot).hexdigest(), "SnapshotId": "mock-snapshot-v1"}
        table = SyntheticTable(descriptor)
        s3 = boto3.client("s3", region_name="ap-southeast-2", aws_access_key_id="synthetic", aws_secret_access_key="synthetic")
        pair = RSAKeyPair.generate()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(32)
            origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
            verifier = JWTVerifier(public_key=pair.public_key, issuer="https://synthetic.invalid", audience="synthetic-kb", required_scopes=["kb:read"])
            notes = S3Notes(s3, "synthetic-vault")
            app = create_app(auth_provider=verifier, gate=GrantGate(table, "synthetic-owner"), notes=notes,
                             search=SnapshotSearch(s3, "synthetic-index", table, notes), base_url=origin)
            server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="critical"))
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            with Stubber(s3) as stub:
                stub.add_response("get_object", response(snapshot), {"Bucket": "synthetic-index", "Key": descriptor["Key"]})
                for _ in range(2):
                    stub.add_response("get_object", response(raw), {"Bucket": "synthetic-vault", "Key": "notes/" + PATH})
                thread.start()
                try:
                    for _ in range(100):
                        if server.started:
                            break
                        time.sleep(0.02)
                    self.assertTrue(server.started)
                    asyncio.run(self.exercise(origin, pair, table, raw))
                    stub.assert_no_pending_responses()
                finally:
                    server.should_exit = True
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())

    async def exercise(self, origin, pair, table, raw):
        def token(subject="synthetic-owner", audience="synthetic-kb", expires=300, scopes=None):
            return pair.create_token(subject=subject, issuer="https://synthetic.invalid", audience=audience,
                                     scopes=["kb:read"] if scopes is None else scopes, expires_in_seconds=expires,
                                     additional_claims={"client_id": "synthetic-client"})
        async with httpx2.AsyncClient() as http:
            self.assertEqual((await http.get(origin + "/healthz")).status_code, 200)
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            for bad_token in (None, "invalid", token(audience="wrong-audience"), token(expires=-600), token(scopes=[])):
                headers = {"Accept": "application/json, text/event-stream"}
                if bad_token:
                    headers["Authorization"] = "Bearer " + bad_token
                denied = await http.post(origin + "/mcp", json=request, headers=headers)
                self.assertIn(denied.status_code, (401, 403))
                self.assertNotIn("orchard", denied.text)
            for origin_headers in ({"Host": "attacker.invalid"}, {"Origin": "https://attacker.invalid"}):
                denied = await http.post(origin + "/mcp", json=request, headers={
                    **origin_headers, "Authorization": "Bearer " + token(),
                    "Accept": "application/json, text/event-stream",
                })
                self.assertIn(denied.status_code, (400, 403, 421))
        async with Client(origin + "/mcp", auth=token(), timeout=10) as client:
            tools = await client.list_tools()
            self.assertEqual({tool.name for tool in tools}, {"search_kb", "fetch_note"})
            found = (await client.call_tool("search_kb", {"query": "citrus-lantern-742"})).data
            self.assertEqual(found["results"][0]["path"], PATH)
            self.assertEqual(found["results"][0]["freshness"], "current")
            fetched = (await client.call_tool("fetch_note", {"path": PATH})).data
            self.assertEqual(fetched["content"], raw.decode())
            self.assertEqual(fetched["sha256"], hashlib.sha256(raw).hexdigest())
            for arguments in ({"path": "../private.md"}, {"path": "Wiki/not-granted.md"}):
                with self.assertRaises(ToolError):
                    await client.call_tool("fetch_note", arguments)
            table.revoked = True
            with self.assertRaises(ToolError):
                await client.call_tool("fetch_note", {"path": PATH})
        async with Client(origin + "/mcp", auth=token(subject="another-owner"), timeout=10) as client:
            with self.assertRaises(ToolError):
                await client.call_tool("fetch_note", {"path": PATH})


if __name__ == "__main__":
    unittest.main()
