"""Synthetic ordinary-note editing, conditional writes and recovery checks."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import time
import unittest

from botocore.exceptions import ClientError, EndpointConnectionError
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
import httpx2

from cloud_kb.api import create_app
from cloud_kb.auth import GrantGate
from cloud_kb.storage import S3Notes, UPDATE_ROOTS, update_requires_review
from cloud_kb.updater import NoteUpdater


PATH = "Areas/MCP Demo/Orchard index.md"
BASE = b"# Synthetic orchard\n\n## Notes\n\nOwner text stays here.\n"


class VersionedS3:
    def __init__(self):
        self.versions = {}
        self.before_put = None
        self.lose_response = False
        self.fail_before_put = False
        self.truncated_history = False
        self.puts = 0
        self.seed(PATH, BASE, {"owner-tag": "preserve"})

    def seed(self, path, raw, metadata=None):
        versions = self.versions.setdefault("notes/" + path, [])
        record = {"Body": raw, "VersionId": "version-" + str(len(versions) + 1),
                  "ETag": '"' + hashlib.md5(raw).hexdigest() + '"', "Metadata": metadata or {},
                  "ContentType": "text/markdown; charset=utf-8"}
        versions.append(record)
        return record

    def get_object(self, *, Bucket, Key, VersionId=None):
        records = self.versions.get(Key, [])
        found = next((x for x in records if x["VersionId"] == VersionId), None) if VersionId else (records[-1] if records else None)
        if found is None:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {**found, "Body": BytesIO(found["Body"]), "ContentLength": len(found["Body"])}

    def put_object(self, *, Bucket, Key, Body, IfMatch, Metadata, **kwargs):
        assert kwargs["ServerSideEncryption"] == "AES256"
        if self.fail_before_put:
            self.fail_before_put = False
            raise EndpointConnectionError(endpoint_url="https://synthetic.invalid")
        if self.before_put:
            callback, self.before_put = self.before_put, None
            callback()
        current = self.versions.get(Key, [])
        if not current or current[-1]["ETag"] != IfMatch:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.puts += 1
        result = self.seed(Key.removeprefix("notes/"), Body, Metadata)
        if self.lose_response:
            self.lose_response = False
            raise EndpointConnectionError(endpoint_url="https://synthetic.invalid")
        return {"VersionId": result["VersionId"], "ETag": result["ETag"]}

    def list_object_versions(self, *, Bucket, Prefix, MaxKeys):
        assert MaxKeys == 32
        return {"Versions": [{"Key": key, "VersionId": record["VersionId"]}
                             for key, rows in self.versions.items() if key.startswith(Prefix)
                             for record in reversed(rows)][:MaxKeys], "IsTruncated": self.truncated_history}


class Table:
    def __init__(self):
        self.items = {}
        self.fail_completion = False

    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        row = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": deepcopy(row)} if row else {}

    def put_item(self, *, Item, ConditionExpression):
        assert ConditionExpression == "attribute_not_exists(PK)"
        key = Item["PK"], Item["SK"]
        if key in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[key] = deepcopy(Item)

    def update_item(self, *, Key, ExpressionAttributeValues, ConditionExpression, **kwargs):
        if self.fail_completion:
            raise EndpointConnectionError(endpoint_url="https://synthetic.invalid")
        row = self.items[Key["PK"], Key["SK"]]
        values = ExpressionAttributeValues
        assert row["RequestDigest"] == values[":request"]
        row.update(State=values[":state"], Persistence=values[":state"], Revision=values[":revision"], UpdatedAt=values[":now"])
        row.pop("ProposedContent", None)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.s3, self.table = VersionedS3(), Table()
        self.notes = S3Notes(self.s3, "synthetic-vault")
        self.updater = NoteUpdater(self.notes, self.table, indexed_sha256=lambda _: "older-index-digest")
        self.args = dict(principal="synthetic-owner", client_id="client", operation_id="update-001", path=PATH,
                         expected_revision=self.notes.fetch(PATH)["revision"], old_text="## Notes",
                         new_text="## Notes\n\n- [[Resources/MCP Demo/Synthetic learning]]", origin="Synthetic check",
                         date="2026-10-20", evidence_links=[], inference_labels=["ai-inference"],
                         allowed_prefixes=list(UPDATE_ROOTS), read_prefixes=list(UPDATE_ROOTS))

    def test_exact_edit_preserves_metadata_body_versions_and_pending_index(self):
        result = self.updater.update(**self.args)
        self.assertEqual(result["persistence"], "persisted")
        self.assertEqual(result["indexing"], "pending")
        self.assertEqual(result["revision"], "version-2")
        note = self.notes.fetch(PATH)
        self.assertEqual(note["revision"], result["revision"])
        self.assertIn("Owner text stays here.", note["content"])
        self.assertIn(self.args["new_text"], note["content"])
        self.assertIn('"origin":"Synthetic check"', note["content"])
        self.assertEqual(self.s3.versions["notes/" + PATH][-1]["Metadata"], {"owner-tag": "preserve"})
        self.assertEqual(self.notes.read(PATH, version="version-1")["raw"], BASE)
        self.assertNotIn("ProposedContent", next(iter(self.table.items.values())))

    def test_replay_and_changed_input(self):
        first = self.updater.update(**self.args)
        replay = self.updater.update(**self.args)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["revision"], first["revision"])
        self.assertEqual(self.s3.puts, 1)
        with self.assertRaisesRegex(ValueError, "operation_id_reused"):
            self.updater.update(**{**self.args, "new_text": "Other content"})

    def test_stale_and_concurrent_owner_edits_never_overwrite(self):
        self.s3.seed(PATH, b"Owner changed this.\n")
        with self.assertRaisesRegex(ValueError, "revision_conflict"):
            self.updater.update(**self.args)
        self.setUp()
        self.s3.before_put = lambda: self.s3.seed(PATH, b"Concurrent owner change.\n")
        with self.assertRaisesRegex(ValueError, "revision_conflict"):
            self.updater.update(**self.args)
        self.assertEqual(self.notes.read(PATH)["raw"], b"Concurrent owner change.\n")
        self.assertEqual(self.s3.puts, 0)

    def test_lost_s3_response_and_database_completion_recover_without_duplicate(self):
        self.s3.lose_response = True
        result = self.updater.update(**self.args)
        self.assertEqual(result["persistence"], "persisted")
        self.assertEqual(self.s3.puts, 1)
        self.setUp()
        self.table.fail_completion = True
        first = self.updater.update(**self.args)
        self.assertEqual(first["operation_audit"], "pending_retry")
        self.table.fail_completion = False
        # Another writer can update the note before the original response is
        # repaired; recover the first receipt from its immutable S3 version.
        self.s3.seed(PATH, b"Later owner revision.\n")
        replay = self.updater.update(**self.args)
        self.assertEqual(replay["revision"], first["revision"])
        self.assertEqual(replay["indexing"], "superseded")
        self.assertEqual(self.s3.puts, 1)
        self.assertEqual(self.notes.read(PATH)["raw"], b"Later owner revision.\n")

    def test_failure_before_write_is_unknown_and_same_id_can_retry(self):
        self.s3.fail_before_put = True
        with self.assertRaisesRegex(RuntimeError, "write_outcome_unknown"):
            self.updater.update(**self.args)
        self.assertEqual(self.notes.read(PATH)["raw"], BASE)
        self.assertEqual(self.updater.update(**self.args)["persistence"], "persisted")
        self.assertEqual(self.s3.puts, 1)

    def test_ambiguous_missing_protected_and_out_of_scope_edits_fail(self):
        for args, reason in [({"old_text": "not present"}, "patch_not_unique"),
                             ({"path": "Wiki/Index.md"}, "forbidden"),
                             ({"path": "Archive/Snapshot.md"}, "forbidden"),
                             ({"allowed_prefixes": ["Ideas/"]}, "forbidden"),
                             ({"read_prefixes": ["Ideas/"]}, "forbidden"),
                             ({"new_text": "", "old_text": BASE.decode()}, "empty_note")]:
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, reason):
                self.updater.update(**{**self.args, **args})
        self.s3.seed(PATH, b"# Twice\n## Notes\n## Notes\n")
        with self.assertRaisesRegex(ValueError, "patch_not_unique"):
            self.updater.update(**{**self.args, "expected_revision": "version-2"})

    def test_canonical_yaml_forms_and_proposed_promotion_require_review(self):
        for content in ('---\nstatus: canonical\n---\n## Notes',
                        '---\n"status": "canonical"\n---\n## Notes',
                        '---\nauthority: >-\n  binding\n---\n## Notes',
                        '---\nstatus: canonical\nstatus: draft\n---\n## Notes',
                        '---\nstatus: [canonical]\n---\n## Notes',
                        '---\ntype: source\n---\n## Notes',
                        '---\nstatus: confirmed\n---\n## Notes'.replace('\n','\r\n')):
            with self.subTest(content=content):
                self.s3.seed(PATH, content.encode())
                with self.assertRaisesRegex(ValueError, "review_required"):
                    self.updater.update(**{**self.args, "expected_revision": self.notes.fetch(PATH)["revision"]})
        self.setUp()
        with self.assertRaisesRegex(ValueError, "review_required"):
            self.updater.update(**{**self.args, "old_text": BASE.decode(),
                                   "new_text": "---\nstatus: verified\n---\n# Claim"})
        self.assertTrue(update_requires_review("Resources/_Review/AGENTS.md", "# Rules"))
        self.assertFalse(update_requires_review(PATH, "---\nstatus:\n---\n# Ordinary note"))
        self.assertTrue(update_requires_review(PATH, "---\nstatus: canonical\n# Unclosed header"))

    def test_utf8_bom_crlf_and_truncated_fetch_keep_unrelated_content(self):
        raw = b"\xef\xbb\xbf# Synthetic\r\n## Notes\r\nOwner text.\r\n"
        self.s3.seed(PATH, raw)
        fetched = self.notes.fetch(PATH, 5)
        self.assertTrue(fetched["truncated"])
        self.assertTrue(fetched["revision"])
        self.updater.update(**{**self.args, "expected_revision": fetched["revision"]})
        saved = self.notes.read(PATH)["raw"]
        self.assertTrue(saved.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"Owner text.\r\n", saved)

    def test_status_is_read_only_and_respects_current_scope(self):
        self.table.fail_completion = True
        first = self.updater.update(**self.args)
        before = deepcopy(self.table.items)
        status_args = {key: self.args[key] for key in ("principal", "client_id", "operation_id", "allowed_prefixes", "read_prefixes")}
        status = self.updater.status(**status_args)
        self.assertEqual(status["revision"], first["revision"])
        self.assertEqual(self.table.items, before)
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.updater.status(**{**status_args, "allowed_prefixes": ["Ideas/"]})


class UpdateWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_fetch_revision_is_in_json_text_and_structured_result_and_update_works(self):
        s3, table = VersionedS3(), Table()
        notes = S3Notes(s3, "synthetic-vault")
        updater = NoteUpdater(notes, table)
        pair = RSAKeyPair.generate()
        origin = "https://synthetic-kb.invalid"
        table.items["GRANT#owner", "CLIENT#client"] = {"Revoked": False, "ExpiresAt": int(time.time()) + 300,
                 "Scopes": ["kb:read", "kb:capture", "kb:update"], "Prefixes": list(UPDATE_ROOTS),
                 "CapturePrefixes": ["Resources/_Review/AI Learning/"], "UpdatePrefixes": list(UPDATE_ROOTS)}
        verifier = JWTVerifier(public_key=pair.public_key, issuer=origin, audience="synthetic", required_scopes=["kb:read"])
        app = create_app(auth_provider=verifier, gate=GrantGate(table, "owner", origin), notes=notes,
                         search=None, updater=updater, base_url=origin)
        token = pair.create_token(subject="owner", issuer=origin, audience="synthetic", scopes=["kb:read"],
                                  additional_claims={"client_id": "client"})
        def http_factory(**kwargs):
            return httpx2.AsyncClient(**{**kwargs, "transport": httpx2.ASGITransport(app)})
        transport = StreamableHttpTransport(origin + "/mcp", auth=token, httpx_client_factory=http_factory)
        async with app.router.lifespan_context(app), Client(transport) as client:
            fetched = await client.call_tool("fetch_note", {"path": PATH})
            payload = json.loads(next(block.text for block in fetched.content if block.type == "text"))
            structured = fetched.structured_content
            self.assertEqual(payload["revision"], "version-1")
            self.assertEqual(structured["revision"], payload["revision"])
            args = {"operation_id": "wire-update", "path": PATH, "expected_revision": payload["revision"],
                    "old_text": "## Notes", "new_text": "## Notes\n\n- [[Synthetic note]]", "origin": "Synthetic wire check",
                    "date": "2026-10-20", "evidence_links": [], "inference_labels": ["ai-inference"]}
            saved = await client.call_tool("update_note", args)
            self.assertEqual(saved.structured_content["persistence"], "persisted")
            status = await client.call_tool("get_change_status", {"operation_id": "wire-update"})
            self.assertEqual(status.structured_content["revision"], saved.structured_content["revision"])
            grant = table.items["GRANT#owner", "CLIENT#client"]
            grant["Scopes"] = ["kb:read", "kb:capture"]
            with self.assertRaises(ToolError):
                await client.call_tool("update_note", {**args, "operation_id": "denied-update"})


if __name__ == "__main__":
    unittest.main()
