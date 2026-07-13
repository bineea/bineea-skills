import importlib.util
import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("quant_baseline", ROOT / "scripts" / "quant_baseline.py")
quant_baseline = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(quant_baseline)


class QuantBaselineTests(unittest.TestCase):
    def test_poisson_matrix_top_scores_are_stable(self):
        result = quant_baseline.poisson_summary(1.4, 1.0, max_goals=7)

        self.assertEqual("1-1", result["top_scores"][0]["score"])
        self.assertAlmostEqual(
            result["top_scores"][0]["probability"],
            math.exp(-2.4) * 1.4,
            places=6,
        )
        for score in result["top_scores"]:
            self.assertGreaterEqual(score["probability"], 0)
            self.assertLessEqual(score["probability"], 1)
        for value in result["outcome_probabilities"].values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 1)
        self.assertGreater(result["overflow_probability"], 0)

    def test_direct_xg_blends_xg_and_goal_rates(self):
        payload = {
            "quant_baseline_inputs": {
                "team_a": {
                    "xg_for": 1.8,
                    "xg_against": 0.9,
                    "goals_for_rate": 1.4,
                    "goals_against_rate": 1.1,
                },
                "team_b": {
                    "xg_for": 1.2,
                    "xg_against": 1.5,
                    "goals_for_rate": 1.0,
                    "goals_against_rate": 1.2,
                },
                "sources": ["src_xg_001"],
            }
        }

        result = quant_baseline.build_quant_baseline(payload)

        team_a_xg_lambda = math.sqrt(1.8 * 1.5)
        team_a_goal_lambda = math.sqrt(1.4 * 1.2)
        expected_a = 0.70 * team_a_xg_lambda + 0.30 * team_a_goal_lambda
        self.assertEqual("computed", result["status"])
        self.assertEqual("direct", result["xg"]["status"])
        self.assertAlmostEqual(result["expected_goals"]["team_a_lambda"], expected_a, places=4)
        self.assertEqual(["src_xg_001"], result["source_ids"])

    def test_missing_xg_falls_back_to_partial_goal_rate_baseline(self):
        payload = {
            "quant_baseline_inputs": {
                "team_a": {"goals_for_rate": 1.4, "goals_against_rate": 1.1},
                "team_b": {"goals_for_rate": 1.0, "goals_against_rate": 1.2},
            }
        }

        result = quant_baseline.build_quant_baseline(payload)

        self.assertEqual("partial", result["status"])
        self.assertEqual("unavailable", result["xg"]["status"])
        self.assertIn("xG", " ".join(result["missing_inputs"]))

    def test_unavailable_sanger_does_not_change_lambda(self):
        payload = {
            "quant_baseline_inputs": {
                "team_a": {"goals_for_rate": 1.4, "goals_against_rate": 1.1},
                "team_b": {"goals_for_rate": 1.0, "goals_against_rate": 1.2},
                "sanger": {"status": "unavailable"},
            }
        }

        baseline = quant_baseline.build_quant_baseline(payload)

        self.assertEqual("unavailable", baseline["sanger"]["status"])
        self.assertEqual(0, baseline["sanger"]["team_a_lambda_delta"])
        self.assertEqual(0, baseline["sanger"]["team_b_lambda_delta"])

    def test_cli_outputs_quant_baseline_fragment(self):
        payload = {
            "quant_baseline_inputs": {
                "team_a": {"goals_for_rate": 1.4, "goals_against_rate": 1.1},
                "team_b": {"goals_for_rate": 1.0, "goals_against_rate": 1.2},
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "pack.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            completed = subprocess.run(
                [
                    "py",
                    "-3.13",
                    str(ROOT / "scripts" / "quant_baseline.py"),
                    "--input",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        fragment = json.loads(completed.stdout)
        self.assertIn("quant_baseline", fragment)
        self.assertIn("poisson", fragment["quant_baseline"])


if __name__ == "__main__":
    unittest.main()
