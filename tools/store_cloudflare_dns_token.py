#!/usr/bin/env python3
"""Prompt securely for a Cloudflare token and store it in AWS Secrets Manager."""
import argparse
from getpass import getpass
import sys

import boto3
from botocore.exceptions import ClientError


def store(token, *, secret_name="pkb/dev/cloudflare-dns", region="ap-southeast-2", update=False, session=None):
    if not isinstance(token, str) or not token.strip():
        raise ValueError("A non-empty Cloudflare API token is required")
    secrets = (session or boto3.Session(region_name=region)).client("secretsmanager")
    try:
        existing = secrets.describe_secret(SecretId=secret_name)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
        existing = None
    if existing and not update:
        raise ValueError("Secret already exists; pass --update to rotate its value")
    if existing:
        result = secrets.put_secret_value(SecretId=secret_name, SecretString=token.strip())
        arn = result["ARN"]
    else:
        result = secrets.create_secret(Name=secret_name, Description="Zone-scoped DNS token for Personal KB MCP pipeline",
                                       SecretString=token.strip(), Tags=[{"Key": "Project", "Value": "pkb"},
                                                                        {"Key": "Environment", "Value": "dev"}])
        arn = result["ARN"]
    return arn


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-name", default="pkb/dev/cloudflare-dns")
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--update", action="store_true", help="Rotate an existing secret")
    args = parser.parse_args()
    token = getpass("Cloudflare zone-scoped API token (input hidden): ")
    try:
        print(store(token, secret_name=args.secret_name, region=args.region, update=args.update))
    except (ValueError, ClientError) as error:
        print(f"Could not store token: {error}", file=sys.stderr)
        raise SystemExit(1)
