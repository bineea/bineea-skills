import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validator", ROOT / "scripts" / "validate_analysis.py")
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)
CATALOG = json.loads((ROOT / "config" / "dimensions.json").read_text(encoding="utf-8"))


def build_analysis():
    sources = [{"source_id": "s1"}, {"source_id": "s2"}, {"source_id": "s3"}]
    entries = []
    for dimension in CATALOG["dimensions"]:
        checks = {}
        for index, check_key in enumerate(dimension["required_checks"]):
            checks[check_key] = {
                "status": "supported",
                "finding": f"{check_key}：{dimension['key']}的针对性发现{index}",
                "evidence": [f"{dimension['key']}检查项{index}的独立事实"],
                "source_ids": ["s1"],
            }
        entries.append({
            "dimension_key": dimension["key"],
            "score": 3,
            "confidence": "medium",
            "conclusion": f"{dimension['key']}综合结论",
            "check_results": checks,
            "evidence": [f"{dimension['key']}维度独立证据"],
            "source_ids": ["s1"],
            "unknown_items": [],
        })
    player = {
        "player_name": "测试球员",
        "position": "前锋",
        "player_type": "终结型",
        "status": "健康",
        "expected_starter": True,
        "expected_minutes": 90,
        "conclusion": "预计首发并承担主要进攻任务",
        "evidence": ["近期连续首发"],
        "source_ids": ["s2"],
    }
    return {
        "sources": sources,
        "player_assessments": {
            "team_a": [copy.deepcopy(player) for _ in range(3)],
            "team_b": [copy.deepcopy(player) for _ in range(3)],
        },
        "dimension_analyses": entries,
        "final_prediction": {
            "win_tendency": "A队不败",
            "main_score_range": ["1-0", "1-1"],
            "primary_score": "1-0",
            "alternative_scores": ["1-1"],
            "total_goals_min": 1,
            "total_goals_max": 3,
            "both_teams_to_score": "medium",
            "strong_second_goal": "medium",
            "strong_third_goal": "low",
            "weak_first_goal": "medium",
            "weak_second_goal": "low",
            "clean_sheet": "medium",
            "draw_type": "1-1",
            "trigger_conditions": ["早球", "红牌", "门将失误"],
            "tail_scores": ["4-0"],
            "event_scenarios": {
                "favorite_red_card": "改判1-1或0-1",
                "underdog_red_card": "上调至2-0或3-0",
                "underdog_two_red_cards": "进入4-0至6-0尾部",
                "penalty_or_goalkeeper_error": "受益方增加一球路径",
            },
            "confidence": "medium",
        },
    }


class ValidatorRegressionTests(unittest.TestCase):
    def test_valid_analysis_passes(self):
        errors, _ = validator.validate_analysis(CATALOG, build_analysis())
        self.assertEqual([], errors)

    def test_cloned_check_findings_are_rejected(self):
        analysis = build_analysis()
        first = analysis["dimension_analyses"][0]
        for result in first["check_results"].values():
            result["finding"] = "检查项：完全相同的概括"
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("子检查项发现过度重复" in error for error in errors))

    def test_missing_event_scenario_is_rejected(self):
        analysis = build_analysis()
        del analysis["final_prediction"]["event_scenarios"]["underdog_two_red_cards"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("event_scenarios 缺少情景" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
