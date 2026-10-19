#!/usr/bin/env python3
"""Deploy the reviewed development MCP application from the trusted deployment pipeline.

AWS SDK configuration supplies credentials. No .env/key handling, IAM bootstrap,
Google credentials, owner-grant creation or private KB migration occurs here.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

import boto3
from botocore.exceptions import ClientError, WaiterError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.seed_mock_kb import publish


@dataclass(frozen=True)
class Deployment:
    execution_role: str
    auth_secret: str
    owner_sub: str
    redirects: str
    seed_mock: bool = False

    @classmethod
    def from_environment(cls):
        names = ("CFN_EXECUTION_ROLE_ARN", "AUTH_SECRET_ARN", "GOOGLE_OWNER_SUB", "CLIENT_REDIRECT_URIS")
        values = [os.environ[name] for name in names]
        if not all(values):
            raise ValueError("Missing private application configuration")
        callbacks = json.loads(values[3])
        if not isinstance(callbacks, list) or not callbacks:
            raise ValueError("Configure exact OAuth client callbacks")
        return cls(*values, seed_mock=os.environ.get("MCP_SEED_MOCK") == "true")


def outputs(cfn, stack):
    response = cfn.describe_stacks(StackName=stack)["Stacks"][0]
    return {item["OutputKey"]: item["OutputValue"] for item in response.get("Outputs", [])}


def upload_release(s3, bucket, path):
    raw = path.read_bytes()
    if len(raw) > 50 * 1024 * 1024:
        raise ValueError("Release exceeds the reviewed compressed-size bound")
    digest = hashlib.sha256(raw).hexdigest()
    key = f"releases/{digest}.zip"
    try:
        response = s3.put_object(Bucket=bucket, Key=key, Body=raw,
                                 ServerSideEncryption="AES256", ContentType="application/zip", IfNoneMatch="*")
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
            raise
        response = s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            if body.read(len(raw) + 1) != raw:
                raise RuntimeError("Existing code artifact differs from its content-addressed name")
        finally:
            body.close()
    version = response.get("VersionId")
    if not version or version == "null":
        raise RuntimeError("Code releases require a versioned bucket")
    return key, version, digest


def recover_empty_application(cfn, execution_role):
    """Remove only rolled-back, empty application metadata so CREATE can retry."""
    stack = "pkb-dev-application"
    allowed = {"AWS::Lambda::Function", "AWS::Lambda::Permission",
               "AWS::ApiGatewayV2::Integration", "AWS::ApiGatewayV2::Route", "AWS::ApiGatewayV2::Stage"}
    for page in cfn.get_paginator("list_stack_resources").paginate(StackName=stack):
        for resource in page["StackResourceSummaries"]:
            if resource["ResourceType"] not in allowed or resource["ResourceStatus"] != "DELETE_COMPLETE":
                raise RuntimeError("Failed application still owns resources; automatic recovery refused")
    cfn.delete_stack(StackName=stack, RoleARN=execution_role)
    cfn.get_waiter("stack_delete_complete").wait(StackName=stack, WaiterConfig={"Delay": 3, "MaxAttempts": 100})


def deploy(session, configuration, release):
    cfn, s3 = session.client("cloudformation"), session.client("s3")
    trust = outputs(cfn, "pkb-dev-bootstrap")
    foundation = outputs(cfn, "pkb-dev-foundation")
    if (trust["CloudFormationExecutionRoleArn"] != configuration.execution_role or
            trust["AuthSecretArn"] != configuration.auth_secret or
            foundation["AuthSecretArn"] != configuration.auth_secret):
        raise RuntimeError("Bootstrap, foundation and application access configuration disagree")
    api_id = trust["HttpApiId"]
    if not re.fullmatch(r"[a-z0-9]+", api_id):
        raise RuntimeError("Invalid anchored API identity")
    key, version, digest = upload_release(s3, foundation["ReleaseBucketName"], release)
    parameters = {
        "ProjectName": "pkb", "Environment": "dev", "HttpApiId": api_id,
        "ReleaseBucket": foundation["ReleaseBucketName"], "ReleaseKey": key, "ReleaseVersion": version,
        "VaultBucket": foundation["DataBucketName"], "IndexBucket": foundation["IndexBucketName"],
        "ControlTable": foundation["ControlTableName"], "ApiExecutionRoleArn": foundation["ApiExecutionRoleArn"],
        "IngestionExecutionRoleArn": foundation["IngestionExecutionRoleArn"],
        "IngestionQueueArn": foundation["IngestionQueueArn"],
        "EnableIngestion": os.environ.get("PKB_ENABLE_INGESTION", "false"),
        "AuthSecretArn": configuration.auth_secret, "OwnerGoogleSubject": configuration.owner_sub,
        "ClientRedirectUris": configuration.redirects,
    }
    stack = "pkb-dev-application"
    kind = "UPDATE"
    try:
        existing = cfn.describe_stacks(StackName=stack)["Stacks"][0]
        if existing["StackStatus"] == "ROLLBACK_COMPLETE":
            recover_empty_application(cfn, configuration.execution_role)
            kind = "CREATE"
    except ClientError as error:
        if error.response["Error"]["Code"] != "ValidationError" or "does not exist" not in error.response["Error"].get("Message", ""):
            raise
        kind = "CREATE"
    change = "release-" + digest[:20] + "-" + uuid.uuid4().hex[:12]
    cfn.create_change_set(
        StackName=stack, ChangeSetName=change, ChangeSetType=kind,
        TemplateBody=(ROOT / "infra/application.template.json").read_text(),
        Parameters=[{"ParameterKey": key, "ParameterValue": value} for key, value in parameters.items()],
        RoleARN=configuration.execution_role, Capabilities=["CAPABILITY_NAMED_IAM"],
        Tags=[{"Key": "Project", "Value": "pkb"}, {"Key": "Environment", "Value": "dev"}],
    )
    execute = True
    try:
        cfn.get_waiter("change_set_create_complete").wait(StackName=stack, ChangeSetName=change, WaiterConfig={"Delay": 3, "MaxAttempts": 100})
    except WaiterError:
        detail = cfn.describe_change_set(StackName=stack, ChangeSetName=change)
        reason = detail.get("StatusReason", "")
        if detail.get("Status") != "FAILED" or not any(text in reason for text in ("didn't contain changes", "No updates are to be performed")):
            raise RuntimeError("Application change set did not become executable; inspect private AWS events") from None
        cfn.delete_change_set(StackName=stack, ChangeSetName=change)
        execute = False
    if execute:
        cfn.execute_change_set(StackName=stack, ChangeSetName=change)
        waiter = "stack_create_complete" if kind == "CREATE" else "stack_update_complete"
        cfn.get_waiter(waiter).wait(StackName=stack, WaiterConfig={"Delay": 5, "MaxAttempts": 180})
    if configuration.seed_mock:
        publish(s3, session.resource("dynamodb").Table(foundation["ControlTableName"]),
                foundation["DataBucketName"], foundation["IndexBucketName"])
    endpoint = outputs(cfn, stack)["McpEndpoint"]
    if endpoint != f"https://{api_id}.execute-api.ap-southeast-2.amazonaws.com/mcp":
        raise RuntimeError("Unexpected deployment endpoint")
    with urlopen(endpoint.removesuffix("/mcp") + "/healthz", timeout=30) as health:
        if health.status != 200 or json.loads(health.read(4096)).get("status") != "up":
            raise RuntimeError("Deployed application liveness check failed")
    request = Request(endpoint, data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
                      headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    try:
        with urlopen(request, timeout=30):
            raise RuntimeError("Unauthenticated MCP access was not rejected")
    except HTTPError as error:
        if error.code != 401 or not error.headers.get("WWW-Authenticate", "").startswith("Bearer"):
            raise RuntimeError("Deployed MCP did not reach its authentication boundary") from None
    if os.environ.get("PKB_ENABLE_INGESTION") == "true":
        queue = session.client("sqs")
        run_id = uuid.uuid4().hex
        queue.send_message(QueueUrl=foundation["IngestionQueueUrl"],
                           MessageBody=json.dumps({"kind": "reconcile", "source": "pipeline", "run_id": run_id}))
        table = session.resource("dynamodb").Table(foundation["ControlTableName"])
        deadline = time.monotonic() + 720
        while time.monotonic() < deadline:
            item = table.get_item(Key={"PK": "JOB#" + run_id, "SK": "STATUS"},
                                  ConsistentRead=True).get("Item", {})
            if item.get("Status") in {"published", "unchanged"} and item.get("SnapshotId"):
                break
            time.sleep(10)
        else:
            raise RuntimeError("Cloud hybrid index did not become active within 12 minutes")
    return {"deployment": "complete", "release_sha256": digest, "unauthenticated_denied": True,
            "mock_seeded": configuration.seed_mock,
            "cloud_index": "hybrid-active" if os.environ.get("PKB_ENABLE_INGESTION") == "true" else "not_checked",
            "google_authenticated_read": "pending_owner_verification"}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: deploy_cloud_app.py /absolute/path/release.zip")
    print(json.dumps(deploy(boto3.Session(region_name="ap-southeast-2"), Deployment.from_environment(), Path(sys.argv[1]))))
