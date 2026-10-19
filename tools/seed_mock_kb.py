#!/usr/bin/env python3
"""Publish only the repository's synthetic fixture into the development KB.

No resource creation or private-vault scanning. Refuses to overwrite differing
source content or an active index not explicitly marked SyntheticOnly.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import boto3
from botocore.exceptions import ClientError


NOTE = "Resources/MCP Demo/Mock orchard.md"
FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/cloud-kb" / NOTE
CONTRACT = "lexical-sqlite-v1"


def immutable_put(s3, bucket, key, raw, content_type):
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=raw, ContentType=content_type,
                      ServerSideEncryption="AES256", IfNoneMatch="*")
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
            raise
        body = s3.get_object(Bucket=bucket, Key=key)["Body"]
        try:
            if body.read(len(raw) + 1) != raw:
                raise RuntimeError("Refusing to replace differing existing content")
        finally:
            body.close()


def publish(s3, table, vault_bucket, index_bucket):
    raw = FIXTURE.read_bytes()
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE notes(path TEXT PRIMARY KEY,sha256 TEXT NOT NULL,content TEXT NOT NULL)")
        db.execute("INSERT INTO notes VALUES(?,?,?)", (NOTE, hashlib.sha256(raw).hexdigest(), raw.decode()))
        db.commit()
        snapshot = db.serialize()
    digest = hashlib.sha256(snapshot).hexdigest()
    active_key = {"PK": "INDEX#ACTIVE", "SK": "SNAPSHOT"}
    previous = table.get_item(Key=active_key, ConsistentRead=True).get("Item")
    if previous and previous.get("SyntheticOnly") is not True:
        raise RuntimeError("Refusing to replace an index not marked SyntheticOnly")
    immutable_put(s3, vault_bucket, "notes/" + NOTE, raw, "text/markdown; charset=utf-8")
    index_key = f"indexes/mock/{digest}/index.sqlite"
    immutable_put(s3, index_bucket, index_key, snapshot, "application/vnd.sqlite3")
    descriptor = {**active_key, "Contract": CONTRACT, "SnapshotId": digest, "Sha256": digest,
                  "Key": index_key, "SyntheticOnly": True}
    condition = {"ConditionExpression": "attribute_not_exists(PK)"}
    if previous:
        condition = {"ConditionExpression": "SnapshotId = :previous AND SyntheticOnly = :synthetic",
                     "ExpressionAttributeValues": {":previous": previous["SnapshotId"], ":synthetic": True}}
    table.put_item(Item=descriptor, **condition)
    return {"synthetic_note_sha256": hashlib.sha256(raw).hexdigest(), "snapshot_sha256": digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-bucket", required=True)
    parser.add_argument("--index-bucket", required=True)
    parser.add_argument("--control-table", required=True)
    args = parser.parse_args()
    vault = re.fullmatch(r"pkb-dev-vault-([0-9]{12})-ap-southeast-2", args.vault_bucket)
    if (not vault or args.index_bucket != f"pkb-dev-indexes-{vault[1]}-ap-southeast-2" or
            args.control_table != "pkb-dev-control"):
        parser.error("Only the documented pkb-dev Sydney mock destination is supported")
    session = boto3.Session(region_name="ap-southeast-2")
    result = publish(session.client("s3"), session.resource("dynamodb").Table(args.control_table),
                     args.vault_bucket, args.index_bucket)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
