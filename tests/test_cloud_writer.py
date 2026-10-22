"""Synthetic idempotency and persistence checks for raw KB learning capture."""
from contextlib import closing
from io import BytesIO
import time
import unittest

from botocore.exceptions import ClientError, EndpointConnectionError

from cloud_kb.writer import LearningWriter, MAX_CAPTURE_BYTES
from tools.grant_mcp_client import apply_grant


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.fail_next = False

    def put_object(self, *, Bucket, Key, Body, IfNoneMatch, **kwargs):
        self.assert_private_write(IfNoneMatch, kwargs)
        if self.fail_next:
            self.fail_next = False
            raise ClientError({"Error": {"Code": "InternalError"}}, "PutObject")
        if (Bucket, Key) in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[Bucket, Key] = Body
        return {"VersionId": "synthetic-v1", "ETag": '"synthetic"'}

    @staticmethod
    def assert_private_write(if_none_match, kwargs):
        assert if_none_match == "*"
        assert kwargs["ServerSideEncryption"] == "AES256"

    def get_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        raw = self.objects[Bucket, Key]
        return {"Body": BytesIO(raw), "VersionId": "synthetic-v1", "ETag": '"synthetic"'}


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, *, Item, ConditionExpression):
        key = Item["PK"], Item["SK"]
        if key in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[key] = dict(Item)

    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item else {}

    def update_item(self, *, Key, ExpressionAttributeValues, **_):
        item = self.items[Key["PK"], Key["SK"]]
        values = ExpressionAttributeValues
        item.update({"State": values.get(":persisted", item["State"]),
                     "Persistence": values.get(":persisted", values.get(":retryable")),
                     "Revision": values.get(":revision", item.get("Revision")),
                     "ContentSha256": values.get(":digest", item["ContentSha256"]),
                     "UpdatedAt": values[":now"]})
        if ":audit_revision" in values:
            assert item["Persistence"] == values[":persisted"]
            assert item["ContentSha256"] == values[":digest"]
            item.update(ActivityAudit=values[":recorded"], ActivityAuditContract=values[":contract"],
                        ActivityLogRevision=values[":audit_revision"], ActivityLogSha256=values[":sha"])


class FakeSession:
    def __init__(self, owner="owner-sub", exists=False):
        self.owner = owner
        self.exists = exists
        self.grant = None

    class Lambda:
        def __init__(self, owner):
            self.owner = owner

        def get_function_configuration(self, **_):
            return {"Environment": {"Variables": {"PKB_OWNER_SUB": self.owner}}}

    class Table:
        def __init__(self, session):
            self.session = session

        def put_item(self, *, Item, ConditionExpression, ExpressionAttributeValues):
            assert "ExpiresAt <= :now" in ConditionExpression
            if self.session.exists:
                raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
            self.session.grant = Item

    def client(self, service):
        assert service == "lambda"
        return self.Lambda(self.owner)

    def resource(self, service):
        assert service == "dynamodb"
        return type("Resource", (), {"Table": lambda _, name: self.Table(self)})()


class WriterTests(unittest.TestCase):
    def setUp(self):
        self.s3, self.table = FakeS3(), FakeTable()
        self.writer = LearningWriter(self.s3, self.table, "private-vault")
        self.arguments = dict(
            principal="owner-sub", client_id="client-a", operation_id="capture-001",
            destination="Ideas/", title="A useful learning", markdown="Raw Markdown stays intact.",
            origin="Conversation", created_date="2026-10-19", evidence=["https://example.invalid/source"],
            inference_labels=["ai-inference"], allowed_prefixes=["Ideas/"],
        )

    def test_capture_persists_unverified_note_and_retries_idempotently(self):
        first = self.writer.capture(**self.arguments)
        self.assertEqual(first["persistence"], "persisted")
        self.assertEqual(first["indexing"], "pending")
        self.assertEqual(first["review"], "not_required")
        self.assertEqual(first["activity_audit"], "pending")
        self.assertEqual(first["operation_audit"], "recorded")
        self.assertTrue(first["path"].startswith("Ideas/2026/10/19-"))
        stored = next(iter(self.s3.objects.values()))
        self.assertIn(b"status: unverified", stored)
        self.assertIn(b"Raw Markdown stays intact.", stored)
        replay = self.writer.capture(**self.arguments)
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["path"], replay["path"])
        self.assertEqual(len(self.s3.objects), 1)
        self.assertEqual(self.writer.status(principal="owner-sub", client_id="client-a",
                                            operation_id="capture-001")["path"], first["path"])

    def test_operation_id_cannot_be_reused_for_different_content(self):
        self.writer.capture(**self.arguments)
        changed = {**self.arguments, "markdown": "Different learning."}
        with self.assertRaisesRegex(ValueError, "operation_id_reused"):
            self.writer.capture(**changed)

    def test_capture_destination_is_narrow_and_invalid_metadata_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.writer.capture(**{**self.arguments, "destination": "Wiki/", "allowed_prefixes": ["Ideas/"]})
        with self.assertRaisesRegex(ValueError, "invalid_created_date"):
            self.writer.capture(**{**self.arguments, "created_date": "tomorrow"})

    def test_failed_s3_write_is_visible_and_same_operation_can_retry(self):
        self.s3.fail_next = True
        with self.assertRaisesRegex(RuntimeError, "storage_unavailable"):
            self.writer.capture(**self.arguments)
        self.assertEqual(self.writer.status(principal="owner-sub", client_id="client-a",
                                            operation_id="capture-001")["persistence"], "retryable")
        recovered = self.writer.capture(**self.arguments)
        self.assertEqual(recovered["persistence"], "persisted")

    def test_approved_review_capture_is_exact_and_existing_sources_stay_forbidden(self):
        prefix = "Resources/_Review/AI Learning/"
        result = self.writer.capture(**{**self.arguments, "destination": prefix, "allowed_prefixes": [prefix]})
        self.assertTrue(result["path"].startswith(prefix))
        for destination in ("Wiki/", "Archive/", "Areas/Source Snapshots/", "Ideas/../Wiki/"):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.writer.capture(**{**self.arguments, "destination": destination,
                                       "allowed_prefixes": [destination]})
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.writer.capture(**{**self.arguments, "destination": "Ideas/", "allowed_prefixes": [prefix]})

    def test_new_notes_can_be_captured_in_each_granted_ordinary_folder(self):
        roots = ["Ideas/", "Projects/", "Areas/", "Resources/", "Personal Facts/", "Templates/"]
        for index, destination in enumerate(roots + ["Areas/Career/", "Resources/_Review/AI Learning/"]):
            with self.subTest(destination=destination):
                result = self.writer.capture(**{**self.arguments, "operation_id": f"ordinary-{index}",
                                             "destination": destination, "allowed_prefixes": roots})
                self.assertEqual(result["persistence"], "persisted")
                self.assertTrue(result["path"].startswith(destination))
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.writer.capture(**{**self.arguments, "destination": "Areas/Career/", "allowed_prefixes": ["Ideas/"]})

    def test_utf8_size_limit_applies_before_any_write(self):
        with self.assertRaisesRegex(ValueError, "capture_too_large"):
            self.writer.capture(**{**self.arguments, "markdown": "学" * 12_000})
        self.assertEqual(self.table.items, {})
        self.assertEqual(self.s3.objects, {})

    def test_crash_after_s3_create_recovers_unicode_content_without_overwriting(self):
        arguments = {**self.arguments, "markdown": "合成学习。" * 1000}
        update = self.table.update_item
        def unavailable(**_):
            raise ClientError({"Error": {"Code": "InternalServerError"}}, "UpdateItem")
        self.table.update_item = unavailable
        with self.assertRaises(ClientError):
            self.writer.capture(**arguments)
        original = dict(self.s3.objects)
        self.table.update_item = update
        recovered = self.writer.capture(**arguments)
        self.assertEqual(recovered["persistence"], "persisted")
        self.assertEqual(self.s3.objects, original)

    def test_existing_oversized_object_is_not_accepted_as_a_truncated_match(self):
        receipt = self.writer.capture(**self.arguments)
        key = "notes/" + receipt["path"]
        self.s3.objects["private-vault", key] = b"x" * (MAX_CAPTURE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "capture_too_large"):
            self.writer._read_existing(key)

    def test_status_checks_published_digest_and_keeps_receipt_when_index_is_unavailable(self):
        receipt = self.writer.capture(**self.arguments)
        def status():
            return self.writer.status(principal="owner-sub", client_id="client-a", operation_id="capture-001")
        self.writer.indexed_sha256 = lambda path: receipt["sha256"]
        self.assertEqual(status()["indexing"], "indexed")
        self.writer.indexed_sha256 = lambda path: None
        self.assertEqual(status()["indexing"], "pending")
        self.writer.indexed_sha256 = lambda path: "different-digest"
        self.assertEqual(status()["indexing"], "superseded")
        def unavailable(_):
            raise ValueError("index_unavailable")
        self.writer.indexed_sha256 = unavailable
        self.assertEqual(status()["indexing"], "not_checked")
        self.assertEqual(status()["persistence"], "persisted")
        def disconnected(_):
            raise EndpointConnectionError(endpoint_url="https://synthetic.invalid")
        self.writer.indexed_sha256 = disconnected
        self.assertEqual(status()["indexing"], "not_checked")
        self.assertEqual(status()["persistence"], "persisted")

    def test_owner_grant_is_bounded_and_cannot_replace_active_grant(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            owner_file = Path(directory) / "owner.json"
            owner_file.write_text('{"sub":"owner-sub"}')
            session = FakeSession()
            result = apply_grant(session, owner_file, "client-a", ["kb:capture"], [],
                                 ["Ideas/"], 24)
            self.assertEqual(result["capture_prefixes"], ["Ideas/"])
            self.assertEqual(session.grant["Scopes"], ["kb:capture"])
            with self.assertRaisesRegex(RuntimeError, "grant_exists"):
                apply_grant(FakeSession(exists=True), owner_file, "client-a", ["kb:capture"], [],
                            ["Ideas/"], 24)
            approved = apply_grant(FakeSession(), owner_file, "client-a", ["kb:capture"], [],
                                   ["Resources/_Review/AI Learning/"], 90 * 24)
            self.assertEqual(approved["capture_prefixes"], ["Resources/_Review/AI Learning/"])
            self.assertLessEqual(approved["expires_at"] - time.time(), 90 * 86400)
            with self.assertRaisesRegex(ValueError, "expires_hours_out_of_range"):
                apply_grant(FakeSession(), owner_file, "client-a", ["kb:capture"], [], ["Ideas/"], 2161)
            with self.assertRaisesRegex(ValueError, "invalid_capture_destination"):
                apply_grant(FakeSession(), owner_file, "client-a", ["kb:capture"], [],
                            ["Wiki/"], 24)


if __name__ == "__main__":
    unittest.main()
