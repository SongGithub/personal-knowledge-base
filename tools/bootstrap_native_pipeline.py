#!/usr/bin/env python3
"""Review/apply the one-time CodeBuild bootstrap using declarative CloudFormation.

No OIDC provider action or organisation-policy change is performed. Source is
pinned to an explicitly selected public commit, with no automatic PR releases.
"""
import argparse
import base64
import json
from pathlib import Path
import re
import secrets
import sys
import uuid

from botocore.exceptions import ClientError, WaiterError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.aws_session import session_from_file


def bootstrap(session, source_commit, *, apply=False, start_build=False, seed_mock=False,
              approved_embedding_model_arn=None):
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("Select an exact 40-character source commit")
    cfn = session.client("cloudformation")
    stack, kind = "pkb-dev-bootstrap", "CREATE"
    previous = None
    try:
        previous = cfn.describe_stacks(StackName=stack)["Stacks"][0]
        if "NativePipelineName" not in {value["OutputKey"] for value in previous.get("Outputs", [])}:
            raise RuntimeError("An existing bootstrap uses another delivery mode; refusing an implicit replacement")
        kind = "UPDATE"
    except ClientError as error:
        if error.response["Error"]["Code"] != "ValidationError" or "does not exist" not in error.response["Error"].get("Message", ""):
            raise
    parameters = [
        {"ParameterKey": "SourceCommit", "ParameterValue": source_commit},
        {"ParameterKey": "EnableMockSeeding", "ParameterValue": "true" if seed_mock else "false"},
    ]
    if approved_embedding_model_arn is not None:
        if not re.fullmatch(r"arn:aws:bedrock:ap-southeast-2::foundation-model/cohere\.embed-multilingual-v3", approved_embedding_model_arn):
            raise ValueError("Only the owner-approved Sydney Cohere embedding model may be enabled")
        parameters.append({"ParameterKey": "ApprovedEmbeddingModelArn", "ParameterValue": approved_embedding_model_arn})
    if previous is None:
        # Deliberately invalid upstream credentials: the endpoint can become live
        # and reject unauthenticated requests, but Google/KB access stays closed.
        auth = {"google_client_id": "PENDING_GOOGLE_CLIENT", "google_client_secret": "NOT_CONFIGURED",
                "jwt_signing_key": secrets.token_urlsafe(48),
                "storage_encryption_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}
        parameters.append({"ParameterKey": "AuthSecretJson", "ParameterValue": json.dumps(auth)})
    else:
        specified = {item["ParameterKey"] for item in parameters}
        parameters.extend({"ParameterKey": item["ParameterKey"], "UsePreviousValue": True}
                          for item in previous.get("Parameters", []) if item["ParameterKey"] not in specified)
    change = "native-" + source_commit[:12] + "-" + uuid.uuid4().hex[:12]
    cfn.create_change_set(StackName=stack, ChangeSetName=change, ChangeSetType=kind,
                          TemplateBody=(ROOT / "infra/native-pipeline.template.json").read_text(),
                          Parameters=parameters, Capabilities=["CAPABILITY_NAMED_IAM"],
                          Tags=[{"Key": "Project", "Value": "pkb"}, {"Key": "Environment", "Value": "dev"}])
    try:
        cfn.get_waiter("change_set_create_complete").wait(StackName=stack, ChangeSetName=change, WaiterConfig={"Delay": 3, "MaxAttempts": 100})
    except WaiterError:
        detail = cfn.describe_change_set(StackName=stack, ChangeSetName=change)
        if detail.get("Status") == "FAILED" and "didn't contain changes" in detail.get("StatusReason", ""):
            cfn.delete_change_set(StackName=stack, ChangeSetName=change)
        else:
            raise RuntimeError("Native bootstrap change set failed; inspect private CloudFormation events") from None
    else:
        detail = cfn.describe_change_set(StackName=stack, ChangeSetName=change)
        print(json.dumps({"change_set": change, "resource_changes": [
            {"action": value["ResourceChange"]["Action"], "logical_id": value["ResourceChange"]["LogicalResourceId"],
             "type": value["ResourceChange"]["ResourceType"]} for value in detail.get("Changes", [])]}), flush=True)
        if not apply:
            return {"status": "review_only", "change_set": change}
        cfn.execute_change_set(StackName=stack, ChangeSetName=change)
        cfn.get_waiter("stack_create_complete" if kind == "CREATE" else "stack_update_complete").wait(
            StackName=stack, WaiterConfig={"Delay": 5, "MaxAttempts": 180})
    observed = cfn.describe_stacks(StackName=stack)["Stacks"][0]
    outputs = {item["OutputKey"]: item["OutputValue"] for item in observed["Outputs"]}
    state = {"stack_status": observed["StackStatus"], "source_commit": source_commit, "outputs": outputs}
    if start_build:
        if not apply:
            raise ValueError("Starting a release requires --apply")
        build = session.client("codebuild").start_build(projectName=outputs["NativePipelineName"], sourceVersion=source_commit)["build"]
        state["build_id"] = build["id"]
    state_path = Path("/private/tmp/pkb-native-state.json")
    state_path.write_text(json.dumps(state))
    state_path.chmod(0o600)
    return {"status": observed["StackStatus"], "pipeline_started": "build_id" in state,
            "google_authenticated_read": "pending_google_configuration"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--start-build", action="store_true")
    parser.add_argument("--seed-mock", action="store_true")
    parser.add_argument("--approved-embedding-model-arn")
    args = parser.parse_args()
    print(json.dumps(bootstrap(session_from_file(args.env_file), args.source_commit, apply=args.apply,
                               start_build=args.start_build, seed_mock=args.seed_mock,
                               approved_embedding_model_arn=args.approved_embedding_model_arn)))
