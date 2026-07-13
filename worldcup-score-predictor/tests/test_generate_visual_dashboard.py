import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dashboard", ROOT / "scripts" / "generate_visual_dashboard.py"
)
dashboard = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(dashboard)


class DashboardGenerationTests(unittest.TestCase):
    def test_radar_svg_contains_dimension_labels_and_polygon(self):
        analysis = {
            "dimension_analyses": [
                {"dimension_key": "base_strength", "score": 4},
                {"dimension_key": "market_odds", "score": 3},
                {"dimension_key": "clean_sheet", "score": 2},
            ]
        }

        svg = dashboard.build_radar_svg(analysis, width=320, height=320)

        self.assertIn("<svg", svg)
        self.assertIn("base_strength", svg)
        self.assertIn("<polygon", svg)

    def test_dashboard_file_is_written(self):
        analysis = {
            "match": {"team_a": "A队", "team_b": "B队"},
            "dimension_analyses": [
                {"dimension_key": "base_strength", "score": 4},
                {"dimension_key": "market_odds", "score": 3},
                {"dimension_key": "clean_sheet", "score": 2},
            ],
            "score_distribution": {
                "main_paths": [{"score": "1-0", "condition": "主路径"}],
                "low_block_paths": [],
                "big_win_paths": [],
                "btts_paths": [],
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "dashboard.svg"
            dashboard.write_dashboard(analysis, output)

            self.assertTrue(output.exists())
            self.assertIn("A队 vs B队", output.read_text(encoding="utf-8"))

    def test_dashboard_includes_quant_baseline_summary(self):
        analysis = {
            "match": {"team_a": "A队", "team_b": "B队"},
            "dimension_analyses": [{"dimension_key": "base_strength", "score": 4}],
            "score_distribution": {"main_paths": [], "low_block_paths": [], "big_win_paths": [], "btts_paths": []},
            "quant_baseline": {
                "expected_goals": {"team_a_lambda": 1.4, "team_b_lambda": 1.0},
                "poisson": {
                    "top_scores": [
                        {"score": "1-1", "probability": 0.126982, "rank": 1},
                        {"score": "1-0", "probability": 0.126982, "rank": 2},
                    ],
                    "btts_probability": 0.48,
                    "over_2_5_probability": 0.43,
                },
            },
            "prediction_gates": {
                "quant_baseline_gate": {
                    "status": "rejected",
                    "action": "拒绝量化首选，保留合议比分",
                }
            },
        }

        rows = dashboard.quant_baseline_rows(analysis)

        self.assertTrue(any("量化基线" in row for row in rows))
        self.assertTrue(any("1-1" in row for row in rows))
        self.assertTrue(any("rejected" in row for row in rows))


if __name__ == "__main__":
    unittest.main()
