"""Bounded S3 reads with source revisions, independent of index freshness."""
import hashlib
from pathlib import PurePosixPath
import re

from botocore.exceptions import ClientError


MAX_NOTE_BYTES = 256 * 1024


def authority(path: str, text: str) -> str:
    frontmatter = text.split("---", 2)[1].lower() if text.startswith("---\n") and text.count("---") >= 2 else ""
    if "_review/" in path.lower() or re.search(r"^status:\s*(draft|unverified|working-model|待核对)", frontmatter, re.M):
        return "unverified"
    if path.endswith("/AGENTS.md") or path == "AGENTS.md" or re.search(r"^(status|authority):\s*(canonical|binding)", frontmatter, re.M):
        return "canonical"
    if set(path.lower().split("/")) & {"archive", "archives", "source archives", "source snapshots"}:
        return "archive"
    if re.search(r"^status:\s*(verified|confirmed)", frontmatter, re.M):
        return "verified"
    return "ordinary"


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
            "tier": authority(path, content),
            "truncated": len(content) > max_chars,
            "persistence": "persisted", "indexing": "not_checked",
        }
