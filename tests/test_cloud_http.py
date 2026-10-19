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
from unittest.mock import ANY, patch

import boto3
from botocore.response import StreamingBody
from botocore.stub import Stubber
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from fastmcp.exceptions import ToolError
import httpx2
import uvicorn

from cloud_kb.api import create_app
from cloud_kb.auth import GrantGate
from cloud_kb.search import CONTRACT, SnapshotSearch
from cloud_kb.storage import S3Notes
from cloud_kb.writer import LearningWriter, render_markdown


PATH = "Resources/MCP Demo/Mock orchard.md"
FIXTURE = Path(__file__).parent / "fixtures/cloud-kb" / PATH


class SyntheticTable:
    """Explicit test double, never selected by production configuration."""
    def __init__(self, descriptor):
        self.descriptor = descriptor
        self.revoked = False
        self.items = {}
        self.grants = {
            "synthetic-client": {"Scopes": ["kb:read", "kb:capture"],
                                 "Prefixes": ["Resources/MCP Demo/"], "CapturePrefixes": ["Resources/_Review/AI Learning/"]},
            "synthetic-reader": {"Scopes": ["kb:read"], "Prefixes": ["Resources/_Review/AI Learning/"]},
        }

    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        if Key == {"PK": "INDEX#ACTIVE", "SK": "SNAPSHOT"}:
            return {"Item": self.descriptor}
        if Key.get("PK") == "GRANT#synthetic-owner" and Key.get("SK", "").startswith("CLIENT#"):
            client_id = Key["SK"].removeprefix("CLIENT#")
            grant = self.grants.get(client_id)
            if grant:
                return {"Item": {"Revoked": self.revoked, "ExpiresAt": int(time.time()) + 300, **grant}}
        item = self.items.get((Key.get("PK"), Key.get("SK")))
        return {"Item": item} if item else {}

    def put_item(self, *, Item, ConditionExpression):
        key = Item["PK"], Item["SK"]
        if key in self.items:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[key] = dict(Item)

    def update_item(self, *, Key, ExpressionAttributeValues, **_):
        item = self.items[Key["PK"], Key["SK"]]
        values = ExpressionAttributeValues
        item.update({"State": values.get(":persisted", item["State"]),
                     "Persistence": values.get(":persisted", values.get(":retryable")),
                     "Revision": values.get(":revision", item.get("Revision")),
                     "ContentSha256": values.get(":digest", item["ContentSha256"]),
                     "UpdatedAt": values[":now"]})


def response(raw):
    return {"Body": StreamingBody(BytesIO(raw), len(raw)), "ContentLength": len(raw),
            "VersionId": "mock-v1", "ETag": '"synthetic"'}


class CloudHTTPTests(unittest.TestCase):
    def test_mock_markdown_over_authenticated_http(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(32)
            self.run_mock_proof(listener)

    def test_mock_markdown_over_authenticated_asgi(self):
        # Exercise the same auth, protocol and storage proof in restricted
        # environments that cannot bind a loopback port. Keep the socket test.
        self.run_mock_proof()

    def run_mock_proof(self, listener=None):
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
        with closing(s3):
            origin = (f"http://127.0.0.1:{listener.getsockname()[1]}" if listener else
                      "http://synthetic-kb.invalid")
            verifier = JWTVerifier(public_key=pair.public_key, issuer="https://synthetic.invalid", audience="synthetic-kb", required_scopes=["kb:read"])
            notes = S3Notes(s3, "synthetic-vault")
            search = SnapshotSearch(s3, "synthetic-index", table, notes)
            app = create_app(auth_provider=verifier, gate=GrantGate(table, "synthetic-owner"), notes=notes,
                             search=search,
                             writer=LearningWriter(s3, table, "synthetic-vault"), base_url=origin)
            server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="critical"))
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            with Stubber(s3) as stub:
                stub.add_response("get_object", response(snapshot), {"Bucket": "synthetic-index", "Key": descriptor["Key"]})
                for _ in range(2):
                    stub.add_response("get_object", response(raw), {"Bucket": "synthetic-vault", "Key": "notes/" + PATH})
                stub.add_response("put_object", {"VersionId": "capture-v1"}, {
                    "Bucket": "synthetic-vault", "Key": ANY, "Body": ANY,
                    "ContentType": "text/markdown; charset=utf-8", "ServerSideEncryption": "AES256",
                    "IfNoneMatch": "*"})
                captured_raw = render_markdown(
                    title="Synthetic cross-client learning", markdown="Raw synthetic learning.",
                    origin="synthetic test", created_date="2026-10-19", evidence=[],
                    inference_labels=["ai-inference"])
                stub.add_response("get_object", response(captured_raw), {
                    "Bucket": "synthetic-vault", "Key": ANY})
                if listener:
                    thread.start()
                try:
                    if listener:
                        for _ in range(100):
                            if server.started:
                                break
                            time.sleep(0.02)
                        self.assertTrue(server.started)
                    async def exercise():
                        if listener:
                            await self.exercise(origin, pair, table, raw, captured_raw, search)
                        else:
                            async with app.router.lifespan_context(app):
                                await self.exercise(origin, pair, table, raw, captured_raw, search, app)
                    asyncio.run(exercise())
                    stub.assert_no_pending_responses()
                finally:
                    if listener:
                        server.should_exit = True
                        thread.join(timeout=5)
                        self.assertFalse(thread.is_alive())

    async def exercise(self, origin, pair, table, raw, captured_raw, search, app=None):
        def http_client(**kwargs):
            if app is not None:
                kwargs["transport"] = httpx2.ASGITransport(app)
            return httpx2.AsyncClient(**kwargs)

        def mcp_client(auth):
            transport = StreamableHttpTransport(origin + "/mcp", auth=auth,
                                                httpx_client_factory=http_client)
            return Client(transport, timeout=10)

        def token(subject="synthetic-owner", audience="synthetic-kb", expires=300, scopes=None,
                  client_id="synthetic-client"):
            return pair.create_token(subject=subject, issuer="https://synthetic.invalid", audience=audience,
                                     scopes=["kb:read"] if scopes is None else scopes, expires_in_seconds=expires,
                                     additional_claims={"client_id": client_id})
        async with http_client() as http:
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
        async with mcp_client(token()) as client:
            tools = await client.list_tools()
            self.assertEqual({tool.name for tool in tools},
                             {"search_kb", "fetch_note", "capture_learning",
                          "get_change_status", "get_access_status", "update_note"})
            access = (await client.call_tool("get_access_status", {})).data
            self.assertEqual(access["client_id"], "synthetic-client")
            self.assertTrue(access["owner"])
            self.assertTrue(access["grant"]["present"])
            self.assertEqual(access["grant"]["scopes"], ["kb:capture", "kb:read"])
            found = (await client.call_tool("search_kb", {"query": "citrus-lantern-742", "strategy": "lexical"})).data
            self.assertEqual(found["results"][0]["path"], PATH)
            self.assertEqual(found["results"][0]["freshness"], "current")
            fetched = (await client.call_tool("fetch_note", {"path": PATH})).data
            self.assertEqual(fetched["content"], raw.decode())
            self.assertEqual(fetched["sha256"], hashlib.sha256(raw).hexdigest())
            capture_arguments = {
                "operation_id": "synthetic-capture-001", "destination": "Resources/_Review/AI Learning/",
                "title": "Synthetic cross-client learning", "markdown": "Raw synthetic learning.",
                "origin": "synthetic test", "created_date": "2026-10-19",
                "evidence": [], "inference_labels": ["ai-inference"],
            }
            capture = (await client.call_tool("capture_learning", capture_arguments)).data
            self.assertEqual(capture["persistence"], "persisted")
            self.assertEqual(capture["indexing"], "pending")
            self.assertTrue(capture["path"].startswith("Resources/_Review/AI Learning/"))
            duplicates = {"results": [{"path": capture["path"], "excerpt": "# Synthetic cross-client learning"}]}
            with patch.object(search, "search", return_value=duplicates) as duplicate_search:
                replay = (await client.call_tool("capture_learning", capture_arguments)).data
                self.assertTrue(replay["replayed"])
                self.assertEqual(replay["path"], capture["path"])
                with self.assertRaises(ToolError):
                    await client.call_tool("capture_learning", {**capture_arguments, "markdown": "Changed content."})
                duplicate_search.assert_not_called()
                duplicate = (await client.call_tool("capture_learning", {
                    **capture_arguments, "operation_id": "new-duplicate-operation"})).data
                self.assertEqual(duplicate["state"], "duplicate_review")
            with patch.object(search, "search", side_effect=RuntimeError("index_unavailable")):
                replay = (await client.call_tool("capture_learning", capture_arguments)).data
                self.assertTrue(replay["replayed"])
                legacy_arguments = {key: value for key, value in capture_arguments.items()
                                    if key not in {"markdown", "created_date", "evidence"}}
                legacy_arguments.update(destination="learning", learning=capture_arguments["markdown"],
                                        date=capture_arguments["created_date"], evidence_links=[])
                legacy = (await client.call_tool("capture_learning", legacy_arguments)).data
                self.assertTrue(legacy["replayed"])
                self.assertEqual(legacy["path"], capture["path"])
                for conflicting in ({"markdown": "Different body"}, {"created_date": "2026-10-20"},
                                    {"evidence": ["https://example.invalid/different"]}):
                    with self.subTest(conflicting=conflicting), self.assertRaises(ToolError):
                        await client.call_tool("capture_learning", {**legacy_arguments, **conflicting})
            status = (await client.call_tool("get_change_status", {
                "operation_id": "synthetic-capture-001"})).data
            self.assertEqual(status["path"], capture["path"])
            self.assertEqual(status["persistence"], "persisted")
            table.grants["synthetic-client"]["CapturePrefixes"] = ["Ideas/"]
            with self.assertRaises(ToolError):
                await client.call_tool("capture_learning", legacy_arguments)
        async with mcp_client(token(client_id="synthetic-unregistered")) as client:
            with self.assertRaises(ToolError) as raised:
                await client.call_tool("fetch_note", {"path": PATH})
            self.assertIn("grant_required", str(raised.exception))
            status = (await client.call_tool("get_access_status", {})).data
            self.assertFalse(status["grant"]["present"])
        async with mcp_client(token(client_id="synthetic-reader")) as client:
            fetched_capture = (await client.call_tool("fetch_note", {"path": capture["path"]})).data
            self.assertEqual(fetched_capture["content"].encode(), captured_raw)
            with self.assertRaises(ToolError):
                await client.call_tool("get_change_status", {"operation_id": "synthetic-capture-001"})
            for arguments in ({"path": "../private.md"}, {"path": "Wiki/not-granted.md"}):
                with self.assertRaises(ToolError):
                    await client.call_tool("fetch_note", arguments)
            table.revoked = True
            with self.assertRaises(ToolError):
                await client.call_tool("fetch_note", {"path": PATH})
        async with mcp_client(token(subject="another-owner")) as client:
            with self.assertRaises(ToolError):
                await client.call_tool("fetch_note", {"path": PATH})


if __name__ == "__main__":
    unittest.main()
