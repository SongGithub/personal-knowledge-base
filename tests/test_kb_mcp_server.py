import json
import io
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import retrieval_experiment as retrieval
from kb_mcp_server import IndexUnavailable, KBService, MCPProtocol, serve


class KBMCPServerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        (self.vault / "Canonical").mkdir(parents=True)
        (self.vault / "Archive").mkdir()
        (self.vault / "Canonical/Orion.md").write_text(
            "# Orion policy\n\nCurrent travel rule allows trains and must be followed.\n",
            encoding="utf-8",
        )
        (self.vault / "Archive/Old Orion.md").write_text(
            "# Orion policy\n\nOld travel rule allowed flights.\n",
            encoding="utf-8",
        )
        self.db_path = self.root / "private-index/index.sqlite"
        db = retrieval.database(self.db_path)

        def fake_embed(texts, *_):
            vectors = []
            for text in texts:
                vec = np.asarray(
                    [2.0 if "train" in text.lower() else 1.0, 1.0 if "orion" in text.lower() else 0.0],
                    dtype=np.float32,
                )
                vectors.append(vec / np.linalg.norm(vec))
            return np.stack(vectors)

        with patch.object(retrieval, "embed", side_effect=fake_embed):
            retrieval.build(
                self.vault,
                db,
                "http://127.0.0.1:8000/v1",
                "synthetic",
                {"Canonical/Orion.md": "canonical"},
            )
        db.close()
        self.service = KBService(
            self.vault,
            self.db_path,
            "http://127.0.0.1:8000/v1",
            "synthetic",
            {"Canonical/Orion.md": "canonical"},
        )
        self.protocol = MCPProtocol(self.service)

    def tearDown(self):
        self.temp.cleanup()

    def call_tool(self, name, arguments):
        response = self.protocol.handle(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        )
        self.assertEqual(response["id"], 4)
        result = response["result"]
        self.assertFalse(result.get("isError"), result["content"][0]["text"])
        return json.loads(result["content"][0]["text"])

    def test_only_read_only_tools_are_advertised(self):
        response = self.protocol.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual([tool["name"] for tool in response["result"]["tools"]], ["search_kb", "fetch_note"])
        self.assertEqual(response["result"]["tools"][0]["inputSchema"]["properties"]["strategy"]["default"], "hybrid")
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] for tool in response["result"]["tools"]))

    def test_search_matches_existing_hybrid_ranking_and_returns_excerpt(self):
        with patch.object(retrieval, "embed", return_value=np.asarray([[1.0, 0.0]], dtype=np.float32)):
            result = self.call_tool("search_kb", {"query": "Orion travel trains", "limit": 5, "strategy": "hybrid"})
        db = retrieval.sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            search = retrieval.Search(db, "http://127.0.0.1:8000/v1", "synthetic")
            with patch.object(retrieval, "embed", return_value=np.asarray([[1.0, 0.0]], dtype=np.float32)):
                lex, vec = search.lexical("Orion travel trains"), search.vector("Orion travel trains")
            expected = search.hybrid(lex, vec)
        finally:
            db.close()
        self.assertEqual([row["path"] for row in result["results"]], expected[:5])
        self.assertEqual(result["results"][0]["tier"], "canonical")
        self.assertIn("travel rule", result["results"][0]["excerpt"])

    def test_fetch_note_rejects_traversal_absolute_and_non_markdown_paths(self):
        for path in ("../outside.md", str(self.root / "secret.md"), "Canonical/Orion.md/../../secret"):
            with self.subTest(path=path):
                response = self.protocol.handle(
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "fetch_note", "arguments": {"path": path}}}
                )
                self.assertTrue(response["result"]["isError"])

    def test_service_rejects_vault_or_index_inside_public_repository(self):
        repository = Path(__file__).parents[1]
        with self.assertRaises(ValueError):
            KBService(repository, self.db_path, "http://127.0.0.1:8000/v1", "synthetic")
        with self.assertRaises(ValueError):
            KBService(self.vault, repository / "index.sqlite", "http://127.0.0.1:8000/v1", "synthetic")

    def test_fetch_note_returns_cited_vault_relative_content(self):
        result = self.call_tool("fetch_note", {"path": "Canonical/Orion.md"})
        self.assertEqual(result["path"], "Canonical/Orion.md")
        self.assertEqual(result["tier"], "canonical")
        self.assertIn("Current travel rule", result["content"])

    def test_stdio_transport_emits_only_json_rpc_responses(self):
        incoming = io.StringIO(
            '\n{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}\n'
            '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        )
        outgoing = io.StringIO()
        serve(self.protocol, incoming, outgoing)
        messages = [json.loads(line) for line in outgoing.getvalue().splitlines()]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["result"]["serverInfo"]["name"], "personal-kb-retrieval")

    def test_unknown_tool_arguments_are_rejected(self):
        response = self.protocol.handle(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_kb", "arguments": {"query": "x", "sql": "select *"}}}
        )
        self.assertEqual(response["error"]["code"], -32602)

    def test_index_missing_or_stale_is_reported_without_rebuilding(self):
        stale = KBService(self.vault, self.db_path, "http://127.0.0.1:8000/v1", "different-model")
        with self.assertRaises(IndexUnavailable):
            stale.search_kb("Orion", 5, "lexical")
        self.assertTrue(self.db_path.exists())
        (self.vault / "Canonical/Orion.md").write_text("changed after indexing", encoding="utf-8")
        with self.assertRaises(IndexUnavailable):
            self.service.search_kb("Orion", 5, "lexical")

    def test_search_uses_index_read_only(self):
        before = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        self.service.search_kb("Orion travel", 5, "lexical")
        after = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        self.assertEqual(after, before)

    def test_json_rpc_initialize_tools_and_notifications(self):
        initialized = self.protocol.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}
        )
        self.assertEqual(initialized["result"]["protocolVersion"], "2024-11-05")
        self.assertIsNone(self.protocol.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))


if __name__ == "__main__":
    unittest.main()
