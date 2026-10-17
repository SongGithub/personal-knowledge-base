"""Mock publication checks; no AWS requests leave this process."""
import unittest
from unittest.mock import Mock

from tools.seed_mock_kb import publish


class MockSeedTests(unittest.TestCase):
    def test_refuses_existing_private_index_before_any_write(self):
        s3, table = Mock(), Mock()
        table.get_item.return_value = {"Item": {"SnapshotId": "private"}}
        with self.assertRaisesRegex(RuntimeError, "SyntheticOnly"):
            publish(s3, table, "synthetic-vault", "synthetic-index")
        s3.put_object.assert_not_called()
        table.put_item.assert_not_called()

    def test_publishes_immutable_source_and_snapshot_then_conditional_pointer(self):
        s3, table = Mock(), Mock()
        table.get_item.return_value = {}
        result = publish(s3, table, "synthetic-vault", "synthetic-index")
        self.assertEqual(s3.put_object.call_count, 2)
        for call in s3.put_object.call_args_list:
            self.assertEqual(call.kwargs["IfNoneMatch"], "*")
        descriptor = table.put_item.call_args.kwargs
        self.assertTrue(descriptor["Item"]["SyntheticOnly"])
        self.assertEqual(descriptor["ConditionExpression"], "attribute_not_exists(PK)")
        self.assertEqual(descriptor["Item"]["Sha256"], result["snapshot_sha256"])


if __name__ == "__main__":
    unittest.main()
