"""Bounded S3 reads with source revisions, independent of index freshness."""
import hashlib
from pathlib import PurePosixPath
import re

import yaml

from botocore.exceptions import ClientError


MAX_NOTE_BYTES = 256 * 1024
CAPTURE_ROOTS = ("Ideas/", "Resources/_Review/AI Learning/")
UPDATE_ROOTS = ("Ideas/", "Projects/", "Areas/", "Resources/", "Personal Facts/", "Templates/")


def validate_update_prefix(prefix):
    if not isinstance(prefix, str) or not prefix.endswith("/") or not prefix.startswith(UPDATE_ROOTS):
        raise ValueError("invalid_update_destination")
    normalize_path(prefix + "scope.md")
    return prefix


def update_requires_review(path, content):
    """Source snapshots, policies and canonical/verified knowledge stay protected."""
    parts = {part.casefold() for part in path.split("/")}
    if parts & {"wiki", "archive", "archives", "source archives", "source snapshots", "clippings", "agents.md"}:
        return True
    normalized = content.replace("\r\n", "\n")
    if normalized.startswith("---\n") and normalized.count("---") < 2:
        return True
    frontmatter = normalized.split("---", 2)[1] if normalized.startswith("---\n") and normalized.count("---") >= 2 else ""
    if len(frontmatter.encode()) > 16_384:
        return True
    try:
        node = yaml.compose(frontmatter, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return True
    if node is None:
        return False
    if not isinstance(node, yaml.MappingNode) or node.tag != "tag:yaml.org,2002:map":
        return True
    # Inspect pairs, including duplicate keys, without constructing arbitrary
    # YAML objects or recursively walking aliases. Quotes/folded scalars cannot
    # hide a protected authority marker.
    for key, value in node.value:
        if not isinstance(key, yaml.ScalarNode):
            return True
        name = key.value.casefold()
        if name not in {"status", "authority", "type"}:
            continue
        if not isinstance(value, yaml.ScalarNode):
            return True
        if value.tag in {"tag:yaml.org,2002:null", "tag:yaml.org,2002:bool", "tag:yaml.org,2002:int", "tag:yaml.org,2002:float"}:
            continue
        if value.tag != "tag:yaml.org,2002:str":
            return True
        value = value.value.strip().casefold()
        if name in {"status", "authority"} and value in {"canonical", "binding", "verified", "confirmed"}:
            return True
        if name == "type" and value in {"source", "source-snapshot", "raw-source", "web-clip", "book-excerpt"}:
            return True
    return False


def validate_capture_prefix(prefix: str) -> str:
    """Accept only the supported raw-capture trees; grants must narrow them."""
    if (not isinstance(prefix, str) or not prefix.endswith("/") or
            not prefix.startswith(CAPTURE_ROOTS)):
        raise ValueError("invalid_capture_destination")
    normalize_path(prefix + "scope.md")
    return prefix


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
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or not 1 <= max_chars <= 20_000:
            raise ValueError("invalid_max_chars")
        note = self.read(path)
        result = {key: note[key] for key in ("path", "revision", "sha256", "tier", "persistence", "indexing")}
        result.update(content=note["content"][:max_chars], truncated=len(note["content"]) > max_chars)
        return result

    def read(self, path, version=None):
        """Full bounded internal read; fetch never returns private write metadata."""
        path = normalize_path(path)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key="notes/" + path,
                                              **({"VersionId": version} if version else {}))
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
            "path": path, "content": content, "raw": raw,
            "revision": response.get("VersionId") or response["ETag"],
            "etag": response["ETag"], "metadata": response.get("Metadata", {}),
            "content_type": response.get("ContentType", "text/markdown; charset=utf-8"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "tier": authority(path, content),
            "truncated": False,
            "persistence": "persisted", "indexing": "not_checked",
        }
