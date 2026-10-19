"""Deterministic checks for the live synthetic retrieval comparison gate."""
import unittest
import json

from tools.benchmark_cloud_embeddings import FIXTURE, compare_strategies, quality_gate


class ComparisonTests(unittest.TestCase):
    def test_fixture_covers_retrieval_failure_modes(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertGreaterEqual(len(fixture["notes"]), 20)
        self.assertGreaterEqual(len(fixture["cases"]), 30)
        self.assertGreaterEqual(sum(case.get("cross_language", False) for case in fixture["cases"]), 6)
        self.assertGreaterEqual(sum(case.get("exact_match", False) for case in fixture["cases"]), 7)
        self.assertGreaterEqual(sum(case.get("category") == "near_collision" for case in fixture["cases"]), 4)
        self.assertGreaterEqual(sum(case.get("category") == "paraphrase" for case in fixture["cases"]), 4)

    def test_vector_wins_when_hybrid_loses_top_one(self):
        rows = {
            "lexical": {"top1": 12, "top3": 12, "cross_language_top3": 0, "exact_top1": 4, "mrr": .86},
            "vector": {"top1": 14, "top3": 14, "cross_language_top3": 2, "exact_top1": 2, "mrr": 1.0},
            "hybrid": {"top1": 12, "top3": 14, "cross_language_top3": 2, "exact_top1": 4, "mrr": .94},
        }
        result = compare_strategies(rows)
        self.assertEqual(result["winner"], "vector")
        self.assertFalse(result["default_is_best"])
        self.assertEqual(result["default_top1_gap"], 2)

    def test_default_wins_a_full_tie(self):
        row = {"top1": 14, "top3": 14, "cross_language_top3": 2, "exact_top1": 4, "mrr": 1.0}
        result = compare_strategies({name: row for name in ("lexical", "vector", "hybrid")})
        self.assertEqual(result["winner"], "hybrid")
        self.assertTrue(result["default_is_best"])

    def test_current_hybrid_fails_expanded_cross_language_floor(self):
        rows = {
            "lexical": {"top1": 22},
            "hybrid": {"total": 33, "top1": 25, "top3": 31,
                       "cross_language_total": 6, "cross_language_top3": 5,
                       "exact_total": 7, "exact_top1": 6},
        }
        self.assertFalse(quality_gate(rows))


if __name__ == "__main__":
    unittest.main()
