#!/usr/bin/env python3
"""Grant one verified owner/client bounded KB read and/or raw-note capture access.

This owner-run tool never prints the owner subject or client ID. It refuses to
replace an existing grant; revoke it explicitly before creating a replacement.
"""
import argparse
import json
from pathlib import Path
import re
import time

import boto3
from botocore.exceptions import ClientError

from cloud_kb.storage import normalize_path, validate_capture_prefix, validate_update_prefix
from tools.aws_session import session_from_file


def apply_grant(session, owner_file, client_id, scopes, read_prefixes,
                capture_prefixes, expires_hours, update_prefixes=()):
    owner = json.loads(owner_file.read_text())
    subject = owner.get("sub")
    if not isinstance(subject, str) or not subject or not isinstance(client_id, str) or not client_id:
        raise ValueError("verified_owner_and_client_id_required")
    if not 1 <= expires_hours <= 2160:
        raise ValueError("expires_hours_out_of_range")
    if not scopes or not set(scopes) <= {"kb:read", "kb:capture", "kb:update"}:
        raise ValueError("invalid_scopes")
    for prefix in read_prefixes:
        normalize_path(prefix.rstrip("/") + "/scope.md")
    for prefix in capture_prefixes:
        validate_capture_prefix(prefix)
    for prefix in update_prefixes:
        validate_update_prefix(prefix)
    if ("kb:read" in scopes) != bool(read_prefixes):
        raise ValueError("read_scope_requires_explicit_prefixes")
    if ("kb:capture" in scopes) != bool(capture_prefixes):
        raise ValueError("capture_scope_requires_explicit_prefixes")
    if ("kb:update" in scopes) != bool(update_prefixes) or (update_prefixes and "kb:read" not in scopes):
        raise ValueError("update_scope_requires_explicit_prefixes_and_read")
    function = session.client("lambda").get_function_configuration(FunctionName="pkb-dev-api")
    if function["Environment"]["Variables"].get("PKB_OWNER_SUB") != subject:
        raise ValueError("verified_owner_mismatch")
    item = {
        "PK": "GRANT#" + subject,
        "SK": "CLIENT#" + client_id,
        "Revoked": False,
        "CreatedAt": int(time.time()),
        "ExpiresAt": int(time.time()) + expires_hours * 3600,
        "Scopes": sorted(set(scopes)),
        "Prefixes": sorted(set(read_prefixes)),
        "CapturePrefixes": sorted(set(capture_prefixes)),
        "UpdatePrefixes": sorted(set(update_prefixes)),
        "PolicyRevision": "ordinary-update-v1",
    }
    table = session.resource("dynamodb").Table("pkb-dev-control")
    try:
        table.put_item(Item=item,
                       ConditionExpression="attribute_not_exists(PK) OR ExpiresAt <= :now OR Revoked = :revoked",
                       ExpressionAttributeValues={":now": int(time.time()), ":revoked": True})
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in {"ConditionalCheckFailedException", "ConditionalCheckFailed"}:
            raise RuntimeError("grant_exists; revoke it explicitly before replacing") from None
        raise RuntimeError("grant_write_failed") from None
    return {"status": "granted", "scopes": item["Scopes"],
            "read_prefix_count": len(item["Prefixes"]),
            "capture_prefixes": item["CapturePrefixes"], "update_prefixes": item["UpdatePrefixes"],
            "expires_at": item["ExpiresAt"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aws-env-file", type=Path,
                        help="Optional ignored AWS credential file; omit to use the normal AWS SDK chain/SSO profile")
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--scope", action="append", choices=("kb:read", "kb:capture", "kb:update"), required=True)
    parser.add_argument("--read-prefix", action="append", default=[])
    parser.add_argument("--capture-prefix", action="append", default=[])
    parser.add_argument("--update-prefix", action="append", default=[])
    parser.add_argument("--expires-hours", type=int, default=24)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", args.client_id):
        parser.error("client ID contains invalid characters")
    session = (session_from_file(args.aws_env_file) if args.aws_env_file
               else boto3.Session(region_name="ap-southeast-2"))
    print(json.dumps(apply_grant(session, args.owner_file, args.client_id, args.scope,
                                 args.read_prefix, args.capture_prefix, args.expires_hours, args.update_prefix)))


if __name__ == "__main__":
    main()
