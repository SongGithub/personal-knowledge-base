"""Revision-checked passage edits with durable retries and S3 version recovery."""
from datetime import date as iso_date
import hashlib
import json
import re
import time

from botocore.exceptions import BotoCoreError, ClientError

from cloud_kb.storage import MAX_NOTE_BYTES, normalize_path, permitted, update_requires_review
from cloud_kb.writer import INFERENCE_LABELS


def sha(value):
    return hashlib.sha256(value).hexdigest()


def text(value, name, limit, empty=False):
    if (not isinstance(value, str) or (not empty and not value.strip()) or
            len(value.encode("utf-8")) > limit or
            any(ord(char) < 32 and char not in "\r\n\t" for char in value)):
        raise ValueError("invalid_" + name)
    return value


class NoteUpdater:
    def __init__(self, notes, table, indexed_sha256=None):
        self.notes, self.table, self.indexed_sha256 = notes, table, indexed_sha256

    @staticmethod
    def key(principal, client_id, operation_id):
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", operation_id):
            raise ValueError("invalid_operation_id")
        return {"PK": "OP#" + sha((principal + "\0" + client_id).encode()), "SK": "UPDATE#" + operation_id}

    def get(self, key):
        return self.table.get_item(Key=key, ConsistentRead=True).get("Item")

    def update(self, *, principal, client_id, operation_id, path, expected_revision,
               old_text, new_text, origin, date, evidence_links, inference_labels,
               allowed_prefixes, read_prefixes):
        key = self.key(principal, client_id, operation_id)
        path = normalize_path(path)
        if not permitted(path, allowed_prefixes) or not permitted(path, read_prefixes):
            raise ValueError("forbidden")
        text(expected_revision, "expected_revision", 1024)
        text(old_text, "old_text", 24_576)
        text(new_text, "new_text", 24_576, empty=True)
        text(origin, "origin", 2000)
        try:
            date = iso_date.fromisoformat(date).isoformat()
        except (TypeError, ValueError):
            raise ValueError("invalid_date") from None
        if (not isinstance(evidence_links, list) or len(evidence_links) > 10 or
                any(not isinstance(link, str) or len(link) > 2048 for link in evidence_links) or
                sum(map(len, evidence_links)) > 4000):
            raise ValueError("invalid_evidence_links")
        if (not isinstance(inference_labels, list) or
                any(not isinstance(label, str) or label not in INFERENCE_LABELS for label in inference_labels)):
            raise ValueError("invalid_inference_labels")
        request = dict(path=path, expected_revision=expected_revision, old_text=old_text,
                       new_text=new_text, origin=origin, date=date,
                       evidence_links=evidence_links, inference_labels=sorted(set(inference_labels)))
        request_digest = sha(json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        existing = self.get(key)
        if existing:
            if existing["RequestDigest"] != request_digest:
                raise ValueError("operation_id_reused")
            return self.resume(existing, replayed=True)
        current = self.notes.read(path)
        if current["revision"] != expected_revision:
            raise ValueError("revision_conflict")
        if update_requires_review(path, current["content"]):
            raise ValueError("review_required")
        if current["content"].count(old_text) != 1:
            raise ValueError("patch_not_unique")
        proposed = current["content"].replace(old_text, new_text, 1)
        if not proposed.strip():
            raise ValueError("empty_note")
        if update_requires_review(path, proposed):
            raise ValueError("review_required")
        for link in evidence_links:
            if not link.startswith(("https://", "http://")):
                normalize_path(link)
                if not permitted(link, read_prefixes):
                    raise ValueError("forbidden")
                self.notes.read(link)
        marker = sha((key["PK"] + "\0" + key["SK"]).encode())
        provenance = {"operation": marker, "origin": origin, "date": date,
                      "evidence_links": evidence_links, "inference_labels": request["inference_labels"]}
        encoded = json.dumps(provenance, ensure_ascii=False, separators=(",", ":")).replace("--", "\\u002d\\u002d")
        newline = "\r\n" if "\r\n" in current["content"] else "\n"
        proposed += newline + "<!-- kb-update " + encoded + " -->" + newline
        if current["raw"].startswith(b"\xef\xbb\xbf"):
            proposed = "\ufeff" + proposed
        raw = proposed.encode("utf-8")
        if len(raw) > MAX_NOTE_BYTES:
            raise ValueError("note_too_large")
        item = {**key, "OperationId": operation_id, "Path": path, "RequestDigest": request_digest,
                "ExpectedRevision": expected_revision, "BaseETag": current["etag"],
                "Marker": marker, "ProposedContent": proposed, "ContentSha256": sha(raw),
                "Metadata": current["metadata"], "ContentType": current["content_type"],
                "State": "writing", "Persistence": "pending", "CreatedAt": int(time.time())}
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise RuntimeError("write_state_unavailable") from None
            item = self.get(key)
            if not item or item.get("RequestDigest") != request_digest:
                raise ValueError("operation_id_reused") from None
            return self.resume(item, replayed=True)
        return self.resume(item, replayed=False, first_attempt=True)

    def matches(self, item, note):
        return (note and note["sha256"] == item["ContentSha256"] and
                '"operation":"' + item["Marker"] + '"' in note["content"])

    def current(self, item):
        try:
            return self.notes.read(item["Path"])
        except ValueError as error:
            if str(error) != "not_found":
                raise
            return None

    def recover(self, item, current):
        if self.matches(item, current):
            return current
        # Only inspect the exact granted object's versions. Bound work so a
        # pathological history cannot exhaust the Lambda request deadline.
        versions = self.notes.client.list_object_versions(Bucket=self.notes.bucket,
                                                          Prefix="notes/" + item["Path"], MaxKeys=32)
        candidates = [row for row in versions.get("Versions", []) if row["Key"] == "notes/" + item["Path"]]
        for version in candidates:
            if version["VersionId"] in {item["ExpectedRevision"], current["revision"] if current else None}:
                continue
            note = self.notes.read(item["Path"], version=version["VersionId"])
            if self.matches(item, note):
                return note
        if versions.get("IsTruncated"):
            raise RuntimeError("recovery_pending")
        return None

    def complete(self, item, note, replayed):
        receipt = {**item, "State": "persisted", "Persistence": "persisted", "Revision": note["revision"]}
        try:
            self.table.update_item(
                Key={"PK": item["PK"], "SK": item["SK"]},
                UpdateExpression="SET #s=:state, Persistence=:state, Revision=:revision, UpdatedAt=:now REMOVE ProposedContent",
                ExpressionAttributeNames={"#s": "State"},
                ConditionExpression="RequestDigest=:request",
                ExpressionAttributeValues={":state": "persisted", ":revision": note["revision"],
                                           ":now": int(time.time()), ":request": item["RequestDigest"]},
            )
        except (ClientError, BotoCoreError):
            return self.receipt(receipt, replayed, recorded=False)
        return self.receipt(receipt, replayed)

    def resume(self, item, replayed, first_attempt=False):
        if item.get("Persistence") == "persisted":
            return self.receipt(item, replayed)
        if item.get("State") == "conflict":
            raise ValueError("revision_conflict")
        current = self.current(item)
        if not first_attempt:
            recovered = self.recover(item, current)
            if recovered:
                return self.complete(item, recovered, replayed)
        if not current or current["revision"] != item["ExpectedRevision"] or current["etag"] != item["BaseETag"]:
            raise ValueError("revision_conflict")
        if update_requires_review(item["Path"], current["content"]):
            raise ValueError("review_required")
        try:
            result = self.notes.client.put_object(
                Bucket=self.notes.bucket, Key="notes/" + item["Path"],
                Body=item["ProposedContent"].encode("utf-8"), IfMatch=item["BaseETag"],
                ContentType=item["ContentType"], ServerSideEncryption="AES256",
                Metadata=item["Metadata"])
        except (ClientError, BotoCoreError) as error:
            latest = self.current(item)
            recovered = self.recover(item, latest)
            if recovered:
                return self.complete(item, recovered, replayed)
            code = error.response.get("Error", {}).get("Code", "") if isinstance(error, ClientError) else ""
            if code in {"PreconditionFailed", "412", "ConditionalRequestConflict", "409"}:
                raise ValueError("revision_conflict") from None
            raise RuntimeError("write_outcome_unknown; retry the same operation_id") from None
        revision = result.get("VersionId") or result.get("ETag")
        if not revision:
            raise RuntimeError("write_outcome_unknown; retry the same operation_id")
        return self.complete(item, {"revision": revision}, replayed)

    def status(self, *, principal, client_id, operation_id, allowed_prefixes, read_prefixes):
        item = self.get(self.key(principal, client_id, operation_id))
        if not item:
            raise ValueError("not_found")
        if not permitted(item["Path"], allowed_prefixes) or not permitted(item["Path"], read_prefixes):
            raise ValueError("forbidden")
        if item.get("Persistence") != "persisted":
            recovered = self.recover(item, self.current(item))
            if recovered:
                return self.receipt({**item, "Persistence": "persisted", "State": "persisted",
                                     "Revision": recovered["revision"]}, True, recorded=False)
        return self.receipt(item, False)

    def receipt(self, item, replayed, recorded=True):
        indexing = "pending" if item.get("Persistence") == "persisted" else "not_queued"
        if indexing == "pending" and self.indexed_sha256:
            try:
                found = self.indexed_sha256(item["Path"])
                if found == item["ContentSha256"]:
                    indexing = "indexed"
                else:
                    current = self.current(item)
                    indexing = "pending" if current and current["sha256"] == item["ContentSha256"] else "superseded"
            except (ValueError, RuntimeError, ClientError, BotoCoreError):
                indexing = "not_checked"
        return {"operation_id": item["OperationId"], "operation_type": "update", "path": item["Path"],
                "revision": item.get("Revision"), "sha256": item["ContentSha256"],
                "expected_revision": item["ExpectedRevision"], "state": item.get("State", "writing"),
                "persistence": item.get("Persistence", "pending"), "indexing": indexing,
                "review": "not_required", "operation_audit": "recorded" if recorded else "pending_retry",
                "activity_audit": "pending", "activity_audit_reason": "not_enabled", "replayed": replayed}
