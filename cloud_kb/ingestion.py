"""Reconcile private S3 Markdown into a complete, immutable hybrid snapshot."""
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
import time

import boto3
from botocore.exceptions import ClientError

from cloud_kb.embeddings import BedrockEmbeddings, CONTRACT as EMBEDDING_CONTRACT, pack
from cloud_kb.search import HYBRID_CONTRACT, MAX_SNAPSHOT_BYTES
from cloud_kb.storage import MAX_NOTE_BYTES, authority, normalize_path


ACTIVE = {"PK": "INDEX#ACTIVE", "SK": "SNAPSHOT"}
CHUNKER = "paragraph-1500-v1"


def chunks(text, limit=1500):
    paragraphs = re.split(r"\n\s*\n", text.strip())
    result, current = [], ""
    for paragraph in paragraphs:
        pieces = [paragraph[i:i + limit] for i in range(0, len(paragraph), limit)] or [""]
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > limit:
                result.append(current)
                current = ""
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        result.append(current)
    return result


def read_snapshot(s3, bucket, descriptor):
    if not descriptor or descriptor.get("Contract") != HYBRID_CONTRACT or descriptor.get("EmbeddingContract") != EMBEDDING_CONTRACT:
        return None
    response = s3.get_object(Bucket=bucket, Key=descriptor["Key"])
    body = response["Body"]
    try:
        raw = body.read(MAX_SNAPSHOT_BYTES + 1)
    finally:
        body.close()
    if len(raw) > MAX_SNAPSHOT_BYTES or hashlib.sha256(raw).hexdigest() != descriptor["Sha256"]:
        raise ValueError("index_integrity_failure")
    return raw


def inventory(s3, bucket):
    found = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="notes/"):
        for item in page.get("Contents", []):
            key = item["Key"]
            try:
                path = normalize_path(key.removeprefix("notes/"))
            except ValueError:
                continue
            found.append((path, key))
    return sorted(found)


def reconcile(s3, table, embeddings, vault_bucket, index_bucket):
    previous = table.get_item(Key=ACTIVE, ConsistentRead=True).get("Item")
    previous_raw = read_snapshot(s3, index_bucket, previous)
    with closing(sqlite3.connect(":memory:")) as db:
        if previous_raw:
            db.deserialize(previous_raw)
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("index_integrity_failure")
        else:
            db.execute("CREATE TABLE notes(path TEXT PRIMARY KEY,tier TEXT NOT NULL,sha256 TEXT NOT NULL,source_revision TEXT NOT NULL)")
            db.execute("CREATE TABLE chunks(path TEXT NOT NULL,ordinal INTEGER NOT NULL,text TEXT NOT NULL,vector BLOB NOT NULL,PRIMARY KEY(path,ordinal))")
            db.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        old = dict(db.execute("SELECT path,sha256 FROM notes"))
        paths = inventory(s3, vault_bucket)
        current = set()
        changed = []
        for path, key in paths:
            response = s3.get_object(Bucket=vault_bucket, Key=key)
            body = response["Body"]
            try:
                raw = body.read(MAX_NOTE_BYTES + 1)
            finally:
                body.close()
            if len(raw) > MAX_NOTE_BYTES:
                raise ValueError("note_too_large")
            content = raw.decode("utf-8-sig")
            digest = hashlib.sha256(raw).hexdigest()
            current.add(path)
            if old.get(path) == digest:
                continue
            changed.append((path, content, digest, response.get("VersionId") or response["ETag"]))
        deleted = set(old) - current
        if not changed and not deleted and previous_raw:
            return {"status": "unchanged", "notes": len(current), "embedded_chunks": 0,
                    "snapshot_id": previous["SnapshotId"]}
        with db:
            for path in deleted:
                db.execute("DELETE FROM chunks WHERE path=?", (path,))
                db.execute("DELETE FROM notes WHERE path=?", (path,))
            for path, content, digest, revision in changed:
                parts = chunks(content)
                vectors = []
                for start in range(0, len(parts), 96):
                    vectors.extend(embeddings.documents(parts[start:start + 96]))
                db.execute("DELETE FROM chunks WHERE path=?", (path,))
                db.execute("INSERT INTO notes(path,tier,sha256,source_revision) VALUES(?,?,?,?) "
                           "ON CONFLICT(path) DO UPDATE SET tier=excluded.tier,sha256=excluded.sha256,source_revision=excluded.source_revision",
                           (path, authority(path, content), digest, revision))
                db.executemany("INSERT INTO chunks VALUES(?,?,?,?)",
                               [(path, number, part, pack(vector)) for number, (part, vector) in enumerate(zip(parts, vectors))])
            db.execute("DELETE FROM metadata")
            db.executemany("INSERT INTO metadata VALUES(?,?)", [("embedding_contract", EMBEDDING_CONTRACT),
                           ("chunker", CHUNKER), ("schema", HYBRID_CONTRACT)])
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("index_integrity_failure")
        if db.execute("SELECT COUNT(*) FROM chunks WHERE length(vector)!=4096").fetchone()[0]:
            raise ValueError("incompatible_embedding_contract")
        snapshot = db.serialize()
        counts = {"notes": db.execute("SELECT COUNT(*) FROM notes").fetchone()[0],
                  "chunks": db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]}
    if len(snapshot) > MAX_SNAPSHOT_BYTES:
        raise ValueError("index_too_large")
    digest = hashlib.sha256(snapshot).hexdigest()
    key = f"indexes/{HYBRID_CONTRACT}/{digest}/index.sqlite"
    try:
        s3.put_object(Bucket=index_bucket, Key=key, Body=snapshot,
                      ContentType="application/vnd.sqlite3", ServerSideEncryption="AES256", IfNoneMatch="*")
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
            raise
    manifest = {"schema": HYBRID_CONTRACT, "embedding_contract": EMBEDDING_CONTRACT,
                "sha256": digest, "counts": counts, "created_at": int(time.time())}
    try:
        s3.put_object(Bucket=index_bucket, Key=f"indexes/{HYBRID_CONTRACT}/{digest}/manifest.json",
                      Body=json.dumps(manifest, sort_keys=True).encode(), ContentType="application/json",
                      ServerSideEncryption="AES256", IfNoneMatch="*")
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
            raise
    descriptor = {**ACTIVE, "Contract": HYBRID_CONTRACT, "EmbeddingContract": EMBEDDING_CONTRACT,
                  "SnapshotId": digest, "Sha256": digest, "Key": key, "SyntheticOnly": False}
    if previous:
        condition = {"ConditionExpression": "SnapshotId = :previous",
                     "ExpressionAttributeValues": {":previous": previous["SnapshotId"]}}
    else:
        condition = {"ConditionExpression": "attribute_not_exists(PK)"}
    table.put_item(Item=descriptor, **condition)
    return {"status": "published", "notes": counts["notes"], "chunks": counts["chunks"],
            "embedded_chunks": sum(len(chunks(content)) for _, content, _, _ in changed),
            "snapshot_id": digest}


def handler(event, _context):
    if not event.get("Records"):
        raise ValueError("ingestion_requires_queue_event")
    session = boto3.Session(region_name="ap-southeast-2")
    table = session.resource("dynamodb").Table(os.environ["PKB_CONTROL_TABLE"])
    result = reconcile(session.client("s3"), table,
                       BedrockEmbeddings(session.client("bedrock-runtime")), os.environ["PKB_VAULT_BUCKET"],
                       os.environ["PKB_INDEX_BUCKET"])
    for record in event["Records"]:
        try:
            message = json.loads(record.get("body", "{}"))
        except ValueError:
            continue
        run_id = message.get("run_id")
        if message.get("source") == "pipeline" and isinstance(run_id, str) and re.fullmatch(r"[0-9a-f]{32}", run_id):
            table.put_item(Item={"PK": "JOB#" + run_id, "SK": "STATUS", "Status": result["status"],
                                 "SnapshotId": result["snapshot_id"], "Notes": result["notes"],
                                 "EmbeddedChunks": result["embedded_chunks"],
                                 "ExpiresAt": int(time.time()) + 86400})
    return {"status": result["status"], "notes": result["notes"],
            "embedded_chunks": result["embedded_chunks"]}
