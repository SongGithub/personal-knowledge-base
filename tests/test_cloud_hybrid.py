"""Synthetic embedding, incremental snapshot and ranking checks for PR CI."""
from io import BytesIO
import json
import unittest

from botocore.exceptions import ClientError

from cloud_kb.embeddings import BedrockEmbeddings, DIMENSIONS
from cloud_kb.ingestion import ACTIVE, reconcile
from cloud_kb.search import HYBRID_CONTRACT, SnapshotSearch, rank_hybrid, tokens
from cloud_kb.storage import S3Notes


class FakeS3:
    def __init__(self):
        self.objects = {}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, *, Bucket, Prefix):
        yield {"Contents": [{"Key": key} for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix)]}

    def get_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        raw = self.objects[(Bucket, Key)]
        return {"Body": BytesIO(raw), "ContentLength": len(raw), "VersionId": "synthetic-v1", "ETag": '"synthetic"'}

    def put_object(self, *, Bucket, Key, Body, IfNoneMatch, **_):
        assert IfNoneMatch == "*"
        if (Bucket, Key) in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[(Bucket, Key)] = Body


class FakeTable:
    def __init__(self):
        self.active = None

    def get_item(self, *, Key, ConsistentRead):
        assert Key == ACTIVE and ConsistentRead
        return {"Item": self.active} if self.active else {}

    def put_item(self, *, Item, ConditionExpression, **kwargs):
        if ConditionExpression == "attribute_not_exists(PK)":
            assert self.active is None
        else:
            assert self.active["SnapshotId"] == kwargs["ExpressionAttributeValues"][":previous"]
        self.active = Item


class FakeEmbeddings:
    def __init__(self):
        self.documents_seen = []

    def documents(self, texts):
        self.documents_seen.extend(texts)
        return [self.vector(text) for text in texts]

    def query(self, text):
        return self.vector(text)

    @staticmethod
    def vector(text):
        values = [0.0] * DIMENSIONS
        values[0 if "train" in text.lower() else 1] = 1.0
        return values


class FakeBody:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def close(self):
        pass


class FakeBedrock:
    def invoke_model(self, **request):
        body = json.loads(request["body"])
        assert body["input_type"] in {"search_document", "search_query"}
        vector = [0.0] * DIMENSIONS
        vector[0] = 3.0
        return {"body": FakeBody({"embeddings": [vector for _ in body["texts"]]})}


class HybridTests(unittest.TestCase):
    def test_bedrock_contract_and_chinese_tokens(self):
        adapter = BedrockEmbeddings(FakeBedrock())
        self.assertEqual(adapter.query("synthetic question")[0], 1.0)
        self.assertEqual(tokens("短途旅行坐火车"), ["短途", "途旅", "旅行", "行坐", "坐火", "火车"])
        self.assertEqual(rank_hybrid(["a", "b", "c", "d"], ["d", "c", "b", "a"],
                                     {path: "ordinary" for path in "abcd"}).index("d") < 3, True)

    def test_reconcile_reuses_vectors_and_searches_all_strategies(self):
        s3, table, embeddings = FakeS3(), FakeTable(), FakeEmbeddings()
        path = "Projects/Train.md"
        s3.objects[("vault", "notes/" + path)] = b"# Train\n\nTake the train to Orion."
        first = reconcile(s3, table, embeddings, "vault", "indexes")
        self.assertEqual(first["status"], "published")
        self.assertEqual(table.active["Contract"], HYBRID_CONTRACT)
        self.assertEqual(len(embeddings.documents_seen), 1)
        second = reconcile(s3, table, embeddings, "vault", "indexes")
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(len(embeddings.documents_seen), 1)
        search = SnapshotSearch(s3, "indexes", table, S3Notes(s3, "vault"), embeddings)
        for strategy in ("lexical", "vector", "hybrid"):
            self.assertEqual(search.search("train", ["Projects/"], strategy=strategy)["results"][0]["path"], path)
        del s3.objects[("vault", "notes/" + path)]
        self.assertEqual(search.search("train", ["Projects/"], strategy="hybrid")["results"], [])
        third = reconcile(s3, table, embeddings, "vault", "indexes")
        self.assertEqual(third["notes"], 0)
        self.assertEqual(len(embeddings.documents_seen), 1)


if __name__ == "__main__":
    unittest.main()
