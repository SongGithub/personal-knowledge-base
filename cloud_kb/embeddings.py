"""Pinned Bedrock embedding contract shared by ingestion and query serving."""
from array import array
import json
import math
import sys
import time

from botocore.exceptions import BotoCoreError, ClientError


MODEL_ID = "cohere.embed-multilingual-v3"
REGION = "ap-southeast-2"
DIMENSIONS = 1024
CONTRACT = "bedrock-cohere-multilingual-v3-f32-unit-paragraph-1500-v1"


def normalized(values):
    if len(values) != DIMENSIONS or not all(isinstance(x, (float, int)) and math.isfinite(x) for x in values):
        raise ValueError("invalid_embedding")
    length = math.sqrt(sum(x * x for x in values))
    if length <= 0:
        raise ValueError("invalid_embedding")
    return [float(x / length) for x in values]


def pack(values):
    result = array("f", normalized(values))
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


def unpack(raw):
    if len(raw) != DIMENSIONS * 4:
        raise ValueError("incompatible_embedding_contract")
    result = array("f")
    result.frombytes(raw)
    if sys.byteorder != "little":
        result.byteswap()
    if not all(math.isfinite(x) for x in result):
        raise ValueError("invalid_embedding")
    return result


class BedrockEmbeddings:
    def __init__(self, client, *, model_id=MODEL_ID):
        if model_id != MODEL_ID:
            raise ValueError("unapproved_embedding_model")
        self.client = client
        self.model_id = model_id

    def embed(self, texts, *, input_type):
        if input_type not in {"search_document", "search_query"} or not 1 <= len(texts) <= 96:
            raise ValueError("invalid_embedding_request")
        if any(not isinstance(text, str) or not text.strip() or len(text) > 2000 for text in texts):
            raise ValueError("embedding_input_too_long")
        request = json.dumps({"texts": texts, "input_type": input_type, "truncate": "NONE"})
        for attempt in range(3):
            try:
                response = self.client.invoke_model(
                    modelId=self.model_id, contentType="application/json", accept="application/json", body=request,
                )
                body = response["body"]
                try:
                    payload = json.loads(body.read())
                finally:
                    body.close()
                vectors = payload["embeddings"]
                if len(vectors) != len(texts):
                    raise ValueError("invalid_embedding_response")
                return [normalized(vector) for vector in vectors]
            except ClientError as error:
                code = error.response.get("Error", {}).get("Code", "")
                if code not in {"ThrottlingException", "ModelNotReadyException", "ServiceUnavailableException"} or attempt == 2:
                    raise RuntimeError("provider_unavailable") from None
            except BotoCoreError:
                if attempt == 2:
                    raise RuntimeError("provider_unavailable") from None
            time.sleep(.25 * 2 ** attempt)

    def query(self, text):
        return self.embed([text], input_type="search_query")[0]

    def documents(self, texts):
        return self.embed(texts, input_type="search_document")
