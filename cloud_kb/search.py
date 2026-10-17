"""A lexical first slice over an immutable SQLite snapshot; no fake embeddings."""
from contextlib import closing
import hashlib
import re
import sqlite3

from cloud_kb.storage import normalize_path, permitted


CONTRACT = "lexical-sqlite-v1"
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


class SnapshotSearch:
    def __init__(self, s3, index_bucket: str, table, notes):
        self.s3, self.index_bucket, self.table, self.notes = s3, index_bucket, table, notes
        self._cached = None

    def _snapshot(self):
        descriptor = self.table.get_item(
            Key={"PK": "INDEX#ACTIVE", "SK": "SNAPSHOT"}, ConsistentRead=True,
        ).get("Item", {})
        key, digest = descriptor.get("Key", ""), descriptor.get("Sha256", "")
        if (descriptor.get("Contract") != CONTRACT or not key.startswith("indexes/") or
                not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("index_unavailable")
        if self._cached and self._cached[0] == digest:
            return descriptor, self._cached[1]
        response = self.s3.get_object(Bucket=self.index_bucket, Key=key)
        body = response["Body"]
        try:
            if response.get("ContentLength", 0) > MAX_SNAPSHOT_BYTES:
                raise ValueError("index_too_large")
            data = body.read(MAX_SNAPSHOT_BYTES + 1)
        finally:
            body.close()
        if len(data) > MAX_SNAPSHOT_BYTES or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("index_integrity_failure")
        self._cached = digest, data
        return descriptor, data

    def search(self, query: str, prefixes: list[str], limit: int = 5, strategy: str = "lexical"):
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ValueError("invalid_query")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("invalid_limit")
        if strategy != "lexical":
            raise ValueError("embedding_provider_not_configured")
        descriptor, data = self._snapshot()
        terms = set(re.findall(r"[\w]+", query.casefold()))
        if not terms:
            raise ValueError("invalid_query")
        try:
            with closing(sqlite3.connect(":memory:")) as db:
                db.deserialize(data)
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ValueError("index_integrity_failure")
                rows = db.execute("SELECT path,sha256,content FROM notes LIMIT 1001").fetchall()
        except sqlite3.Error:
            raise ValueError("index_unavailable") from None
        if len(rows) > 1000:
            raise ValueError("index_too_large")
        ranked = []
        for path, source_digest, content in rows:
            if not permitted(normalize_path(path), prefixes):
                continue
            score = sum(content.casefold().count(term) for term in terms)
            if score:
                ranked.append((score, path, source_digest))
        results = []
        for _, path, indexed_digest in sorted(ranked, key=lambda row: (-row[0], row[1])):
            try:
                current = self.notes.fetch(path, max_chars=20_000)
            except ValueError as error:
                if str(error) == "not_found":
                    continue
                raise
            # Never disclose stale cached text. Recheck current contents/existence.
            if not any(term in current["content"].casefold() for term in terms):
                continue
            text = current["content"]
            positions = [text.casefold().find(term) for term in terms if term in text.casefold()]
            start = max(0, min(positions, default=0) - 160)
            results.append({
                "path": path, "tier": current["tier"], "excerpt": text[start:start + 1200],
                "revision": current["revision"], "indexed_sha256": indexed_digest,
                "current_sha256": current["sha256"],
                "freshness": "current" if indexed_digest == current["sha256"] else "changed_since_index",
            })
            if len(results) == limit:
                break
        return {"strategy": strategy, "contract": CONTRACT,
                "snapshot_id": descriptor.get("SnapshotId"), "results": results}
