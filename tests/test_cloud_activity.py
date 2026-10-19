"""Local-only activity append, conflict and crash-recovery evidence."""
import hashlib
import unittest
from unittest.mock import patch
from urllib.parse import quote

from botocore.exceptions import ClientError

from cloud_kb.activity import ACTIVITY_PATH, ActivityLog
from cloud_kb.config import Settings
from cloud_kb.storage import MAX_NOTE_BYTES
from cloud_kb.writer import LearningWriter
from tests.test_cloud_writer import FakeS3, FakeTable


KEY = "notes/" + ACTIVITY_PATH


class LogS3(FakeS3):
    def __init__(self):
        super().__init__()
        self.objects["private-vault", KEY] = b"# Activity log\n\nOwner entry.\n"
        self.log_puts = 0
        self.before_put = None

    def get_object(self, *, Bucket, Key, VersionId=None):
        response = super().get_object(Bucket=Bucket, Key=Key)
        raw = self.objects[Bucket, Key]
        response.update(ETag='"' + hashlib.sha256(raw).hexdigest() + '"',
                        Metadata={"owner-metadata": "preserved"})
        if Key == KEY:
            response["VersionId"] = "log-v" + str(self.log_puts)
            if VersionId is not None:
                assert response["VersionId"] == VersionId
        return response

    def put_object(self, *, Bucket, Key, Body, IfMatch=None, **kwargs):
        if Key != KEY:
            return super().put_object(Bucket=Bucket, Key=Key, Body=Body, **kwargs)
        assert kwargs["ServerSideEncryption"] == "AES256"
        assert kwargs["Metadata"] == {"owner-metadata": "preserved"}
        if self.before_put:
            self.before_put(self)
        current = self.objects[Bucket, Key]
        if IfMatch != '"' + hashlib.sha256(current).hexdigest() + '"':
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.log_puts += 1
        self.objects[Bucket, Key] = Body
        return {"VersionId": "log-v" + str(self.log_puts)}


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.s3, self.table = LogS3(), FakeTable()
        self.arguments = dict(
            principal="owner-sub", client_id="client-a", operation_id="capture-001",
            destination="Resources/_Review/AI Learning/", title="Synthetic learning",
            markdown="Synthetic raw learning.", origin="Synthetic conversation", created_date="2026-10-20",
            evidence=[], inference_labels=["ai-inference"],
            allowed_prefixes=["Resources/_Review/AI Learning/"],
        )
        self.writer = LearningWriter(self.s3, self.table, "private-vault",
                                     activity_log=ActivityLog(self.s3, "private-vault"))

    def capture(self):
        return self.writer.capture(**self.arguments)

    def status(self):
        return self.writer.status(principal="owner-sub", client_id="client-a", operation_id="capture-001")

    def test_append_preserves_owner_content_and_replays_once(self):
        original = self.s3.objects["private-vault", KEY]
        first = self.capture()
        self.assertEqual(first["activity_audit"], "recorded")
        self.assertEqual(first["activity_log_revision"], "log-v1")
        self.assertEqual(first["revision"], "synthetic-v1")
        log = self.s3.objects["private-vault", KEY]
        self.assertTrue(log.startswith(original))
        self.assertIn(first["sha256"].encode(), log)
        self.assertIn(("../" + quote(first["path"], safe="/")).encode(), log)
        self.assertEqual(self.capture()["activity_audit"], "recorded")
        self.assertEqual(self.status()["activity_audit"], "recorded")
        self.assertEqual(self.s3.log_puts, 1)

    def test_concurrent_owner_edit_is_preserved_after_precondition_retry(self):
        def concurrent_edit(s3):
            s3.objects["private-vault", KEY] += b"Concurrent owner edit.\n"
            s3.before_put = None
        self.s3.before_put = concurrent_edit
        self.assertEqual(self.capture()["activity_audit"], "recorded")
        self.assertIn(b"Concurrent owner edit.\n", self.s3.objects["private-vault", KEY])
        self.assertEqual(self.s3.log_puts, 1)

    def test_busy_log_keeps_note_persisted_and_audit_retryable(self):
        self.s3.before_put = lambda s3: s3.objects.__setitem__(("private-vault", KEY),
                                       s3.objects["private-vault", KEY] + b"Owner edit.\n")
        first = self.capture()
        self.assertEqual(first["persistence"], "persisted")
        self.assertEqual(first["activity_audit"], "pending")
        self.assertEqual(first["activity_audit_error"], "activity_log_busy")
        self.s3.before_put = None
        self.assertEqual(self.capture()["activity_audit"], "recorded")

    def test_crash_after_append_recovers_without_duplicate_or_timestamp_drift(self):
        update = self.table.update_item
        def unavailable(**kwargs):
            if ":audit_revision" in kwargs["ExpressionAttributeValues"]:
                raise ClientError({"Error": {"Code": "InternalServerError"}}, "UpdateItem")
            return update(**kwargs)
        self.table.update_item = unavailable
        with patch("cloud_kb.writer.time.time", return_value=1_700_000_000):
            first = self.capture()
        self.assertEqual(first["activity_audit_error"], "activity_state_unavailable")
        self.assertEqual(self.status()["activity_audit"], "pending")
        self.table.update_item = update
        with patch("cloud_kb.writer.time.time", return_value=1_700_000_600):
            self.assertEqual(self.capture()["activity_audit"], "recorded")
        self.assertEqual(self.s3.log_puts, 1)
        self.assertEqual(self.s3.objects["private-vault", KEY].count(b"<!-- kb-capture-audit:"), 1)

    def test_missing_full_or_invalid_log_is_never_replaced(self):
        for raw, error in ((None, "activity_log_missing"), (b"x" * MAX_NOTE_BYTES, "activity_log_too_large"),
                           (b"\xff", "activity_log_invalid_utf8")):
            with self.subTest(error=error):
                if raw is None:
                    self.s3.objects.pop(("private-vault", KEY), None)
                else:
                    self.s3.objects["private-vault", KEY] = raw
                receipt = self.capture()
                self.assertEqual(receipt["persistence"], "persisted")
                self.assertEqual(receipt["activity_audit_error"], error)
                self.assertEqual(self.s3.objects.get(("private-vault", KEY)), raw)
        with patch.object(self.s3, "get_object", side_effect=ClientError(
                {"Error": {"Code": "AccessDenied"}}, "GetObject")):
            receipt = self.capture()
        self.assertEqual(receipt["persistence"], "persisted")
        self.assertEqual(receipt["activity_audit_error"], "activity_log_unavailable")
        self.assertEqual(self.s3.log_puts, 0)

    def test_legacy_recorded_row_is_not_mistaken_for_a_log_append(self):
        self.writer.activity_log = None
        self.capture()
        item = next(iter(self.table.items.values()))
        item["ActivityAudit"] = "recorded"
        self.assertEqual(self.status()["activity_audit"], "pending")
        self.assertEqual(self.status()["activity_audit_reason"], "not_enabled")
        self.assertEqual(self.s3.log_puts, 0)

    def test_readback_failure_is_visible_and_retry_recognises_saved_entry(self):
        read = self.writer.activity_log._read
        def failed_readback(version=None):
            if version:
                raise RuntimeError("activity_log_unavailable")
            return read()
        with patch.object(self.writer.activity_log, "_read", side_effect=failed_readback):
            receipt = self.capture()
        self.assertEqual(receipt["persistence"], "persisted")
        self.assertEqual(receipt["activity_audit"], "pending")
        self.assertEqual(receipt["activity_audit_error"], "activity_log_unavailable")
        self.assertEqual(self.capture()["activity_audit"], "recorded")
        self.assertEqual(self.s3.log_puts, 1)

    def test_tampered_audit_entry_is_not_silently_duplicated(self):
        self.capture()
        item = next(iter(self.table.items.values()))
        item["ActivityAudit"] = "pending"
        self.s3.objects["private-vault", KEY] = self.s3.objects["private-vault", KEY].replace(
            b"Captured unverified learning", b"Changed entry")
        receipt = self.capture()
        self.assertEqual(receipt["activity_audit_error"], "activity_log_entry_conflict")
        self.assertEqual(self.s3.log_puts, 1)

    def test_status_never_appends_and_failed_note_write_never_audits(self):
        self.s3.fail_next = True
        with self.assertRaisesRegex(RuntimeError, "storage_unavailable"):
            self.capture()
        self.assertEqual(self.status()["persistence"], "retryable")
        self.assertEqual(self.s3.log_puts, 0)
        with patch.object(self.writer.activity_log, "append", side_effect=RuntimeError("activity_log_unavailable")):
            self.assertEqual(self.capture()["persistence"], "persisted")
        with patch.object(self.writer.activity_log, "append", side_effect=AssertionError("status must be read-only")):
            self.assertEqual(self.status()["activity_audit"], "pending")

    def test_retry_after_note_state_failure_uses_original_operation_date(self):
        update = self.table.update_item
        def unavailable(**_):
            raise ClientError({"Error": {"Code": "InternalServerError"}}, "UpdateItem")
        self.table.update_item = unavailable
        with patch("cloud_kb.writer.time.time", return_value=1_700_000_000):
            with self.assertRaises(ClientError):
                self.capture()
        self.assertEqual(self.s3.log_puts, 0)
        self.table.update_item = update
        with patch("cloud_kb.writer.time.time", return_value=1_700_086_400):
            self.assertEqual(self.capture()["activity_audit"], "recorded")
        self.assertIn(b"2023-11-14T22:13:20+00:00", self.s3.objects["private-vault", KEY])


class ActivityConfigTests(unittest.TestCase):
    def test_feature_defaults_off_and_invalid_switch_fails_closed(self):
        environment = {"PKB_BASE_URL": "https://synthetic.invalid", "PKB_VAULT_BUCKET": "vault",
                       "PKB_INDEX_BUCKET": "indexes", "PKB_CONTROL_TABLE": "control",
                       "PKB_OWNER_SUB": "owner", "PKB_SECRET_ARN": "secret",
                       "PKB_CLIENT_REDIRECT_URIS": '["http://127.0.0.1/callback"]'}
        with patch.dict("os.environ", environment, clear=True):
            self.assertFalse(Settings.from_environment().activity_log_enabled)
            with patch.dict("os.environ", {"PKB_ACTIVITY_LOG_ENABLED": "true"}):
                self.assertTrue(Settings.from_environment().activity_log_enabled)
            with patch.dict("os.environ", {"PKB_ACTIVITY_LOG_ENABLED": "yes"}):
                with self.assertRaisesRegex(ValueError, "PKB_ACTIVITY_LOG_ENABLED"):
                    Settings.from_environment()


if __name__ == "__main__":
    unittest.main()
