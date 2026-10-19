"""Immutable cloud snapshots: legacy lexical proof and versioned hybrid search."""
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import math
from pathlib import PurePosixPath
import re
import sqlite3

from cloud_kb.embeddings import CONTRACT as EMBEDDING_CONTRACT, unpack
from cloud_kb.storage import normalize_path, permitted


CONTRACT = "lexical-sqlite-v1"
HYBRID_CONTRACT = "hybrid-sqlite-v1"
DEFAULT_STRATEGY = "hybrid"
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
STOP = set("a an and are as at be did do for from how i in is it my of on or the to was were what when why with 的 了 吗 我 是 在 有 和".split())
AUTHORITY = {"canonical": 0, "verified": 1, "ordinary": 2, "archive": 3, "unverified": 4}


def tokens(text):
    words = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.lower())
    result = []
    for word in words:
        if re.fullmatch(r"[\u3400-\u9fff]+", word):
            result.extend(word[i:i + 2] for i in range(len(word) - 1))
            if len(word) == 1:
                result.append(word)
        elif word not in STOP:
            result.append(word)
    return result


def rank_hybrid(lexical, vector, tiers):
    scores = defaultdict(float)
    for ranking, weight in ((lexical[:30], .25), (vector[:30], .75)):
        for rank, path in enumerate(ranking, 1):
            scores[path] += weight / (60 + rank)
    fused = sorted(scores, key=lambda path: (-scores[path], path))
    if not fused:
        return []
    cutoff = scores[fused[0]] * .98
    near = [path for path in fused if scores[path] >= cutoff]
    rest = [path for path in fused if scores[path] < cutoff]
    near.sort(key=lambda path: (AUTHORITY[tiers[path]], -scores[path], path))
    fused = near + rest
    # A cross-language query can have misleading lexical hits. Preserve the
    # strongest semantic candidate in the first three without overriding rank 1.
    if vector and vector[0] in fused and fused.index(vector[0]) >= 3:
        fused.remove(vector[0])
        fused.insert(2, vector[0])
    return fused


class SnapshotSearch:
    def __init__(self, s3, index_bucket: str, table, notes, embeddings=None):
        self.s3, self.index_bucket, self.table, self.notes = s3, index_bucket, table, notes
        self.embeddings = embeddings
        self._cached = None

    def _snapshot(self):
        descriptor = self.table.get_item(
            Key={"PK": "INDEX#ACTIVE", "SK": "SNAPSHOT"}, ConsistentRead=True,
        ).get("Item", {})
        key, digest = descriptor.get("Key", ""), descriptor.get("Sha256", "")
        if (descriptor.get("Contract") not in {CONTRACT, HYBRID_CONTRACT} or not key.startswith("indexes/") or
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

    def search(self, query: str, prefixes: list[str], limit: int = 5, strategy: str = DEFAULT_STRATEGY):
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ValueError("invalid_query")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("invalid_limit")
        if strategy not in {"lexical", "vector", "hybrid"}:
            raise ValueError("invalid_strategy")
        descriptor, data = self._snapshot()
        if descriptor["Contract"] == CONTRACT:
            if strategy != "lexical":
                raise ValueError("embedding_provider_not_configured")
            return self._legacy(query, prefixes, limit, descriptor, data)
        if descriptor.get("EmbeddingContract") != EMBEDDING_CONTRACT:
            raise ValueError("incompatible_embedding_contract")
        if strategy != "lexical" and self.embeddings is None:
            raise ValueError("embedding_provider_not_configured")
        return self._hybrid(query, prefixes, limit, strategy, descriptor, data)

    def _legacy(self, query, prefixes, limit, descriptor, data):
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
        return {"strategy": "lexical", "contract": CONTRACT,
                "snapshot_id": descriptor.get("SnapshotId"), "results": results}

    def _hybrid(self, query, prefixes, limit, strategy, descriptor, data):
        try:
            with closing(sqlite3.connect(":memory:")) as db:
                db.deserialize(data)
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ValueError("index_integrity_failure")
                meta = dict(db.execute("SELECT key,value FROM metadata"))
                if meta.get("embedding_contract") != EMBEDDING_CONTRACT:
                    raise ValueError("incompatible_embedding_contract")
                rows = db.execute("SELECT c.path,c.ordinal,c.text,c.vector,n.tier,n.sha256 "
                                  "FROM chunks c JOIN notes n USING(path) ORDER BY c.path,c.ordinal LIMIT 20001").fetchall()
        except sqlite3.Error:
            raise ValueError("index_unavailable") from None
        if len(rows) > 20000 or any(row[3] is None for row in rows):
            raise ValueError("index_unavailable")
        for row in rows:
            normalize_path(row[0])
        tiers = {row[0]: row[4] for row in rows}
        digests = {row[0]: row[5] for row in rows}
        lexical = []
        if strategy != "vector":
            query_terms = Counter(tokens(query))
            if not query_terms:
                raise ValueError("invalid_query")
            term_counts = [Counter(tokens(row[2] + " " + PurePosixPath(row[0]).stem * 2)) for row in rows]
            lengths = [sum(counts.values()) for counts in term_counts]
            mean_length = sum(lengths) / len(lengths) if lengths else 1
            df = Counter(term for counts in term_counts for term in counts)
            scores = defaultdict(float)
            for row, counts, length in zip(rows, term_counts, lengths):
                score = 0.0
                for term, query_frequency in query_terms.items():
                    frequency = counts.get(term, 0)
                    if frequency:
                        idf = math.log(1 + (len(rows) - df[term] + .5) / (df[term] + .5))
                        score += query_frequency * idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / mean_length))
                scores[row[0]] = max(scores[row[0]], score)
            lexical = [path for path, score in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0])) if score > 0]
        vector = []
        similarities = {}
        if strategy != "lexical":
            q = self.embeddings.query(query)
            for path, ordinal, _part, blob, _tier, _digest in rows:
                values = unpack(blob)
                score = sum(a * b for a, b in zip(q, values))
                if path not in similarities or score > similarities[path][0]:
                    similarities[path] = (score, ordinal)
            vector = [path for path, _ in sorted(similarities.items(), key=lambda pair: (-pair[1][0], pair[0]))]
        ranking = lexical if strategy == "lexical" else vector if strategy == "vector" else rank_hybrid(lexical, vector, tiers)
        results = []
        for path in ranking:
            if not permitted(path, prefixes):
                continue
            try:
                current = self.notes.fetch(path, max_chars=20_000)
            except ValueError as error:
                if str(error) == "not_found":
                    continue
                raise
            if current["sha256"] != digests[path]:
                # A changed source must be re-indexed before indexed snippets can be shown.
                continue
            candidates = [(ordinal, part) for p, ordinal, part, *_ in rows if p == path]
            if strategy != "lexical" and path in similarities:
                chosen = next(part for ordinal, part in candidates if ordinal == similarities[path][1])
            else:
                terms = Counter(tokens(query))
                chosen = max(candidates, key=lambda row: (sum(terms[t] * tokens(row[1]).count(t) for t in terms), -row[0]))[1]
            results.append({"path": path, "tier": tiers[path], "excerpt": chosen.strip()[:1200],
                            "revision": current["revision"], "indexed_sha256": digests[path],
                            "current_sha256": current["sha256"], "freshness": "current"})
            if len(results) >= limit:
                break
        return {"strategy": strategy, "contract": HYBRID_CONTRACT,
                "embedding_contract": EMBEDDING_CONTRACT, "snapshot_id": descriptor.get("SnapshotId"),
                "results": results}
