#!/usr/bin/env python3
"""Synthetic bilingual retrieval gate using the production Bedrock adapter and search code.

Only repository synthetic fixture text is sent to the model. The private KB is
never loaded by this gate or printed in CI logs.
"""
import argparse
from contextlib import closing
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cloud_kb.embeddings import BedrockEmbeddings, CONTRACT as EMBEDDING_CONTRACT, pack
from cloud_kb.ingestion import chunks
from cloud_kb.search import HYBRID_CONTRACT, SnapshotSearch
from cloud_kb.storage import authority
from tools.aws_session import session_from_file

FIXTURE = ROOT / "tests/fixtures/cloud-kb/hybrid-benchmark.json"


class SyntheticS3:
    def __init__(self, raw):
        self.raw = raw

    def get_object(self, **_):
        return {"Body": BytesIO(self.raw), "ContentLength": len(self.raw)}


class SyntheticTable:
    def __init__(self, descriptor):
        self.descriptor = descriptor

    def get_item(self, **_):
        return {"Item": self.descriptor}


class SyntheticNotes:
    def __init__(self, notes):
        self.notes = notes

    def fetch(self, path, max_chars=20000):
        content = self.notes[path]
        return {"path": path, "content": content[:max_chars], "revision": "synthetic-v1",
                "tier": authority(path, content), "sha256": hashlib.sha256(content.encode()).hexdigest()}


def benchmark(embeddings, fixture):
    notes = {item["path"]: item["text"] for item in fixture["notes"]}
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE notes(path TEXT PRIMARY KEY,tier TEXT,sha256 TEXT,source_revision TEXT)")
        db.execute("CREATE TABLE chunks(path TEXT,ordinal INTEGER,text TEXT,vector BLOB,PRIMARY KEY(path,ordinal))")
        db.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)")
        db.execute("INSERT INTO metadata VALUES('embedding_contract',?)", (EMBEDDING_CONTRACT,))
        for path in notes:
            text = notes[path]
            db.execute("INSERT INTO notes VALUES(?,?,?,?)", (path, authority(path, text), hashlib.sha256(text.encode()).hexdigest(), "synthetic-v1"))
            parts = chunks(text)
            vectors = embeddings.documents(parts)
            db.executemany("INSERT INTO chunks VALUES(?,?,?,?)",
                           [(path, ordinal, part, pack(vector)) for ordinal, (part, vector) in enumerate(zip(parts, vectors))])
        db.commit()
        raw = db.serialize()
    digest = hashlib.sha256(raw).hexdigest()
    descriptor = {"Contract": HYBRID_CONTRACT, "EmbeddingContract": EMBEDDING_CONTRACT,
                  "Key": "indexes/synthetic/index.sqlite", "Sha256": digest, "SnapshotId": digest}
    search = SnapshotSearch(SyntheticS3(raw), "synthetic-index", SyntheticTable(descriptor), SyntheticNotes(notes), embeddings)
    results = {}
    for strategy in ("lexical", "vector", "hybrid"):
        ranked = [search.search(case["query"], ["Projects/", "Areas/", "Resources/", "Ideas/"],
                                limit=5, strategy=strategy)["results"] for case in fixture["cases"]]
        total = len(ranked)
        top1 = sum(bool(rows and rows[0]["path"] == case["expected"])
                   for rows, case in zip(ranked, fixture["cases"]))
        top3 = sum(case["expected"] in [row["path"] for row in rows[:3]]
                   for rows, case in zip(ranked, fixture["cases"]))
        cross = [i for i, case in enumerate(fixture["cases"]) if case.get("cross_language")]
        cross_top3 = sum(fixture["cases"][i]["expected"] in [row["path"] for row in ranked[i][:3]] for i in cross)
        results[strategy] = {"top1": top1, "top3": top3, "total": total,
                             "cross_language_top3": cross_top3, "cross_language_total": len(cross)}
    return results


def quality_gate(results):
    lexical, hybrid = results["lexical"], results["hybrid"]
    # The floor is deliberately bounded to this versioned synthetic fixture.
    # It catches missing/wrong embedding modes, vector corruption and rank drift.
    return (hybrid["top1"] >= 10 and hybrid["top3"] >= 13 and
            hybrid["cross_language_top3"] == hybrid["cross_language_total"] and
            hybrid["top1"] >= lexical["top1"] - 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Ignored local AWS credential file; omit inside trusted CodeBuild")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text())
    session = session_from_file(args.env_file)
    result = benchmark(BedrockEmbeddings(session.client("bedrock-runtime")), fixture)
    stress_parts = chunks("跨语言知识检索与向量索引。" * 150)
    if len(stress_parts) < 2 or len(BedrockEmbeddings(session.client("bedrock-runtime")).documents(stress_parts)) != len(stress_parts):
        raise SystemExit("Long synthetic Chinese document did not embed completely")
    passed = quality_gate(result)
    print(json.dumps({"fixture": fixture["version"], "model": "cohere.embed-multilingual-v3",
                      "region": "ap-southeast-2", "results": result, "gate": "pass" if passed else "fail"}))
    if not passed:
        raise SystemExit("Embedding benchmark below synthetic bilingual quality floor")


if __name__ == "__main__":
    main()
