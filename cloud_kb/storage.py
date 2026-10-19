"""Bounded S3 reads with source revisions, independent of index freshness."""
import hashlib
from pathlib import PurePosixPath

from botocore.exceptions import ClientError


MAX_NOTE_BYTES = 256 * 1024


def normalize_path(path: str) -> str:
    if not isinstance(path, str) or not path or len(path) > 1024:
        raise ValueError("invalid_path")
    parts = path.split("/")
    if (any(part in {"", ".", ".."} or part.startswith(".") for part in parts) or
            "\\" in path or any(ord(char) < 32 for char in path) or
            PurePosixPath(path).suffix.lower() != ".md"):
        raise ValueError("invalid_path")
    return path


def permitted(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix or path.startswith(prefix.rstrip("/") + "/")
               for prefix in prefixes if prefix)


class S3Notes:
    def __init__(self, client, bucket: str):
        self.client = client
        self.bucket = bucket

    def fetch(self, path: str, max_chars: int = 10_000) -> dict:
        path = normalize_path(path)
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or not 1 <= max_chars <= 20_000:
            raise ValueError("invalid_max_chars")
        try:
            response = self.client.get_object(Bucket=self.bucket, Key="notes/" + path)
        except ClientError as error:
            if error.response["Error"]["Code"] in {"NoSuchKey", "NoSuchVersion", "404"}:
                raise ValueError("not_found") from None
            raise RuntimeError("storage_unavailable") from None
        body = response["Body"]
        try:
            if response.get("ContentLength", 0) > MAX_NOTE_BYTES:
                raise ValueError("note_too_large")
            raw = body.read(MAX_NOTE_BYTES + 1)
        finally:
            body.close()
        if len(raw) > MAX_NOTE_BYTES:
            raise ValueError("note_too_large")
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeError:
            raise ValueError("invalid_markdown_encoding") from None
        # Content digest is independent of opaque S3 ETags and storage VersionIds.
        return {
            "path": path, "content": content[:max_chars],
            "revision": response.get("VersionId") or response["ETag"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "tier": "canonical" if path.startswith("Wiki/") else "source",
            "truncated": len(content) > max_chars,
            "persistence": "persisted", "indexing": "not_checked",
        }
