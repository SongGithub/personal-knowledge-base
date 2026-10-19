"""Keep IAM validation active while correcting two provider catalogue entries."""
import json
from pathlib import Path
import unittest

from tools.lint_infra import validate


class InfraLintTests(unittest.TestCase):
    def permissions(self, action):
        template = {"Resources": {"Policy": {"Type": "AWS::IAM::ManagedPolicy", "Properties": {
            "PolicyDocument": {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Action": action, "Resource": "*"}]}}}}}
        return [match for match in validate(json.dumps(template)) if match.rule.id == "W3037"]

    def test_declared_provider_tag_actions_are_known(self):
        self.assertEqual(self.permissions(["apigateway:TagResource", "apigateway:UntagResource"]), [])

    def test_misspelled_iam_actions_still_fail(self):
        self.assertTrue(self.permissions("apigateway:TagResorce"))

    def test_api_note_writes_are_limited_to_raw_capture_trees(self):
        template = json.loads((Path(__file__).parents[1] /
                               "infra/foundation.template.json").read_text())
        statements = template["Resources"]["ApiExecutionRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
        write = next(item for item in statements if item.get("Sid") == "WriteKnowledgeThroughBackendPolicy")
        self.assertEqual(write["Action"], "s3:PutObject")
        self.assertEqual(write["Resource"], [
            {"Fn::Sub": "${DataBucket.Arn}/notes/Ideas/*"},
            {"Fn::Sub": "${DataBucket.Arn}/notes/Resources/_Review/AI Learning/*"},
        ])

    def test_runtime_boundary_only_allows_note_puts_under_raw_capture_trees(self):
        root = Path(__file__).parents[1]
        for name in ("bootstrap.template.json", "native-pipeline.template.json"):
            template = json.loads((root / "infra" / name).read_text())
            statements = template["Resources"]["RuntimePermissionsBoundary"]["Properties"]["PolicyDocument"]["Statement"]
            write = next(item for item in statements
                         if item.get("Effect") == "Allow" and item.get("Action") == "s3:PutObject")
            vault_resources = [resource["Fn::Sub"] for resource in write["Resource"]
                               if "-vault-" in resource["Fn::Sub"]]
            prefix = "arn:${AWS::Partition}:s3:::${ProjectName}-${Environment}-vault-${AWS::AccountId}-${AWS::Region}/notes/"
            self.assertEqual(set(vault_resources), {
                prefix + "Ideas/*", prefix + "Resources/_Review/AI Learning/*",
            })


if __name__ == "__main__":
    unittest.main()
