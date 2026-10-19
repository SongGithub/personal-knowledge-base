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
import subprocess
import sys
import uuid

from botocore.exceptions import ClientError, WaiterError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.aws_session import session_from_file


MODEL_CONFIG_PATHS = (
    "cloud_kb/embeddings.py", "cloud_kb/ingestion.py", "cloud_kb/search.py",
    "tests/fixtures/cloud-kb/hybrid-benchmark.json", "tools/benchmark_cloud_embeddings.py",
)
DISABLED_CLOUDFLARE_SECRET = "arn:aws:secretsmanager:ap-southeast-2:000000000000:secret:disabled-cloudflare-dns"
DISABLED_DOMAIN_CERTIFICATE = "arn:aws:acm:ap-southeast-2:000000000000:certificate/00000000-0000-0000-0000-000000000000"


def model_config_changed(previous_commit, source_commit, previous_model, current_model):
    """Fail closed when a pinned source cannot be compared with the prior release."""
    if not previous_commit or previous_model != current_model:
        return True
    diff = subprocess.run(
        ["git", "diff", "--name-only", previous_commit, source_commit, "--", *MODEL_CONFIG_PATHS],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return diff.returncode != 0 or bool(diff.stdout.strip())


def bootstrap(session, source_commit, *, apply=False, start_build=False, seed_mock=False,
              approved_embedding_model_arn=None, custom_domain_name=None,
              custom_domain_certificate_arn=None, cloudflare_dns_token_secret_arn=None,
              disable_custom_domain=False):
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
    old_parameters = {item["ParameterKey"]: item.get("ParameterValue", "") for item in previous.get("Parameters", [])} if previous else {}
    selected_domain = "" if disable_custom_domain else (custom_domain_name if custom_domain_name is not None else old_parameters.get("CustomDomainName", ""))
    selected_certificate = ("" if disable_custom_domain else
                            custom_domain_certificate_arn if custom_domain_certificate_arn is not None
                            else old_parameters.get("CustomDomainCertificateArn", ""))
    if selected_certificate == DISABLED_DOMAIN_CERTIFICATE:
        selected_certificate = ""
    selected_cf_secret = (DISABLED_CLOUDFLARE_SECRET if disable_custom_domain else
                          cloudflare_dns_token_secret_arn if cloudflare_dns_token_secret_arn is not None
                          else old_parameters.get("CloudflareDnsTokenSecretArn", DISABLED_CLOUDFLARE_SECRET))
    if selected_domain and (not selected_certificate or selected_cf_secret == DISABLED_CLOUDFLARE_SECRET):
        raise ValueError("Custom hostname requires its Sydney ACM certificate and Cloudflare token secret ARN")
    if not selected_domain and (selected_certificate or selected_cf_secret != DISABLED_CLOUDFLARE_SECRET):
        raise ValueError("Disable the custom hostname, certificate and Cloudflare token together")
    if selected_domain not in ("", "mcp.midu.com.au"):
        raise ValueError("Only the owner-selected MCP hostname is allowed")
    if selected_certificate and not re.fullmatch(
            r"arn:aws:acm:ap-southeast-2:[0-9]{12}:certificate/[a-f0-9-]+", selected_certificate):
        raise ValueError("Custom-domain certificate must be issued by ACM in ap-southeast-2")
    if selected_cf_secret != DISABLED_CLOUDFLARE_SECRET and not re.fullmatch(
            r"arn:aws:secretsmanager:ap-southeast-2:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]+", selected_cf_secret):
        raise ValueError("Cloudflare token must be stored in Secrets Manager in ap-southeast-2")
    selected_model = approved_embedding_model_arn if approved_embedding_model_arn is not None else old_parameters.get("ApprovedEmbeddingModelArn", "")
    require_default_winner = model_config_changed(old_parameters.get("SourceCommit"), source_commit,
                                                   old_parameters.get("ApprovedEmbeddingModelArn", ""), selected_model)
    parameters = [
        {"ParameterKey": "SourceCommit", "ParameterValue": source_commit},
        {"ParameterKey": "EnableMockSeeding", "ParameterValue": "true" if seed_mock else "false"},
        {"ParameterKey": "RequireDefaultWinner", "ParameterValue": "true" if require_default_winner else "false"},
        {"ParameterKey": "CustomDomainName", "ParameterValue": selected_domain},
        {"ParameterKey": "CustomDomainCertificateArn", "ParameterValue": selected_certificate or DISABLED_DOMAIN_CERTIFICATE},
        {"ParameterKey": "CloudflareDnsTokenSecretArn", "ParameterValue": selected_cf_secret},
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
    domain_group = parser.add_mutually_exclusive_group()
    domain_group.add_argument("--custom-domain-name", choices=("mcp.midu.com.au",))
    domain_group.add_argument("--disable-custom-domain", action="store_true")
    parser.add_argument("--custom-domain-certificate-arn")
    parser.add_argument("--cloudflare-dns-token-secret-arn")
    args = parser.parse_args()
    print(json.dumps(bootstrap(session_from_file(args.env_file), args.source_commit, apply=args.apply,
                               start_build=args.start_build, seed_mock=args.seed_mock,
                               approved_embedding_model_arn=args.approved_embedding_model_arn,
                               custom_domain_name=args.custom_domain_name,
                               custom_domain_certificate_arn=args.custom_domain_certificate_arn,
                               cloudflare_dns_token_secret_arn=args.cloudflare_dns_token_secret_arn,
                               disable_custom_domain=args.disable_custom_domain)))
