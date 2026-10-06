import hashlib
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
        self.assertEqual(r.authority("Archive/old.md", "", {}), "archive")
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

    def test_source_snapshot_does_not_follow_markdown_symlinks_outside_vault(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vault = root / "vault"
            vault.mkdir()
            outside = root / "outside.md"
            outside.write_text("private content", encoding="utf-8")
            (vault / "linked.md").symlink_to(outside)
            (vault / "local.md").write_text("local content", encoding="utf-8")
            manifest, _ = r.source_snapshot(vault)
        self.assertEqual([entry[0] for entry in manifest], ["local.md"])


class RecordingEmbed:
    """Deterministic embed() stand-in that records every text it is asked for."""

    def __init__(self):
        self.calls = []

    def __call__(self, texts, *_):
        self.calls.append(list(texts))
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = np.asarray([digest[i] + 1 for i in range(4)], dtype=np.float32)
            vectors.append(vec / np.linalg.norm(vec))
        return np.stack(vectors)

    @property
    def texts(self):
        return [text for call in self.calls for text in call]


class IncrementalIndexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / "a.md").write_text("# A\n\nalpha original body", encoding="utf-8")
        (self.vault / "b.md").write_text("# B\n\nbravo original body", encoding="utf-8")
        self.db = r.database(self.root / "index.sqlite")

    def build(self, **kwargs):
        recorder = RecordingEmbed()
        overrides = kwargs.pop("overrides", {})
        model = kwargs.pop("model", "synthetic")
        with patch.object(r, "embed", side_effect=recorder):
            info = r.build(self.vault, self.db, "http://127.0.0.1:8000/v1", model, overrides, **kwargs)
        return info, recorder

    def vectors(self):
        return {(row[0], row[1]): row[2] for row in self.db.execute("SELECT path,ordinal,vector FROM chunks")}

    def test_second_run_without_changes_is_a_noop_and_preserves_vectors(self):
        first, recorded = self.build()
        self.assertTrue(first["full_rebuild"])
        self.assertEqual(first["embedded_chunks"], 2)
        before = self.vectors()
        second, second_recorded = self.build()
        self.assertEqual(second["mode"], "noop")
        self.assertEqual(second["embedded_chunks"], 0)
        self.assertEqual(second_recorded.calls, [])
        self.assertEqual(self.vectors(), before)

    def test_single_note_change_reindexes_only_that_note(self):
        self.build()
        before = self.vectors()
        (self.vault / "b.md").write_text("# B\n\nbravo CHANGED body zzz", encoding="utf-8")
        info, recorded = self.build()
        self.assertEqual((info["changed"], info["unchanged"]), (1, 1))
        self.assertEqual(info["embedded_chunks"], 1)
        self.assertFalse(any("alpha" in text for text in recorded.texts))
        self.assertTrue(any("CHANGED" in text for text in recorded.texts))
        after = self.vectors()
        self.assertEqual(after[("a.md", 0)], before[("a.md", 0)])

    def test_added_note_embeds_only_the_new_note(self):
        self.build()
        (self.vault / "c.md").write_text("# C\n\ncharlie brand new body", encoding="utf-8")
        info, recorded = self.build()
        self.assertEqual(info["added"], 1)
        self.assertTrue(recorded.texts)
        self.assertTrue(all("charlie" in text.lower() for text in recorded.texts))

    def test_deleted_note_is_removed_and_no_embeddings_run(self):
        self.build()
        (self.vault / "a.md").unlink()
        info, recorded = self.build()
        self.assertEqual(info["deleted"], 1)
        self.assertEqual(recorded.calls, [])
        self.assertEqual({row[0] for row in self.db.execute("SELECT path FROM notes")}, {"b.md"})
        self.assertEqual({row[0] for row in self.db.execute("SELECT path FROM chunks")}, {"b.md"})

    def test_authority_only_change_updates_tier_without_embedding(self):
        self.build()
        before = self.vectors()
        info, recorded = self.build(overrides={"a.md": "canonical"})
        self.assertEqual(info["mode"], "authority")
        self.assertTrue(info["authority_refreshed"])
        self.assertEqual(recorded.calls, [])
        tier = self.db.execute("SELECT tier FROM notes WHERE path='a.md'").fetchone()[0]
        self.assertEqual(tier, "canonical")
        self.assertEqual(self.vectors(), before)

    def test_model_change_forces_full_rebuild(self):
        self.build()
        info, recorded = self.build(model="different-model")
        self.assertTrue(info["full_rebuild"])
        self.assertEqual(info["mode"], "full")
        self.assertEqual(len(recorded.texts), 2)

    def test_chunker_change_forces_full_rebuild(self):
        self.build()
        with patch.object(r, "CHUNKER", "paragraph-1500-v2"):
            info, _ = self.build()
        self.assertTrue(info["full_rebuild"])
        self.assertEqual(info["mode"], "full")

    def test_missing_vector_forces_full_rebuild(self):
        self.build()
        with self.db:
            self.db.execute("UPDATE chunks SET vector=NULL WHERE path='a.md'")
        info, _ = self.build()
        self.assertTrue(info["full_rebuild"])


if __name__ == "__main__":
    unittest.main()
