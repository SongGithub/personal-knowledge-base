"""Idempotent, prefix-bounded raw Markdown captures into approved raw-note trees."""
from datetime import date
import hashlib
import json
import re
import time

from botocore.exceptions import BotoCoreError, ClientError

from cloud_kb.activity import AUDIT_CONTRACT
from cloud_kb.storage import normalize_path, validate_capture_prefix


MAX_TITLE = 200
MAX_MARKDOWN = 12_000
MAX_ORIGIN = 500
MAX_EVIDENCE = 10
MAX_EVIDENCE_URL = 2_048
MAX_EVIDENCE_TOTAL = 4_000
MAX_CAPTURE_BYTES = 24_576
INFERENCE_LABELS = {"owner-stated", "external-source", "calculation", "ai-inference"}


def _text(value, limit, field):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("invalid_" + field)
    return value.strip()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _yaml(value):
    return json.dumps(value, ensure_ascii=False)


def _slug(title):
    slug = re.sub(r"[^\w-]+", "-", title.casefold(), flags=re.UNICODE).strip("-")
    return (slug[:72].rstrip("-") or "learning")


def render_markdown(*, title, markdown, origin, created_date, evidence, inference_labels):
    return (
        "---\nstatus: unverified\ncreated: " + _yaml(created_date) +
        "\norigin: " + _yaml(origin) + "\nsource: ai-mcp-capture\n" +
        "inference_labels: " + _yaml(inference_labels) +
        "\nevidence: " + _yaml(evidence) + "\n---\n\n# " + title + "\n\n" + markdown + "\n"
    ).encode("utf-8")


class LearningWriter:
    """Writes only new, unverified captures under an exact grant-configured prefix."""

    def __init__(self, s3, table, bucket, indexed_sha256=None, activity_log=None):
        self.s3, self.table, self.bucket = s3, table, bucket
        self.indexed_sha256 = indexed_sha256
        self.activity_log = activity_log

    def capture(self, *, principal, client_id, operation_id, destination, title,
                markdown, origin, created_date, evidence, inference_labels,
                allowed_prefixes):
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", operation_id):
            raise ValueError("invalid_operation_id")
        if destination not in allowed_prefixes:
            raise ValueError("forbidden")
        try:
            validate_capture_prefix(destination)
        except ValueError:
            raise ValueError("forbidden") from None
        title = _text(title, MAX_TITLE, "title")
        if any(ord(char) < 32 for char in title):
            raise ValueError("invalid_title")
        markdown = _text(markdown, MAX_MARKDOWN, "markdown")
        if any(ord(char) == 0 or (ord(char) < 32 and char not in "\n\r\t") for char in markdown):
            raise ValueError("invalid_markdown")
        origin = _text(origin, MAX_ORIGIN, "origin")
        try:
            created_date = date.fromisoformat(created_date).isoformat()
        except (TypeError, ValueError):
            raise ValueError("invalid_created_date") from None
        if (not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE or
                any(not isinstance(url, str) or len(url) > MAX_EVIDENCE_URL or
                    not url.startswith(("https://", "http://")) for url in evidence) or
                sum(len(url) for url in evidence if isinstance(url, str)) > MAX_EVIDENCE_TOTAL):
            raise ValueError("invalid_evidence")
        if (not isinstance(inference_labels, list) or
                any(not isinstance(label, str) or label not in INFERENCE_LABELS for label in inference_labels)):
            raise ValueError("invalid_inference_labels")
        inference_labels = sorted(set(inference_labels))
        evidence = list(dict.fromkeys(evidence))

        client_key = _sha((principal + "\0" + client_id).encode())
        operation_key = {"PK": "OP#" + client_key, "SK": "CAPTURE#" + operation_id}
        payload = {"title": title, "markdown": markdown, "origin": origin,
                   "created_date": created_date, "evidence": evidence,
                   "inference_labels": inference_labels, "destination": destination}
        request_digest = _sha(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode())
        path = normalize_path(destination + created_date[:4] + "/" + created_date[5:7] + "/" +
                              created_date[8:10] + "-" + _slug(title) + "-" + request_digest[:12] + ".md")
        content = render_markdown(title=title, markdown=markdown, origin=origin,
                                  created_date=created_date, evidence=evidence,
                                  inference_labels=inference_labels)
        if len(content) > MAX_CAPTURE_BYTES:
            raise ValueError("capture_too_large")
        content_digest = _sha(content)
        item = {**operation_key, "OperationId": operation_id, "RequestDigest": request_digest,
                "Path": path, "ContentSha256": content_digest, "Destination": destination,
                "State": "writing", "Persistence": "pending", "Review": "not_required",
                "Indexing": "pending", "ActivityAudit": "pending", "CreatedAt": int(time.time())}
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
            existing = item
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"ConditionalCheckFailedException", "ConditionalCheckFailed"}:
                raise RuntimeError("write_state_unavailable") from None
            existing = self.table.get_item(Key=operation_key, ConsistentRead=True).get("Item", {})
            if not existing:
                raise RuntimeError("write_state_unavailable") from None
            if existing.get("RequestDigest") != request_digest:
                raise ValueError("operation_id_reused") from None
            if existing.get("Persistence") == "persisted":
                return self._finish_capture(existing, replayed=True)

        key = "notes/" + path
        try:
            response = self.s3.put_object(Bucket=self.bucket, Key=key, Body=content,
                                          ContentType="text/markdown; charset=utf-8",
                                          ServerSideEncryption="AES256", IfNoneMatch="*")
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code not in {"PreconditionFailed", "412", "ConditionalRequestConflict"}:
                self._mark_retryable(operation_key)
                raise RuntimeError("storage_unavailable") from None
            current = self._read_existing(key)
            if current is None:
                # S3 may briefly return 409 while another conditional write is
                # resolving. Keep the operation retryable and let the caller
                # retry with the same idempotency key.
                self._mark_retryable(operation_key)
                raise RuntimeError("write_in_progress") from None
            if _sha(current[0]) != content_digest:
                raise ValueError("operation_id_reused") from None
            response = current[1]
        revision = response.get("VersionId") or response.get("ETag", "").strip('"')
        if not revision:
            self._mark_retryable(operation_key)
            raise RuntimeError("storage_unavailable")
        self.table.update_item(
            Key=operation_key,
            UpdateExpression="SET #state=:persisted, Persistence=:persisted, Revision=:revision, "
                             "ContentSha256=:digest, UpdatedAt=:now",
            ExpressionAttributeNames={"#state": "State"},
            ExpressionAttributeValues={":persisted": "persisted", ":revision": revision,
                                       ":digest": content_digest, ":now": int(time.time())},
        )
        return self._finish_capture({**existing, "Persistence": "persisted", "State": "persisted",
                                     "Revision": revision}, replayed=False)

    def _finish_capture(self, item, replayed):
        if self.activity_log is not None and not self._activity_recorded(item):
            try:
                audit = self.activity_log.append(item)
            except (ValueError, RuntimeError, BotoCoreError) as error:
                receipt = self._receipt(item, replayed)
                receipt["activity_audit_error"] = (str(error) if isinstance(error, (ValueError, RuntimeError))
                                                    else "activity_log_unavailable")
                return receipt
            try:
                self.table.update_item(
                    Key={"PK": item["PK"], "SK": item["SK"]},
                    UpdateExpression="SET ActivityAudit=:recorded, ActivityAuditContract=:contract, "
                                     "ActivityLogRevision=:audit_revision, ActivityLogSha256=:sha, UpdatedAt=:now",
                    ConditionExpression="Persistence=:persisted AND ContentSha256=:digest",
                    ExpressionAttributeValues={":recorded": "recorded", ":contract": audit["contract"],
                                               ":audit_revision": audit["revision"], ":sha": audit["sha256"],
                                               ":now": int(time.time()), ":persisted": "persisted",
                                               ":digest": item["ContentSha256"]},
                )
            except (ClientError, BotoCoreError):
                receipt = self._receipt(item, replayed)
                receipt["activity_audit_error"] = "activity_state_unavailable"
                return receipt
            item = {**item, "ActivityAudit": "recorded", "ActivityAuditContract": audit["contract"],
                    "ActivityLogRevision": audit["revision"], "ActivityLogSha256": audit["sha256"]}
        return self._receipt(item, replayed)

    def status(self, *, principal, client_id, operation_id, check_index=True):
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", operation_id):
            raise ValueError("invalid_operation_id")
        key = {"PK": "OP#" + _sha((principal + "\0" + client_id).encode()),
               "SK": "CAPTURE#" + operation_id}
        item = self.table.get_item(Key=key, ConsistentRead=True).get("Item")
        if not item:
            raise ValueError("not_found")
        receipt = self._receipt(item, replayed=False)
        if check_index and item.get("Persistence") == "persisted" and self.indexed_sha256 is not None:
            try:
                digest = self.indexed_sha256(item["Path"])
                receipt["indexing"] = ("indexed" if digest == item["ContentSha256"] else
                                       "superseded" if digest is not None else "pending")
            except (ValueError, RuntimeError, ClientError, BotoCoreError):
                # Index trouble must not hide a durable Markdown receipt.
                receipt["indexing"] = "not_checked"
        return receipt

    def _read_existing(self, key):
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "NoSuchVersion", "404"}:
                return None
            raise RuntimeError("storage_unavailable") from None
        body = response["Body"]
        try:
            raw = body.read(MAX_CAPTURE_BYTES + 1)
        finally:
            body.close()
        if len(raw) > MAX_CAPTURE_BYTES:
            raise ValueError("capture_too_large")
        return raw, response

    def _mark_retryable(self, key):
        self.table.update_item(Key=key, UpdateExpression="SET Persistence=:retryable, UpdatedAt=:now",
                               ExpressionAttributeValues={":retryable": "retryable", ":now": int(time.time())})

    @staticmethod
    def _activity_recorded(item):
        # Legacy records used 'recorded' for the DynamoDB row alone.
        return (item.get("ActivityAudit") == "recorded" and
                item.get("ActivityAuditContract") == AUDIT_CONTRACT and
                bool(item.get("ActivityLogRevision")))

    def _receipt(self, item, replayed):
        audited = self._activity_recorded(item)
        receipt = {"operation_id": item["OperationId"], "state": item.get("State", "writing"),
                   "path": item["Path"], "revision": item.get("Revision"),
                   "sha256": item["ContentSha256"], "persistence": item.get("Persistence", "pending"),
                   "review": item.get("Review", "pending_review"),
                   "indexing": item.get("Indexing", "pending"),
                   "activity_audit": "recorded" if audited else "pending",
                   "operation_audit": "recorded", "replayed": replayed}
        if audited:
            receipt["activity_log_revision"] = item["ActivityLogRevision"]
        else:
            receipt["activity_audit_reason"] = "pending_retry" if self.activity_log is not None else "not_enabled"
        return receipt
