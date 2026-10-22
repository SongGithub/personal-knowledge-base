"""Synthetic SDK-response checks; these do not assert live AWS deployment."""
from io import BytesIO
import unittest

import boto3
from botocore.response import StreamingBody
from botocore.stub import Stubber

from cloud_kb.storage import S3Notes, normalize_path, permitted, validate_capture_prefix


class CloudStorageTests(unittest.TestCase):
    def test_capture_supports_ordinary_folders_and_rejects_protected_destinations(self):
        for prefix in ("Ideas/", "Projects/", "Areas/", "Resources/", "Personal Facts/", "Templates/",
                       "Areas/Career/", "Resources/_Review/AI Learning/"):
            with self.subTest(prefix=prefix):
                self.assertEqual(validate_capture_prefix(prefix), prefix)
        for prefix in ("Wiki/", "Archive/", "Clippings/", "Ideas/../Wiki/", "Ideas//",
                       "Areas/Source Snapshots/", "Resources/Archive/", "Areas/AGENTS.md/", "Ideas/Wiki/"):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                validate_capture_prefix(prefix)

    def test_paths_and_grants(self):
        for path in ("../private.md", "/absolute.md", "Wiki//note.md", "Wiki/./note.md", "Wiki\\note.md", ".env", "notes.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                normalize_path(path)
        self.assertTrue(permitted("Resources/mock.md", ["Resources/"]))
        self.assertFalse(permitted("Resources-secret/mock.md", ["Resources/"]))

    def test_reads_markdown_and_revision_without_an_index(self):
        client = boto3.client("s3", region_name="ap-southeast-2", aws_access_key_id="synthetic", aws_secret_access_key="synthetic")
        raw = "# Mock\nSynthetic citrus orchard. 合成测试。\n".encode()
        with Stubber(client) as stub:
            stub.add_response("get_object", {
                "Body": StreamingBody(BytesIO(raw), len(raw)), "ContentLength": len(raw),
                "VersionId": "synthetic-v1", "ETag": '"synthetic"',
            }, {"Bucket": "synthetic-vault", "Key": "notes/Resources/mock.md"})
            note = S3Notes(client, "synthetic-vault").fetch("Resources/mock.md")
            self.assertIn("合成测试", note["content"])
            self.assertEqual(note["revision"], "synthetic-v1")
            self.assertEqual(note["indexing"], "not_checked")
            stub.assert_no_pending_responses()


if __name__ == "__main__":
    unittest.main()
