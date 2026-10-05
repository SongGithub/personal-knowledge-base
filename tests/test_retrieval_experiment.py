import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import retrieval_experiment as r


class RetrievalExperimentTest(unittest.TestCase):
    def test_local_endpoint_only(self):
        self.assertEqual(r.endpoint("http://127.0.0.1:8000/v1"), "http://127.0.0.1:8000/v1")
        for url in ("https://api.example.com/v1", "http://192.168.1.2:8000/v1", "file:///tmp/model"):
            with self.assertRaises(ValueError):
                r.endpoint(url)

    def test_authority_and_deterministic_fusion(self):
        self.assertEqual(r.authority("Canonical/Policy.md", "", {"Canonical/Policy.md": "canonical"}), "canonical")
        self.assertEqual(r.authority("Sources/Source Archives/old.md", "", {}), "archive")
        self.assertEqual(r.authority("Sources/_Review/new.md", "", {}), "unverified")
        self.assertEqual(r.authority("any.md", "", {"any.md": "verified"}), "verified")
        search = object.__new__(r.Search)
        search.tiers = {"canonical.md": "canonical", "archive.md": "archive"}
        self.assertEqual(search.hybrid(["archive.md", "canonical.md"], ["archive.md", "canonical.md"])[0], "canonical.md")
        self.assertEqual(search.hybrid(["archive.md", "canonical.md"], ["archive.md", "canonical.md"]), search.hybrid(["archive.md", "canonical.md"], ["archive.md", "canonical.md"]))

    def test_index_and_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vault = root / "vault"
            (vault / "Canonical").mkdir(parents=True)
            (vault / "Archive").mkdir(parents=True)
            (vault / "Canonical/Orion travel.md").write_text("# Orion travel\n\nThe current travel rule allows trains.")
            (vault / "Archive/Old Orion travel.md").write_text("# Orion travel\n\nThe old rule allowed flights.")
            db = r.database(root / "index.sqlite")

            def fake_embed(texts, *_):
                vectors = []
                for text in texts:
                    vec = np.asarray([2.0 if "train" in text.lower() else 1.0, 1.0 if "orion" in text.lower() else 0.0], dtype=np.float32)
                    vectors.append(vec / np.linalg.norm(vec))
                return np.stack(vectors)

            with patch.object(r, "embed", side_effect=fake_embed):
                info = r.build(vault, db, "http://127.0.0.1:8000/v1", "synthetic", {"Canonical/Orion travel.md": "canonical"})
                self.assertEqual(info["notes"], 2)
                self.assertFalse(r.build(vault, db, "http://127.0.0.1:8000/v1", "synthetic", {"Canonical/Orion travel.md": "canonical"})["rebuilt"])
                search = r.Search(db, "http://127.0.0.1:8000/v1", "synthetic")
                cases = json.loads((Path(__file__).parents[1] / "examples/synthetic-cases.json").read_text())
                report = r.run_benchmark(search, cases, 3)
            self.assertEqual(report["summary"]["hybrid"]["same_top1_rate"], 1.0)
            self.assertEqual(report["summary"]["hybrid"]["ranking_variance"], 0.0)
            self.assertEqual(report["summary"]["hybrid"]["canonical_top1_rate"], 1.0)
            self.assertEqual(len(report["results"]["hybrid"]), 6)


if __name__ == "__main__":
    unittest.main()
