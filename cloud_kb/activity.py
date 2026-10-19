"""Conditional, idempotent appends to the existing vault activity log.

This backend component needs separate owner authorisation and exact-path IAM
permission. It is not an MCP tool and cannot be enabled by note content.
"""
from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import quote

from botocore.exceptions import BotoCoreError, ClientError

from cloud_kb.storage import MAX_NOTE_BYTES, normalize_path


ACTIVITY_PATH = "Wiki/Activity Log.md"
AUDIT_CONTRACT = "capture-activity-append-v1"


class ActivityLog:
    def __init__(self, s3, bucket):
        self.s3, self.bucket = s3, bucket

    def append(self, operation):
        if operation.get("Persistence") != "persisted":
            raise ValueError("activity_requires_persisted_capture")
        path = normalize_path(operation["Path"])
        digest = operation["ContentSha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid_activity_operation")
        reference = hashlib.sha256((operation["PK"] + "\0" + operation["SK"]).encode()).hexdigest()
        timestamp = datetime.fromtimestamp(int(operation["CreatedAt"]), timezone.utc).isoformat()
        marker = ("<!-- kb-capture-audit:" + reference + " -->").encode()
        block = marker + ("\n- " + timestamp + ": Captured unverified learning " +
                          "[note](../" + quote(path, safe="/") + ") " +
                          "(SHA-256 `" + digest + "`).\n").encode("utf-8")
        key = "notes/" + ACTIVITY_PATH
        for _ in range(3):
            try:
                raw, response = self._read()
                etag = response.get("ETag")
                if not isinstance(etag, str) or not etag:
                    raise RuntimeError("activity_log_unavailable")
                if marker in raw:
                    if block not in raw:
                        raise ValueError("activity_log_entry_conflict")
                    return self._receipt(raw, response)
                separator = b"\n" if raw.endswith(b"\n") else b"\n\n" if raw else b""
                updated = raw + separator + block
                if len(updated) > MAX_NOTE_BYTES:
                    raise ValueError("activity_log_too_large")
                saved = self.s3.put_object(
                    Bucket=self.bucket, Key=key, Body=updated, IfMatch=etag,
                    ContentType=response.get("ContentType", "text/markdown; charset=utf-8"),
                    Metadata=response.get("Metadata", {}), ServerSideEncryption="AES256",
                )
                verified, _response = self._read(version=saved.get("VersionId"))
                if verified != updated:
                    raise RuntimeError("activity_log_verification_failed")
                return self._receipt(updated, saved)
            except ClientError as error:
                code = error.response.get("Error", {}).get("Code", "")
                if code in {"PreconditionFailed", "412", "ConditionalRequestConflict", "409"}:
                    continue
                if code in {"NoSuchKey", "NoSuchVersion", "404"}:
                    raise RuntimeError("activity_log_missing") from None
                raise RuntimeError("activity_log_unavailable") from None
            except BotoCoreError:
                raise RuntimeError("activity_log_unavailable") from None
        raise RuntimeError("activity_log_busy")

    def _read(self, version=None):
        request = {"Bucket": self.bucket, "Key": "notes/" + ACTIVITY_PATH}
        if version:
            request["VersionId"] = version
        response = self.s3.get_object(**request)
        body = response["Body"]
        try:
            raw = body.read(MAX_NOTE_BYTES + 1)
        finally:
            body.close()
        if len(raw) > MAX_NOTE_BYTES:
            raise ValueError("activity_log_too_large")
        try:
            raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("activity_log_invalid_utf8") from None
        return raw, response

    @staticmethod
    def _receipt(raw, response):
        revision = response.get("VersionId") or response.get("ETag")
        if not isinstance(revision, str) or not revision:
            raise RuntimeError("activity_log_unavailable")
        return {"revision": revision, "sha256": hashlib.sha256(raw).hexdigest(),
                "contract": AUDIT_CONTRACT}
