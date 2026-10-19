"""Cold/warm API Gateway event checks against the real Lambda ASGI adapter."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

from cloud_kb import api


class Unused:
    def __getattr__(self, name):
        raise AssertionError("Unexpected data access: " + name)


class LambdaAdapterTests(unittest.TestCase):
    def test_repeated_invocations_and_legacy_handshake(self):
        pair = RSAKeyPair.generate()
        verifier = JWTVerifier(public_key=pair.public_key, issuer="https://synthetic.invalid", audience="synthetic-kb")
        app = api.create_app(auth_provider=verifier, gate=Unused(), notes=Unused(), search=Unused(),
                             writer=Unused(), base_url="https://synthetic.execute-api.invalid")
        token = pair.create_token(issuer="https://synthetic.invalid", audience="synthetic-kb")
        def event(method, params=None, authenticated=True):
            headers = {"host": "synthetic.execute-api.invalid", "content-type": "application/json",
                       "accept": "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25"}
            if authenticated:
                headers["authorization"] = "Bearer " + token
            return {"version": "2.0", "routeKey": "$default", "rawPath": "/mcp", "rawQueryString": "",
                    "headers": headers, "isBase64Encoded": False,
                    "requestContext": {"http": {"method": "POST", "path": "/mcp", "sourceIp": "127.0.0.1"}},
                    "body": json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})}
        # Mangum expects an available synchronous invocation event loop.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with patch.object(api, "production_app", return_value=app) as factory, patch.object(api, "_handler", None):
                denied = api.handler(event("tools/list", authenticated=False), SimpleNamespace())
                self.assertEqual(denied["statusCode"], 401)
                initialized = api.handler(event("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "synthetic-lambda-test", "version": "1"}}), SimpleNamespace())
                self.assertEqual(initialized["statusCode"], 200)
                self.assertEqual(json.loads(initialized["body"])["result"]["protocolVersion"], "2025-11-25")
                for _ in range(2):
                    listed = api.handler(event("tools/list"), SimpleNamespace())
                    self.assertEqual(listed["statusCode"], 200)
                    names = {tool["name"] for tool in json.loads(listed["body"])["result"]["tools"]}
                    self.assertEqual(names, {"search_kb", "fetch_note", "capture_learning",
                                             "get_change_status", "get_access_status"})
                self.assertEqual(factory.call_count, 1)
        finally:
            loop.close()
            asyncio.set_event_loop(None)


if __name__ == "__main__":
    unittest.main()
