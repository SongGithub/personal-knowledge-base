"""Verify deployment orchestration with test doubles; never contact AWS."""
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from botocore.exceptions import ClientError

from tools.deploy_cloud_app import Deployment, deploy, upload_release, recover_empty_application


class DeploymentTests(unittest.TestCase):
    def test_custom_domain_requires_issued_sydney_certificate_and_exact_hostname(self):
        base = {"CFN_EXECUTION_ROLE_ARN": "role", "AUTH_SECRET_ARN": "secret",
                "GOOGLE_OWNER_SUB": "owner", "CLIENT_REDIRECT_URIS": '["http://localhost:8765/callback"]'}
        with patch.dict(os.environ, base | {"MCP_CUSTOM_DOMAIN_NAME": "mcp.midu.com.au"}, clear=True):
            with self.assertRaisesRegex(ValueError, "both MCP_CUSTOM_DOMAIN_NAME"):
                Deployment.from_environment()
        valid = base | {"MCP_CUSTOM_DOMAIN_NAME": "mcp.midu.com.au",
                        "MCP_CLOUDFLARE_DNS_TOKEN": "synthetic-cloudflare-token",
                        "MCP_CUSTOM_DOMAIN_CERTIFICATE_ARN":
                            "arn:aws:acm:ap-southeast-2:123456789012:certificate/abcd-1234"}
        with patch.dict(os.environ, valid, clear=True):
            self.assertEqual(Deployment.from_environment().custom_domain_name, "mcp.midu.com.au")
        invalid = valid | {"MCP_CUSTOM_DOMAIN_NAME": "other.midu.com.au"}
        with patch.dict(os.environ, invalid, clear=True):
            with self.assertRaisesRegex(ValueError, "must be mcp.midu.com.au"):
                Deployment.from_environment()

    def test_failed_application_retry_only_deletes_empty_application_metadata(self):
        cfn = Mock()
        cfn.get_paginator.return_value.paginate.return_value = [{"StackResourceSummaries": [
            {"ResourceType": "AWS::Lambda::Function", "ResourceStatus": "DELETE_COMPLETE"}]}]
        recover_empty_application(cfn, "scoped-role")
        cfn.delete_stack.assert_called_once_with(StackName="pkb-dev-application", RoleARN="scoped-role")

    def test_failed_application_recovery_refuses_live_or_data_resources(self):
        for kind, status in [("AWS::Lambda::Function", "CREATE_COMPLETE"),
                             ("AWS::S3::Bucket", "DELETE_COMPLETE")]:
            cfn = Mock()
            cfn.get_paginator.return_value.paginate.return_value = [{"StackResourceSummaries": [
                {"ResourceType": kind, "ResourceStatus": status}]}]
            with self.assertRaisesRegex(RuntimeError, "automatic recovery refused"):
                recover_empty_application(cfn, "scoped-role")
            cfn.delete_stack.assert_not_called()

    def test_upload_replay_requires_matching_versioned_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.zip"
            path.write_bytes(b"synthetic code artifact")
            s3 = Mock()
            s3.put_object.side_effect = ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
            s3.get_object.return_value = {"Body": BytesIO(path.read_bytes()), "VersionId": "synthetic-version"}
            key, version, digest = upload_release(s3, "synthetic-release-bucket", path)
            self.assertEqual(key, "releases/" + digest + ".zip")
            self.assertEqual(version, "synthetic-version")
            self.assertEqual(s3.put_object.call_args.kwargs["IfNoneMatch"], "*")

    def test_configuration_disagreement_stops_before_code_upload(self):
        session, cfn = Mock(), Mock()
        session.client.return_value = cfn
        trust = {"CloudFormationExecutionRoleArn": "configured-role", "AuthSecretArn": "different-secret"}
        foundation = {"AuthSecretArn": "configured-secret"}
        with patch("tools.deploy_cloud_app.outputs", side_effect=[trust, foundation]):
            with self.assertRaisesRegex(RuntimeError, "disagree"):
                deploy(session, Deployment("configured-role", "configured-secret", "owner", "[]"), Path("unused.zip"))
        cfn.put_object.assert_not_called()
        cfn.create_change_set.assert_not_called()

    def test_first_deployment_uses_scoped_role_and_records_google_read_pending(self):
        cfn, s3, acm, session = Mock(), Mock(), Mock(), Mock()
        session.client.side_effect = lambda name: {"cloudformation": cfn, "s3": s3, "acm": acm}[name]
        cfn.describe_stacks.side_effect = ClientError({"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")
        trust = {"CloudFormationExecutionRoleArn": "scoped-role", "AuthSecretArn": "named-secret", "HttpApiId": "mockapi"}
        foundation = {"AuthSecretArn": "named-secret", "ReleaseBucketName": "code-only", "DataBucketName": "notes",
                      "IndexBucketName": "indexes", "ControlTableName": "control", "ApiExecutionRoleArn": "api-runtime",
                      "IngestionExecutionRoleArn": "ingestion-runtime", "IngestionQueueArn": "synthetic-queue-arn"}
        endpoint = "https://mockapi.execute-api.ap-southeast-2.amazonaws.com/mcp"
        health = Mock()
        health.__enter__ = Mock(return_value=health)
        health.__exit__ = Mock(return_value=False)
        health.status = 200
        health.read.return_value = b'{"status":"up"}'
        denied = HTTPError(endpoint, 401, "Unauthorized", {"WWW-Authenticate": "Bearer resource_metadata=\"https://synthetic.invalid\""}, None)
        with patch.dict(os.environ, {"PKB_ENABLE_INGESTION": "false"}), \
                patch("tools.deploy_cloud_app.outputs", side_effect=[trust, foundation, {"McpEndpoint": endpoint}]), \
                patch("tools.deploy_cloud_app.upload_release", return_value=("releases/mock.zip", "version", "digest")), \
                patch("tools.deploy_cloud_app.urlopen", side_effect=[health, denied]):
            result = deploy(session, Deployment("scoped-role", "named-secret", "owner", '["http://localhost:8765/callback"]'), Path("unused.zip"))
        request = cfn.create_change_set.call_args.kwargs
        self.assertEqual(request["RoleARN"], "scoped-role")
        self.assertEqual(request["ChangeSetType"], "CREATE")
        self.assertEqual(request["StackName"], "pkb-dev-application")
        cfn.execute_change_set.assert_called_once()
        session.resource.assert_not_called()
        self.assertEqual(result["google_authenticated_read"], "pending_owner_verification")

    def test_custom_domain_deployment_keeps_origin_health_check_and_reports_dns_target(self):
        cfn, s3, acm, session = Mock(), Mock(), Mock(), Mock()
        session.client.side_effect = lambda name: {"cloudformation": cfn, "s3": s3, "acm": acm}[name]
        cfn.describe_stacks.side_effect = ClientError(
            {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")
        trust = {"CloudFormationExecutionRoleArn": "scoped-role", "AuthSecretArn": "named-secret", "HttpApiId": "mockapi"}
        foundation = {"AuthSecretArn": "named-secret", "ReleaseBucketName": "code-only", "DataBucketName": "notes",
                      "IndexBucketName": "indexes", "ControlTableName": "control", "ApiExecutionRoleArn": "api-runtime",
                      "IngestionExecutionRoleArn": "ingestion-runtime", "IngestionQueueArn": "synthetic-queue-arn"}
        origin = "https://mockapi.execute-api.ap-southeast-2.amazonaws.com/mcp"
        app = {"McpEndpoint": "https://mcp.midu.com.au/mcp", "DefaultMcpEndpoint": origin,
               "CustomDomainRecordTarget": "d-example.execute-api.ap-southeast-2.amazonaws.com",
               "GoogleRedirectUri": "https://mcp.midu.com.au/auth/callback"}
        health = Mock()
        health.__enter__ = Mock(return_value=health)
        health.__exit__ = Mock(return_value=False)
        health.status = 200
        health.read.return_value = b'{"status":"up"}'
        denied = HTTPError(origin, 401, "Unauthorized", {"WWW-Authenticate": "Bearer"}, None)
        configuration = Deployment("scoped-role", "named-secret", "owner",
                                   '["http://localhost:8765/callback"]',
                                   custom_domain_name="mcp.midu.com.au",
                                   custom_domain_certificate_arn=
                                       "arn:aws:acm:ap-southeast-2:123456789012:certificate/abcd-1234",
                                   cloudflare_dns_token="synthetic-cloudflare-token")
        cloudflare = Mock()
        with patch.dict(os.environ, {"PKB_ENABLE_INGESTION": "false"}), \
                patch("tools.deploy_cloud_app.outputs", side_effect=[trust, foundation, app]), \
                patch("tools.deploy_cloud_app.upload_release", return_value=("releases/mock.zip", "version", "digest")), \
                patch("tools.deploy_cloud_app.CloudflareDns", return_value=cloudflare), \
                patch("tools.deploy_cloud_app.ensure_certificate_validated") as validate_cert, \
                patch("tools.deploy_cloud_app.verify_custom_endpoint") as verify_custom, \
                patch("tools.deploy_cloud_app.urlopen", side_effect=[health, denied]) as urlopen:
            result = deploy(session, configuration, Path("unused.zip"))
        request = cfn.create_change_set.call_args.kwargs
        params = {item["ParameterKey"]: item["ParameterValue"] for item in request["Parameters"]}
        self.assertEqual(params["CustomDomainName"], "mcp.midu.com.au")
        self.assertEqual(params["CustomDomainCertificateArn"], configuration.custom_domain_certificate_arn)
        validate_cert.assert_called_once_with(acm, cloudflare, configuration.custom_domain_certificate_arn)
        cloudflare.ensure_cname.assert_called_once_with(
            "mcp.midu.com.au", app["CustomDomainRecordTarget"])
        verify_custom.assert_called_once_with("https://mcp.midu.com.au/mcp")
        self.assertEqual(urlopen.call_args_list[0].args[0], "https://mockapi.execute-api.ap-southeast-2.amazonaws.com/healthz")
        self.assertEqual(urlopen.call_args_list[1].args[0].full_url, origin)
        self.assertEqual(result["custom_domain_record_target"], app["CustomDomainRecordTarget"])
        self.assertEqual(result["custom_domain_dns"], "verified_dns_only")


if __name__ == "__main__":
    unittest.main()
