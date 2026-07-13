#!/usr/bin/env python3
"""生成赛前量化基线：xG/进球率 -> 双泊松比分分布。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


MIN_LAMBDA = 0.15
MAX_LAMBDA = 4.00
MAX_SANGER_DELTA = 0.35
DEFAULT_MAX_GOALS = 7


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def nonnegative_number(value: Any) -> bool:
    return finite_number(value) and value >= 0


def clamp(value: float, minimum: float = MIN_LAMBDA, maximum: float = MAX_LAMBDA) -> float:
    return max(minimum, min(maximum, value))


def rounded(value: float) -> float:
    return round(value, 6)


def sqrt_product(first: Any, second: Any) -> float | None:
    if not nonnegative_number(first) or not nonnegative_number(second):
        return None
    return math.sqrt(float(first) * float(second))


def poisson_pmf(lambda_value: float, max_goals: int) -> list[float]:
    return [
        math.exp(-lambda_value) * (lambda_value**goals) / math.factorial(goals)
        for goals in range(max_goals + 1)
    ]


def probability_at_least(lambda_value: float, threshold: int) -> float:
    lower_tail = sum(
        math.exp(-lambda_value) * (lambda_value**goals) / math.factorial(goals)
        for goals in range(threshold)
    )
    return max(0.0, min(1.0, 1.0 - lower_tail))


def poisson_summary(team_a_lambda: float, team_b_lambda: float, max_goals: int = DEFAULT_MAX_GOALS) -> dict[str, Any]:
    team_a_probs = poisson_pmf(team_a_lambda, max_goals)
    team_b_probs = poisson_pmf(team_b_lambda, max_goals)
    score_cells: list[dict[str, Any]] = []
    outcome = {"team_a_win": 0.0, "draw": 0.0, "team_b_win": 0.0}
    btts = 0.0
    over_2_5 = 0.0
    matrix_probability = 0.0

    for goals_a, prob_a in enumerate(team_a_probs):
        for goals_b, prob_b in enumerate(team_b_probs):
            probability = prob_a * prob_b
            matrix_probability += probability
            if goals_a > goals_b:
                outcome["team_a_win"] += probability
            elif goals_a == goals_b:
                outcome["draw"] += probability
            else:
                outcome["team_b_win"] += probability
            if goals_a >= 1 and goals_b >= 1:
                btts += probability
            if goals_a + goals_b >= 3:
                over_2_5 += probability
            score_cells.append(
                {
                    "score": f"{goals_a}-{goals_b}",
                    "probability": probability,
                    "team_a_goals": goals_a,
                    "team_b_goals": goals_b,
                }
            )

    score_cells.sort(
        key=lambda item: (
            -item["probability"],
            -(item["team_a_goals"] + item["team_b_goals"]),
            item["team_a_goals"],
            item["team_b_goals"],
        )
    )
    top_scores = [
        {
            "score": item["score"],
            "probability": rounded(item["probability"]),
            "rank": index,
        }
        for index, item in enumerate(score_cells[:10], start=1)
    ]
    return {
        "max_goals": max_goals,
        "top_scores": top_scores,
        "outcome_probabilities": {key: rounded(value) for key, value in outcome.items()},
        "btts_probability": rounded(btts),
        "over_2_5_probability": rounded(over_2_5),
        "team_goal_probabilities": {
            "team_a": {
                "ge_1": rounded(probability_at_least(team_a_lambda, 1)),
                "ge_2": rounded(probability_at_least(team_a_lambda, 2)),
                "ge_3": rounded(probability_at_least(team_a_lambda, 3)),
            },
            "team_b": {
                "ge_1": rounded(probability_at_least(team_b_lambda, 1)),
                "ge_2": rounded(probability_at_least(team_b_lambda, 2)),
                "ge_3": rounded(probability_at_least(team_b_lambda, 3)),
            },
        },
        "clean_sheet_probabilities": {
            "team_a_clean_sheet": rounded(math.exp(-team_b_lambda)),
            "team_b_clean_sheet": rounded(math.exp(-team_a_lambda)),
        },
        "overflow_probability": rounded(max(0.0, 1.0 - matrix_probability)),
    }


def extract_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("quant_baseline_inputs"), dict):
        return payload["quant_baseline_inputs"]
    if isinstance(payload.get("match_evidence_pack"), dict):
        pack = payload["match_evidence_pack"]
    else:
        pack = payload
    if isinstance(pack.get("quant_baseline_inputs"), dict):
        return pack["quant_baseline_inputs"]
    facts = pack.get("facts") if isinstance(pack, dict) else None
    if isinstance(facts, dict) and isinstance(facts.get("quant_baseline_inputs"), dict):
        return facts["quant_baseline_inputs"]
    return {}


def normalize_sanger(raw_sanger: Any) -> dict[str, Any]:
    if not isinstance(raw_sanger, dict) or raw_sanger.get("status") != "computed":
        return {
            "status": "unavailable",
            "model_id": "",
            "formula_ref": "",
            "team_a_lambda_delta": 0,
            "team_b_lambda_delta": 0,
            "confidence": "unknown",
            "source_ids": [],
            "reason": "未配置桑格公式或来源",
        }

    delta_a = raw_sanger.get("team_a_lambda_delta", 0)
    delta_b = raw_sanger.get("team_b_lambda_delta", 0)
    if not finite_number(delta_a) or not finite_number(delta_b):
        raise ValueError("桑格 lambda delta 必须是数字")
    if abs(float(delta_a)) > MAX_SANGER_DELTA or abs(float(delta_b)) > MAX_SANGER_DELTA:
        raise ValueError(f"桑格 lambda delta 单队绝对值不得超过 {MAX_SANGER_DELTA}")
    return {
        "status": "computed",
        "model_id": str(raw_sanger.get("model_id", "")).strip(),
        "formula_ref": str(raw_sanger.get("formula_ref", "")).strip(),
        "team_a_lambda_delta": rounded(float(delta_a)),
        "team_b_lambda_delta": rounded(float(delta_b)),
        "confidence": raw_sanger.get("confidence", "unknown"),
        "source_ids": raw_sanger.get("source_ids", []),
        "reason": raw_sanger.get("reason", ""),
    }


def build_quant_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    inputs = extract_inputs(payload)
    team_a = inputs.get("team_a", {}) if isinstance(inputs.get("team_a"), dict) else {}
    team_b = inputs.get("team_b", {}) if isinstance(inputs.get("team_b"), dict) else {}
    source_ids = inputs.get("sources") if isinstance(inputs.get("sources"), list) else []
    missing_inputs: list[str] = []

    team_a_xg_component = sqrt_product(team_a.get("xg_for"), team_b.get("xg_against"))
    team_b_xg_component = sqrt_product(team_b.get("xg_for"), team_a.get("xg_against"))
    has_direct_xg = team_a_xg_component is not None and team_b_xg_component is not None

    team_a_goal_component = sqrt_product(team_a.get("goals_for_rate"), team_b.get("goals_against_rate"))
    team_b_goal_component = sqrt_product(team_b.get("goals_for_rate"), team_a.get("goals_against_rate"))
    has_goal_rates = team_a_goal_component is not None and team_b_goal_component is not None

    if has_direct_xg and has_goal_rates:
        base_a = 0.70 * team_a_xg_component + 0.30 * team_a_goal_component
        base_b = 0.70 * team_b_xg_component + 0.30 * team_b_goal_component
        status = "computed"
        xg_status = "direct"
    elif has_direct_xg:
        base_a = team_a_xg_component
        base_b = team_b_xg_component
        status = "computed"
        xg_status = "direct"
        missing_inputs.append("缺少进球/失球率，使用 direct xG/xGA 建立基线")
    elif has_goal_rates:
        base_a = team_a_goal_component
        base_b = team_b_goal_component
        status = "partial"
        xg_status = "unavailable"
        missing_inputs.append("缺少 direct xG/xGA，使用进球率回退基线")
    else:
        base_a = 1.0
        base_b = 1.0
        status = "unavailable"
        xg_status = "unavailable"
        missing_inputs.append("缺少 direct xG/xGA 与进球/失球率，量化基线不可用")

    sanger = normalize_sanger(inputs.get("sanger"))
    final_a = clamp(float(base_a) + float(sanger["team_a_lambda_delta"]))
    final_b = clamp(float(base_b) + float(sanger["team_b_lambda_delta"]))

    return {
        "schema_version": "quant-baseline-1.0",
        "status": status,
        "source_ids": source_ids,
        "missing_inputs": missing_inputs,
        "xg": {
            "status": xg_status,
            "team_a_xg_for": team_a.get("xg_for") if nonnegative_number(team_a.get("xg_for")) else None,
            "team_a_xg_against": team_a.get("xg_against") if nonnegative_number(team_a.get("xg_against")) else None,
            "team_b_xg_for": team_b.get("xg_for") if nonnegative_number(team_b.get("xg_for")) else None,
            "team_b_xg_against": team_b.get("xg_against") if nonnegative_number(team_b.get("xg_against")) else None,
            "source_ids": source_ids if has_direct_xg else [],
            "reason": "" if has_direct_xg else "未提供双方 direct xG/xGA",
        },
        "expected_goals": {
            "team_a_lambda": rounded(final_a),
            "team_b_lambda": rounded(final_b),
            "total_lambda": rounded(final_a + final_b),
            "lambda_components": {
                "team_a": {
                    "xg_component": rounded(team_a_xg_component) if team_a_xg_component is not None else None,
                    "goal_rate_component": rounded(team_a_goal_component) if team_a_goal_component is not None else None,
                    "sanger_delta": sanger["team_a_lambda_delta"],
                    "final_lambda": rounded(final_a),
                },
                "team_b": {
                    "xg_component": rounded(team_b_xg_component) if team_b_xg_component is not None else None,
                    "goal_rate_component": rounded(team_b_goal_component) if team_b_goal_component is not None else None,
                    "sanger_delta": sanger["team_b_lambda_delta"],
                    "final_lambda": rounded(final_b),
                },
            },
        },
        "poisson": poisson_summary(final_a, final_b, DEFAULT_MAX_GOALS),
        "sanger": sanger,
        "calibration_flags": {
            "top_score_gate_n": 10,
            "primary_score_outside_top_n": False,
            "btts_conflict": False,
            "over_2_5_conflict": False,
            "strong_third_goal_conflict": False,
            "clean_sheet_conflict": False,
            "lambda_delta_flag": False,
        },
    }


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("输入文件顶层必须是 JSON 对象")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成量化基线 JSON fragment")
    parser.add_argument("--input", required=True, type=Path, help="Match Evidence Pack 或比赛输入 JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        fragment = {"quant_baseline": build_quant_baseline(load_json(args.input))}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(fragment, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
