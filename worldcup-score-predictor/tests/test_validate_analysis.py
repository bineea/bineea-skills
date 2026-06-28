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


def build_review_metadata():
    assignments = CATALOG["dimension_review_assignments"]
    return {
        "schema_version": "multi-agent-review-1.0",
        "mode": "multi_agent_consensus",
        "role_results_used": [
            "attack_agent",
            "defense_risk_agent",
            "market_history_agent",
            "anti_btts_agent",
            "tail_score_agent",
            "skeptic_agent",
            "consensus_arbiter",
        ],
        "primary_dimension_owners": copy.deepcopy(assignments["primary"]),
        "review_dimension_owners": copy.deepcopy(assignments["review"]),
        "conflicts_resolved": [
            {
                "issue_id": "D1",
                "issue_type": "score_gap",
                "affected_dimensions": ["strong_third_goal"],
                "positions": [
                    {
                        "role_id": "attack_agent",
                        "position": "强队第三球为 medium",
                    },
                    {
                        "role_id": "skeptic_agent",
                        "objection": "替补冲击证据不足，不应上调到 high",
                    },
                ],
                "resolution": "保留 medium，不进入唯一主路径",
                "confidence_change": "high -> medium",
            }
        ],
        "claims_rejected": [
            {
                "role_id": "attack_agent",
                "claim": "强队第三球可以上调为 high",
                "reason": "缺少第二个高质量来源支撑替补冲击",
            }
        ],
        "unknown_rationale": [],
    }


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
        "review_metadata": build_review_metadata(),
        "market_calibration": {
            "market_signal": "balanced",
            "favorite_handicap": 1.0,
            "goal_line": 2.5,
            "btts_market": "medium",
            "model_vs_market_gap": "aligned",
            "calibration_action": "维持模型判断",
            "source_ids": ["s3"],
        },
        "prediction_gates": {
            "weak_goal_gate": {
                "status": "pass",
                "original_level": "medium",
                "final_level": "medium",
                "independent_paths": ["反击速度", "定位球高点"],
                "action": "保留弱队第一球为 medium",
                "reason": "存在两条独立进球路径",
            },
            "clean_sheet_gate": {
                "status": "pass",
                "clean_sheet_level": "medium",
                "weak_goal_level": "medium",
                "conflict_resolved": True,
                "action": "同时保留零封和弱队进球路径为不同比分分布",
                "reason": "1-0与1-1分别进入主路径",
            },
            "market_calibration_gate": {
                "status": "pass",
                "market_signal": "balanced",
                "action": "不触发强队大胜硬上调",
                "reason": "让球未达到深盘阈值",
            },
            "low_block_draw_gate": {
                "status": "pass",
                "low_block_risk": "medium",
                "selected_score": "1-0",
                "action": "保留1-0闷局路径",
                "reason": "强队可能小胜但总进球偏低",
            },
            "tail_score_gate": {
                "status": "pass",
                "tail_scores_checked": ["4-0", "1-0", "1-1"],
                "action": "保留大胜、闷局和双方进球尾部",
                "reason": "三类尾部均已检查",
            },
        },
        "score_distribution": {
            "main_paths": [
                {"score": "1-0", "probability": "medium", "condition": "强队控场但第二球不足"},
                {"score": "1-1", "probability": "medium", "condition": "弱队两条进球路径兑现"},
            ],
            "low_block_paths": [
                {"score": "1-0", "status": "pass", "reason": "低比分小胜路径成立"}
            ],
            "big_win_paths": [
                {"score": "4-0", "status": "tail", "reason": "弱队红牌或后程崩盘"}
            ],
            "btts_paths": [
                {"score": "1-1", "status": "pass", "reason": "弱队有两条独立路径"}
            ],
        },
        "tail_scenarios": [
            {"scenario_type": "big_win", "score": "4-0", "status": "tail", "condition": "弱队红牌或连续失误"},
            {"scenario_type": "low_block", "score": "1-0", "status": "main", "condition": "强队控场但机会质量一般"},
            {"scenario_type": "btts", "score": "1-1", "status": "main", "condition": "弱队反击或定位球得分"},
        ],
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

    def test_missing_review_metadata_is_rejected(self):
        analysis = build_analysis()
        del analysis["review_metadata"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("review_metadata 必须是对象" in error for error in errors))

    def test_missing_required_role_is_rejected(self):
        analysis = build_analysis()
        analysis["review_metadata"]["role_results_used"].remove("skeptic_agent")
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("缺少必需角色" in error for error in errors))

    def test_missing_resolved_conflict_is_rejected(self):
        analysis = build_analysis()
        analysis["review_metadata"]["conflicts_resolved"] = []
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("已裁决分歧" in error for error in errors))

    def test_high_confidence_requires_multiple_sources(self):
        analysis = build_analysis()
        first = analysis["dimension_analyses"][0]
        first["confidence"] = "high"
        first["source_ids"] = ["s1"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("high confidence" in error for error in errors))

    def test_weak_goal_medium_requires_two_independent_paths(self):
        analysis = build_analysis()
        analysis["prediction_gates"]["weak_goal_gate"]["independent_paths"] = ["单一反击点"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("独立进球路径" in error for error in errors))

    def test_deep_market_requires_third_goal_and_big_win_score(self):
        analysis = build_analysis()
        analysis["market_calibration"]["market_signal"] = "favorite_big_win"
        analysis["market_calibration"]["favorite_handicap"] = 2.0
        analysis["final_prediction"]["strong_third_goal"] = "low"
        analysis["final_prediction"]["tail_scores"] = ["2-0"]
        analysis["score_distribution"]["big_win_paths"] = [
            {"score": "2-0", "status": "tail", "reason": "不是大胜"}
        ]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("strong_third_goal" in error for error in errors))
        self.assertTrue(any("净胜3球" in error for error in errors))

    def test_btts_medium_requires_weak_goal_gate_paths(self):
        analysis = build_analysis()
        analysis["final_prediction"]["weak_first_goal"] = "low"
        analysis["final_prediction"]["both_teams_to_score"] = "medium"
        analysis["prediction_gates"]["weak_goal_gate"]["final_level"] = "low"
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("weak_first_goal 为 low" in error for error in errors))

    def test_clean_sheet_and_weak_goal_conflict_requires_resolution(self):
        analysis = build_analysis()
        analysis["prediction_gates"]["clean_sheet_gate"]["conflict_resolved"] = False
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("显式裁决冲突" in error for error in errors))

    def test_score_distribution_is_required(self):
        analysis = build_analysis()
        del analysis["score_distribution"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("score_distribution 必须是对象" in error for error in errors))

    def test_tail_scenarios_require_all_types(self):
        analysis = build_analysis()
        analysis["tail_scenarios"] = [
            {"scenario_type": "big_win", "score": "4-0", "status": "tail", "condition": "弱队崩盘"}
        ]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("tail_scenarios 缺少类型" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
