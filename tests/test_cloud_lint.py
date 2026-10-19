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

    def test_api_note_writes_are_limited_to_ideas(self):
        template = json.loads((Path(__file__).parents[1] /
                               "infra/foundation.template.json").read_text())
        statements = template["Resources"]["ApiExecutionRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
        write = next(item for item in statements if item.get("Sid") == "WriteKnowledgeThroughBackendPolicy")
        self.assertEqual(write["Action"], "s3:PutObject")
        self.assertEqual(write["Resource"], {"Fn::Sub": "${DataBucket.Arn}/notes/Ideas/*"})

    def test_runtime_boundary_only_allows_note_puts_under_ideas(self):
        root = Path(__file__).parents[1]
        for name in ("bootstrap.template.json", "native-pipeline.template.json"):
            template = json.loads((root / "infra" / name).read_text())
            statements = template["Resources"]["RuntimePermissionsBoundary"]["Properties"]["PolicyDocument"]["Statement"]
            write = next(item for item in statements
                         if item.get("Effect") == "Allow" and item.get("Action") == "s3:PutObject")
            vault_resources = [resource["Fn::Sub"] for resource in write["Resource"]
                               if "-vault-" in resource["Fn::Sub"]]
            self.assertEqual(len(vault_resources), 1)
            self.assertTrue(vault_resources[0].endswith("/notes/Ideas/*"))

    def test_custom_domain_create_uses_supported_scoped_conditions(self):
        root = Path(__file__).parents[1]
        for name in ("bootstrap.template.json", "native-pipeline.template.json"):
            template = json.loads((root / "infra" / name).read_text())
            statements = template["Resources"]["CloudFormationExecutionRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
            create = next(item for item in statements if item.get("Sid") == "CreateRegionalMcpDomain")
            conditions = create["Condition"]["StringEquals"]
            self.assertEqual(conditions["apigateway:Request/EndpointType"], "REGIONAL")
            self.assertEqual(conditions["apigateway:Request/SecurityPolicy"], "TLS_1_2")
            self.assertNotIn("apigateway:Request/RoutingMode", conditions)
            self.assertEqual(conditions["aws:RequestTag/Project"], {"Ref": "ProjectName"})
            self.assertEqual(conditions["aws:RequestTag/Environment"], {"Ref": "Environment"})

    def test_custom_domain_provisioning_is_fixed_to_mcp_hostname(self):
        root = Path(__file__).parents[1]
        for name in ("bootstrap.template.json", "native-pipeline.template.json"):
            template = json.loads((root / "infra" / name).read_text())
            policies = [resource["Properties"]["Policies"] for resource in template["Resources"].values()
                        if resource.get("Type") == "AWS::IAM::Role" and
                        resource["Properties"].get("RoleName", {}).get("Fn::Sub") == "${ProjectName}-${Environment}-cfn-execution"]
            self.assertEqual(len(policies), 1)
            statements = policies[0][0]["PolicyDocument"]["Statement"]
            domain = next(item for item in statements
                          if item.get("Sid") == "ManageOnlyMcpDomainAndMappings")
            self.assertTrue(all("mcp.midu.com.au" in resource["Fn::Sub"]
                                for resource in domain["Resource"]))


if __name__ == "__main__":
    unittest.main()
