"""Keep IAM validation active while correcting two provider catalogue entries."""
import json
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


if __name__ == "__main__":
    unittest.main()
