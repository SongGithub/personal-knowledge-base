"""AWS-native trust and bootstrap checks with no real AWS mutations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from tools.aws_session import session_from_file
from tools.bootstrap_native_pipeline import bootstrap


class NativePipelineTests(unittest.TestCase):
    def test_native_template_has_service_trust_and_no_identity_provider(self):
        template = json.loads(Path("infra/native-pipeline.template.json").read_text())
        types = {item["Type"] for item in template["Resources"].values()}
        self.assertNotIn("AWS::IAM::OIDCProvider", types)
        self.assertNotIn("GitHubDeploymentRole", template["Resources"])
        project = template["Resources"]["NativePipeline"]["Properties"]
        self.assertFalse(project["Environment"]["PrivilegedMode"])
        self.assertEqual(project["ConcurrentBuildLimit"], 1)
        self.assertEqual(project["TimeoutInMinutes"], 30)
        self.assertEqual(project["SourceVersion"], {"Ref": "SourceCommit"})
        trust = template["Resources"]["NativeBuildRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
        self.assertEqual(trust["Principal"], {"Service": "codebuild.amazonaws.com"})
        self.assertIn("aws:SourceArn", trust["Condition"]["ArnEquals"])

    def test_local_credential_file_is_parsed_without_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.env"
            path.write_text("AWS_ACCESS_KEY_ID=synthetic-id\nAWS_ACCESS_KEY='$(must-not-execute)'\n")
            with patch("tools.aws_session.boto3.Session") as session:
                session_from_file(path)
                self.assertEqual(session.call_args.kwargs["aws_secret_access_key"], "$(must-not-execute)")

    def test_review_only_does_not_execute_or_start_build(self):
        session, cfn = Mock(), Mock()
        session.client.return_value = cfn
        cfn.describe_stacks.side_effect = ClientError({"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")
        cfn.describe_change_set.return_value = {"Changes": []}
        result = bootstrap(session, "a" * 40)
        self.assertEqual(result["status"], "review_only")
        cfn.execute_change_set.assert_not_called()
        request = cfn.create_change_set.call_args.kwargs
        private = next(item["ParameterValue"] for item in request["Parameters"] if item["ParameterKey"] == "AuthSecretJson")
        self.assertEqual(json.loads(private)["google_client_id"], "PENDING_GOOGLE_CLIENT")

    def test_existing_other_bootstrap_mode_cannot_be_replaced_implicitly(self):
        session, cfn = Mock(), Mock()
        session.client.return_value = cfn
        cfn.describe_stacks.return_value = {"Stacks": [{"Outputs": [{"OutputKey": "GitHubDeploymentRoleArn", "OutputValue": "synthetic"}]}]}
        with self.assertRaisesRegex(RuntimeError, "another delivery mode"):
            bootstrap(session, "b" * 40, apply=True)
        cfn.create_change_set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
