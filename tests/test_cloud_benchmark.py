"""Deterministic checks for the live synthetic retrieval comparison gate."""
import unittest

from tools.benchmark_cloud_embeddings import compare_strategies


class ComparisonTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
