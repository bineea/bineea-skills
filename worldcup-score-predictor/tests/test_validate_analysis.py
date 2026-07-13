import copy
import hashlib
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


AGENT_RUN_IDS = {
    "attack_agent": "019f32d6-f852-7362-ad17-eb70507b0311",
    "defense_risk_agent": "019f32d6-f852-7362-ad17-eb70507b0322",
    "market_history_agent": "019f32d6-f852-7362-ad17-eb70507b0333",
    "anti_btts_agent": "019f32d6-f852-7362-ad17-eb70507b0344",
    "tail_score_agent": "019f32d6-f852-7362-ad17-eb70507b0355",
    "skeptic_agent": "019f32d6-f852-7362-ad17-eb70507b0366",
    "consensus_arbiter": "019f32d6-f852-7362-ad17-eb70507b0377",
}


def artifact_hash(role_id):
    path = ROOT / "tests" / "fixtures" / "agent_runs" / f"{role_id}.json"
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_review_metadata():
    assignments = CATALOG["dimension_review_assignments"]
    roles = [
        "attack_agent",
        "defense_risk_agent",
        "market_history_agent",
        "anti_btts_agent",
        "tail_score_agent",
        "skeptic_agent",
        "consensus_arbiter",
    ]
    return {
        "schema_version": "multi-agent-review-1.0",
        "mode": "multi_agent_consensus",
        "role_results_used": roles,
        "agent_execution": {
            "execution_mode": "independent_subagents",
            "orchestrator": "codex_multi_agent",
            "tooling": "multi_agent_v1.spawn_agent",
            "fallback_used": False,
            "runs": [
                {
                    "role_id": role,
                    "agent_run_id": AGENT_RUN_IDS[role],
                    "agent_type": "worker" if role != "consensus_arbiter" else "default",
                    "tool_call_id": f"call_{index:03d}",
                    "started_at": f"2026-06-18T09:{index:02d}:00Z",
                    "completed_at": f"2026-06-18T09:{index + 10:02d}:00Z",
                    "artifact_type": "dimension_patch" if role != "consensus_arbiter" else "arbiter_merge",
                    "artifact_ref": f"tests/fixtures/agent_runs/{role}.json",
                    "summary_hash": artifact_hash(role),
                    "status": "completed",
                }
                for index, role in enumerate(roles, start=1)
            ],
        },
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
        "advanced_metrics": {
            "xg_per90": 0.32,
            "xa_per90": 0.18,
            "shots_per90": 2.4,
            "dribbles_completed_per90": 1.2,
            "dribbled_past_per90": 0.4,
            "temperature_stamina_note": "常温样本下冲刺和回防稳定",
        },
    }
    return {
        "sources": sources,
        "player_assessments": {
            "team_a": [copy.deepcopy(player) for _ in range(3)],
            "team_b": [copy.deepcopy(player) for _ in range(3)],
        },
        "player_matchup_edges": [
            {
                "matchup_id": "M1",
                "attacker": "测试球员",
                "defender": "测试球员",
                "matchup_type": "wing_vs_fullback",
                "metric_comparison": "场均成功过人1.2次 vs 场均被过0.4次",
                "edge": "team_a",
                "source_ids": ["s2"],
            },
            {
                "matchup_id": "M2",
                "attacker": "测试球员",
                "defender": "测试球员",
                "matchup_type": "striker_vs_center_back",
                "metric_comparison": "xG/90与防空成功率形成中性对位",
                "edge": "neutral",
                "source_ids": ["s2"],
            },
            {
                "matchup_id": "M3",
                "attacker": "测试球员",
                "defender": "测试球员",
                "matchup_type": "pressing_vs_build_up",
                "metric_comparison": "压迫频率对后场出球失误率",
                "edge": "team_b",
                "source_ids": ["s2"],
            },
        ],
        "dimension_analyses": entries,
        "review_metadata": build_review_metadata(),
        "dynamic_weighting": {
            "model_version": "dynamic-weight-1.0",
            "context": {
                "stage": "group_stage",
                "temperature_c": 26,
                "rest_delta_days": 0,
            },
            "adjustments": [
                {
                    "dimension_key": "stage_psychology",
                    "base_weight": 1.0,
                    "adjusted_weight": 1.1,
                    "trigger_type": "stage",
                    "reason": "小组赛压力存在但未达到淘汰赛级别",
                    "source_ids": ["s1"],
                },
                {
                    "dimension_key": "environment_schedule",
                    "base_weight": 1.0,
                    "adjusted_weight": 1.0,
                    "trigger_type": "environment",
                    "reason": "温度和休息天数未触发额外体能修正",
                    "source_ids": ["s1"],
                },
            ],
            "learning_feedback": {
                "status": "applied",
                "sample_count": 12,
                "summary": "参考历史误差样本后维持基础权重",
            },
        },
        "quant_baseline": {
            "schema_version": "quant-baseline-1.0",
            "status": "partial",
            "source_ids": ["s3"],
            "missing_inputs": ["缺少 direct xG/xGA，使用进球率回退基线"],
            "xg": {
                "status": "unavailable",
                "team_a_xg_for": None,
                "team_a_xg_against": None,
                "team_b_xg_for": None,
                "team_b_xg_against": None,
                "source_ids": [],
                "reason": "测试样本未提供 direct xG/xGA",
            },
            "expected_goals": {
                "team_a_lambda": 1.20,
                "team_b_lambda": 0.95,
                "total_lambda": 2.15,
                "lambda_components": {
                    "team_a": {
                        "xg_component": None,
                        "goal_rate_component": 1.20,
                        "sanger_delta": 0,
                        "final_lambda": 1.20,
                    },
                    "team_b": {
                        "xg_component": None,
                        "goal_rate_component": 0.95,
                        "sanger_delta": 0,
                        "final_lambda": 0.95,
                    },
                },
            },
            "poisson": {
                "max_goals": 7,
                "top_scores": [
                    {"score": "1-0", "probability": 0.12, "rank": 1},
                    {"score": "1-1", "probability": 0.11, "rank": 2},
                    {"score": "2-0", "probability": 0.07, "rank": 3},
                ],
                "outcome_probabilities": {
                    "team_a_win": 0.45,
                    "draw": 0.28,
                    "team_b_win": 0.27,
                },
                "btts_probability": 0.48,
                "over_2_5_probability": 0.43,
                "team_goal_probabilities": {
                    "team_a": {"ge_1": 0.70, "ge_2": 0.34, "ge_3": 0.12},
                    "team_b": {"ge_1": 0.61, "ge_2": 0.25, "ge_3": 0.07},
                },
                "clean_sheet_probabilities": {
                    "team_a_clean_sheet": 0.39,
                    "team_b_clean_sheet": 0.30,
                },
                "overflow_probability": 0.01,
            },
            "sanger": {
                "status": "unavailable",
                "model_id": "",
                "formula_ref": "",
                "team_a_lambda_delta": 0,
                "team_b_lambda_delta": 0,
                "confidence": "unknown",
                "source_ids": [],
                "reason": "未配置桑格公式或来源",
            },
            "calibration_flags": {
                "top_score_gate_n": 10,
                "primary_score_outside_top_n": False,
                "btts_conflict": False,
                "over_2_5_conflict": False,
                "strong_third_goal_conflict": False,
                "clean_sheet_conflict": False,
                "lambda_delta_flag": False,
            },
        },
        "market_calibration": {
            "market_signal": "balanced",
            "favorite_handicap": 1.0,
            "goal_line": 2.5,
            "btts_market": "medium",
            "model_vs_market_gap": "aligned",
            "calibration_action": "维持模型判断",
            "source_ids": ["s3"],
            "odds_snapshots": [
                {
                    "captured_at": "2026-06-18T10:00:00Z",
                    "minutes_before_kickoff": 120,
                    "market_type": "handicap",
                    "value": "team_a -1.0",
                    "source_ids": ["s3"],
                },
                {
                    "captured_at": "2026-06-18T11:00:00Z",
                    "minutes_before_kickoff": 60,
                    "market_type": "handicap",
                    "value": "team_a -1.0",
                    "source_ids": ["s3"],
                },
            ],
            "late_market_watch": {
                "status": "pass",
                "checked_window_minutes": 120,
                "abnormal_movement": False,
                "movement_summary": "赛前两小时内让球和大小球未出现异常跳动",
                "action": "维持模型判断",
            },
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
            "quant_baseline_gate": {
                "status": "pass",
                "original_level": "aligned",
                "final_level": "aligned",
                "top_score_gate_n": 10,
                "action": "量化基线与主路径一致",
                "reason": "首选比分在泊松Top-N内，且BTTS/大球/零封无明显冲突",
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
            "score_orientation": {
                "order": "team_a_team_b",
                "team_a": "A队",
                "team_b": "B队",
                "favorite_side": "team_a",
                "primary_score": {
                    "team_a_goals": 1,
                    "team_b_goals": 0,
                },
                "score_label": "A队 1-0 B队",
            },
            "confidence": "medium",
        },
    }


class ValidatorRegressionTests(unittest.TestCase):
    def test_valid_analysis_passes(self):
        errors, _ = validator.validate_analysis(CATALOG, build_analysis())
        self.assertEqual([], errors)

    def test_missing_quant_baseline_is_rejected(self):
        analysis = build_analysis()
        del analysis["quant_baseline"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("quant_baseline 必须是对象" in error for error in errors))

    def test_sanger_delta_limit_is_rejected(self):
        analysis = build_analysis()
        analysis["quant_baseline"]["sanger"] = {
            "status": "computed",
            "model_id": "sanger-custom",
            "formula_ref": "manual:future-formula",
            "team_a_lambda_delta": 0.36,
            "team_b_lambda_delta": 0,
            "confidence": "medium",
            "source_ids": ["s3"],
        }
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("桑格" in error and "0.35" in error for error in errors))

    def test_quant_baseline_score_deviation_requires_gate_resolution(self):
        analysis = build_analysis()
        analysis["quant_baseline"]["poisson"]["top_scores"] = [
            {"score": "2-0", "probability": 0.16, "rank": 1},
            {"score": "2-1", "probability": 0.13, "rank": 2},
        ]
        analysis["quant_baseline"]["calibration_flags"]["primary_score_outside_top_n"] = True
        analysis["prediction_gates"]["quant_baseline_gate"]["status"] = "pass"
        analysis["prediction_gates"]["quant_baseline_gate"]["action"] = "维持量化基线"
        analysis["prediction_gates"]["quant_baseline_gate"]["reason"] = "没有偏差"
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("quant_baseline_gate" in error and "偏离" in error for error in errors))

    def test_quant_baseline_score_deviation_can_be_rejected_with_reason(self):
        analysis = build_analysis()
        analysis["quant_baseline"]["poisson"]["top_scores"] = [
            {"score": "2-0", "probability": 0.16, "rank": 1},
            {"score": "2-1", "probability": 0.13, "rank": 2},
        ]
        analysis["quant_baseline"]["calibration_flags"]["primary_score_outside_top_n"] = True
        analysis["prediction_gates"]["quant_baseline_gate"]["status"] = "rejected"
        analysis["prediction_gates"]["quant_baseline_gate"]["action"] = "拒绝量化首选，保留合议比分"
        analysis["prediction_gates"]["quant_baseline_gate"]["reason"] = "当前阵容和低位闸门支持1-0，量化模型低估0-0/1-0闷局。"
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertFalse(any("quant_baseline_gate" in error and "偏离" in error for error in errors))

    def test_btts_conflict_requires_quant_gate_action(self):
        analysis = build_analysis()
        analysis["final_prediction"]["both_teams_to_score"] = "high"
        analysis["quant_baseline"]["poisson"]["btts_probability"] = 0.38
        analysis["quant_baseline"]["calibration_flags"]["btts_conflict"] = True
        analysis["prediction_gates"]["quant_baseline_gate"]["status"] = "pass"
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("BTTS" in error and "quant_baseline_gate" in error for error in errors))

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
        analysis["review_metadata"]["agent_execution"]["runs"] = [
            run
            for run in analysis["review_metadata"]["agent_execution"]["runs"]
            if run["role_id"] != "skeptic_agent"
        ]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("缺少必需角色" in error for error in errors))

    def test_missing_independent_agent_execution_is_rejected(self):
        analysis = build_analysis()
        del analysis["review_metadata"]["agent_execution"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("agent_execution 必须记录真实独立子 Agent 运行" in error for error in errors))

    def test_reused_agent_run_id_is_rejected(self):
        analysis = build_analysis()
        runs = analysis["review_metadata"]["agent_execution"]["runs"]
        runs[1]["agent_run_id"] = runs[0]["agent_run_id"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("agent_run_id 必须彼此独立" in error for error in errors))

    def test_handwritten_agent_run_id_is_rejected(self):
        analysis = build_analysis()
        analysis["review_metadata"]["agent_execution"]["runs"][0]["agent_run_id"] = "agent-run-1"
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("agent_run_id 格式不像真实子 Agent ID" in error for error in errors))

    def test_missing_agent_artifact_is_rejected(self):
        analysis = build_analysis()
        analysis["review_metadata"]["agent_execution"]["runs"][0]["artifact_ref"] = "tests/fixtures/agent_runs/missing.json"
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("artifact_ref 文件不存在" in error for error in errors))

    def test_bad_agent_artifact_hash_is_rejected(self):
        analysis = build_analysis()
        analysis["review_metadata"]["agent_execution"]["runs"][0]["summary_hash"] = "sha256:" + "0" * 64
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("summary_hash 与 artifact_ref 内容不一致" in error for error in errors))

    def test_non_whitelisted_multi_agent_tooling_is_rejected(self):
        analysis = build_analysis()
        analysis["review_metadata"]["agent_execution"]["tooling"] = "manual_role_play"
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("tooling 必须是白名单工具" in error for error in errors))

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

    def test_missing_dynamic_weighting_is_rejected(self):
        analysis = build_analysis()
        del analysis["dynamic_weighting"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("dynamic_weighting 必须是对象" in error for error in errors))

    def test_extreme_heat_requires_environment_weight_adjustment(self):
        analysis = build_analysis()
        analysis["dynamic_weighting"]["context"]["temperature_c"] = 39
        analysis["dynamic_weighting"]["adjustments"] = [
            item
            for item in analysis["dynamic_weighting"]["adjustments"]
            if item["dimension_key"] != "environment_schedule"
        ]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("高温" in error for error in errors))

    def test_missing_late_market_snapshots_are_rejected(self):
        analysis = build_analysis()
        analysis["market_calibration"]["odds_snapshots"] = []
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("odds_snapshots" in error for error in errors))

    def test_missing_player_advanced_metrics_is_rejected(self):
        analysis = build_analysis()
        del analysis["player_assessments"]["team_a"][0]["advanced_metrics"]
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("advanced_metrics" in error for error in errors))

    def test_score_orientation_must_match_primary_score(self):
        analysis = build_analysis()
        analysis["final_prediction"]["score_orientation"]["primary_score"]["team_a_goals"] = 0
        errors, _ = validator.validate_analysis(CATALOG, analysis)
        self.assertTrue(any("score_orientation" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
