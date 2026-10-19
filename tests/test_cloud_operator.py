"""Synthetic checks for explicit owner-only setup; no Google or AWS calls."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from tools.google_owner_subject import private_write
from tools.verify_cloud_mcp import NOTE, provision_mock_grant


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.owner = Path(self.directory.name) / "owner.json"
        private_write(self.owner, json.dumps({"sub": "synthetic-owner"}))
        self.session, self.cfn, self.table, self.runtime = Mock(), Mock(), Mock(), Mock()
        self.session.client.side_effect = lambda name: {"cloudformation": self.cfn, "lambda": self.runtime}[name]
        self.cfn.describe_stacks.side_effect = lambda StackName: {"Stacks": [{"Outputs": [
            {"OutputKey": key, "OutputValue": value} for key, value in
            ({"HttpApiId": "synthetic"} if StackName == "pkb-dev-bootstrap" else
             {"ControlTableName": "pkb-dev-control"}).items()]}]}
        self.runtime.get_function_configuration.return_value = {
            "Environment": {"Variables": {"PKB_OWNER_SUB": "synthetic-owner"}}}
        self.session.resource.return_value.Table.return_value = self.table
        self.url = "https://synthetic.execute-api.ap-southeast-2.amazonaws.com/mcp"

    def test_private_files_are_restricted_and_never_overwritten(self):
        self.assertEqual(self.owner.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            private_write(self.owner, "replacement")
        self.assertEqual(json.loads(self.owner.read_text())["sub"], "synthetic-owner")

    def test_explicit_grant_is_short_lived_and_exactly_mock_only(self):
        provision_mock_grant(self.session, self.url, self.owner, "synthetic-client")
        request = self.table.put_item.call_args.kwargs
        self.assertEqual(request["ConditionExpression"], "attribute_not_exists(PK)")
        self.assertEqual(request["Item"]["Prefixes"], [NOTE])
        self.assertEqual(request["Item"]["Scopes"], ["kb:read"])
        self.assertTrue(request["Item"]["SyntheticOnly"])
        self.assertLessEqual(request["Item"]["ExpiresAt"] - time.time(), 1800)

    def test_wrong_endpoint_and_owner_fail_before_grant_write(self):
        with self.assertRaises(ValueError):
            provision_mock_grant(self.session, "https://unexpected.example/mcp", self.owner, "synthetic-client")
        self.runtime.get_function_configuration.return_value["Environment"]["Variables"]["PKB_OWNER_SUB"] = "another-owner"
        with self.assertRaises(ValueError):
            provision_mock_grant(self.session, self.url, self.owner, "synthetic-client")
        self.table.put_item.assert_not_called()


if __name__ == "__main__":
    unittest.main()
