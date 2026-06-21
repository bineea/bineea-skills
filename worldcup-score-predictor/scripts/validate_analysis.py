#!/usr/bin/env python3
"""校验世界杯比分预测是否完整覆盖机器维度清单。"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = SKILL_ROOT / "config" / "dimensions.json"
DEFAULT_CSV = SKILL_ROOT / "seed" / "dimensions.csv"
DEFAULT_DB = SKILL_ROOT / "data" / "worldcup_prediction_knowledge.sqlite"
SCORE_RE = re.compile(r"^(\d+)-(\d+)$")


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须是 JSON 对象")
    return value


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_catalog(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dimensions = catalog.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        return ["维度目录缺少非空 dimensions 数组"]

    keys: list[str] = []
    for index, dimension in enumerate(dimensions):
        prefix = f"dimensions[{index}]"
        if not isinstance(dimension, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        key = dimension.get("key")
        if not nonempty_text(key):
            errors.append(f"{prefix}.key 不能为空")
            continue
        keys.append(key)
        if not nonempty_text(dimension.get("name")):
            errors.append(f"{key}: name 不能为空")
        checks = dimension.get("required_checks")
        if not isinstance(checks, dict) or not checks:
            errors.append(f"{key}: required_checks 必须是非空对象")
        elif any(not nonempty_text(k) or not nonempty_text(v) for k, v in checks.items()):
            errors.append(f"{key}: required_checks 的键和值均不能为空")

    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        errors.append("维度键重复: " + ", ".join(duplicates))
    if len(keys) != 26:
        errors.append(f"机器维度数量应为26，实际为{len(keys)}")
    return errors


def validate_asset_alignment(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    catalog_keys = [item["key"] for item in catalog["dimensions"]]

    if DEFAULT_CSV.exists():
        with DEFAULT_CSV.open(encoding="utf-8-sig", newline="") as handle:
            csv_keys = [row["dimension_key"] for row in csv.DictReader(handle)]
        if csv_keys != catalog_keys:
            errors.append("seed/dimensions.csv 与 config/dimensions.json 的维度顺序或内容不一致")

    if DEFAULT_DB.exists():
        connection = sqlite3.connect(DEFAULT_DB)
        try:
            rows = connection.execute(
                "SELECT dimension_key FROM dimension_catalog ORDER BY rowid"
            ).fetchall()
        finally:
            connection.close()
        db_keys = [row[0] for row in rows]
        if db_keys != catalog_keys:
            errors.append("SQLite dimension_catalog 与 config/dimensions.json 不一致")
    return errors


def validate_check_result(
    dimension_key: str,
    check_key: str,
    result: Any,
    known_source_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    prefix = f"{dimension_key}.{check_key}"
    if not isinstance(result, dict):
        return [f"{prefix}: 检查结果必须是对象"]

    status = result.get("status")
    allowed = {"supported", "contradicted", "neutral", "unknown", "not_applicable"}
    if status not in allowed:
        errors.append(f"{prefix}: status 必须是 {sorted(allowed)} 之一")
    if not nonempty_text(result.get("finding")):
        errors.append(f"{prefix}: finding 不能为空")

    evidence = result.get("evidence")
    source_ids = result.get("source_ids")
    if not isinstance(evidence, list):
        errors.append(f"{prefix}: evidence 必须是数组")
        evidence = []
    if not isinstance(source_ids, list):
        errors.append(f"{prefix}: source_ids 必须是数组")
        source_ids = []

    if status in {"supported", "contradicted", "neutral"} and not any(
        nonempty_text(item) for item in evidence
    ):
        errors.append(f"{prefix}: 已判断的检查项至少需要一条证据")
    if status == "unknown" and not nonempty_text(result.get("finding")):
        errors.append(f"{prefix}: unknown 必须说明未知原因")
    unknown_sources = sorted(
        source_id for source_id in source_ids if source_id not in known_source_ids
    )
    if unknown_sources:
        errors.append(f"{prefix}: 引用了不存在的来源 {unknown_sources}")
    return errors


def validate_analysis(catalog: dict[str, Any], analysis: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required_fields = set(catalog["required_analysis_fields"])
    dimensions = {item["key"]: item for item in catalog["dimensions"] if item.get("required")}

    sources = analysis.get("sources")
    if not isinstance(sources, list):
        errors.append("sources 必须是数组")
        sources = []
    source_ids: list[str] = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or not nonempty_text(source.get("source_id")):
            errors.append(f"sources[{index}].source_id 不能为空")
            continue
        source_ids.append(source["source_id"])
    if len(source_ids) != len(set(source_ids)):
        errors.append("sources 中存在重复 source_id")
    known_source_ids = set(source_ids)

    entries = analysis.get("dimension_analyses")
    if not isinstance(entries, list):
        return errors + ["dimension_analyses 必须是数组"], warnings

    entry_keys = [
        entry.get("dimension_key") for entry in entries if isinstance(entry, dict)
    ]
    duplicates = sorted({key for key in entry_keys if key and entry_keys.count(key) > 1})
    if duplicates:
        errors.append("分析维度重复: " + ", ".join(duplicates))
    missing = sorted(set(dimensions) - set(entry_keys))
    unknown = sorted(set(entry_keys) - set(dimensions))
    if missing:
        errors.append("缺少必选维度: " + ", ".join(missing))
    if unknown:
        errors.append("存在未知维度: " + ", ".join(unknown))

    scored_keys: set[str] = set()
    evidence_signature_counts: dict[tuple[str, ...], list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("dimension_analyses 中的项目必须是对象")
            continue
        key = entry.get("dimension_key")
        if key not in dimensions:
            continue
        absent_fields = sorted(required_fields - set(entry))
        if absent_fields:
            errors.append(f"{key}: 缺少字段 {absent_fields}")
            continue

        score = entry.get("score")
        confidence = entry.get("confidence")
        conclusion = entry.get("conclusion")
        unknown_items = entry.get("unknown_items")
        if confidence not in catalog["confidence_values"]:
            errors.append(f"{key}: confidence 值无效")
        if not nonempty_text(conclusion):
            errors.append(f"{key}: conclusion 不能为空")
        if not isinstance(unknown_items, list):
            errors.append(f"{key}: unknown_items 必须是数组")
            unknown_items = []

        if score is None:
            if confidence != "unknown":
                errors.append(f"{key}: score 为空时 confidence 必须为 unknown")
            if not any(nonempty_text(item) for item in unknown_items):
                errors.append(f"{key}: score 为空时必须在 unknown_items 说明原因")
        elif not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            errors.append(f"{key}: score 必须是1至5的整数或明确未知")
        else:
            scored_keys.add(key)

        checks = entry.get("check_results")
        if not isinstance(checks, dict):
            errors.append(f"{key}: check_results 必须是对象")
            continue
        required_checks = dimensions[key]["required_checks"]
        missing_checks = sorted(set(required_checks) - set(checks))
        extra_checks = sorted(set(checks) - set(required_checks))
        if missing_checks:
            errors.append(f"{key}: 缺少子检查项 {missing_checks}")
        if extra_checks:
            errors.append(f"{key}: 存在未知子检查项 {extra_checks}")
        available_check_keys = set(required_checks) & set(checks)
        for check_key in available_check_keys:
            errors.extend(
                validate_check_result(key, check_key, checks[check_key], known_source_ids)
            )

        judged_finding_cores: list[str] = []
        for check_key in available_check_keys:
            result = checks[check_key]
            if not isinstance(result, dict) or result.get("status") not in {
                "supported", "contradicted", "neutral"
            }:
                continue
            finding = result.get("finding")
            if nonempty_text(finding):
                judged_finding_cores.append(finding.split("：", 1)[-1].strip())
        quality_rules = catalog.get("evidence_quality_rules", {})
        configured_minimum = quality_rules.get(
            "minimum_unique_check_findings_per_dimension", 3
        )
        required_unique = min(configured_minimum, len(judged_finding_cores))
        if required_unique and len(set(judged_finding_cores)) < required_unique:
            errors.append(
                f"{key}: 子检查项发现过度重复；至少需要{required_unique}条针对性结论，"
                f"当前为{len(set(judged_finding_cores))}条"
            )

        entry_evidence = entry.get("evidence")
        if not isinstance(entry_evidence, list):
            errors.append(f"{key}: evidence 必须是数组")
            entry_evidence = []
        if score is not None and not any(nonempty_text(item) for item in entry_evidence):
            errors.append(f"{key}: 已评分维度至少需要一条维度级证据")
        evidence_signature = tuple(
            sorted(item.strip() for item in entry_evidence if nonempty_text(item))
        )
        if evidence_signature:
            evidence_signature_counts.setdefault(evidence_signature, []).append(key)

        entry_source_ids = entry.get("source_ids")
        if not isinstance(entry_source_ids, list):
            errors.append(f"{key}: source_ids 必须是数组")
            entry_source_ids = []
        else:
            invalid_ids = sorted(
                source_id for source_id in entry_source_ids if source_id not in known_source_ids
            )
            if invalid_ids:
                errors.append(f"{key}: 引用了不存在的来源 {invalid_ids}")
        if score is not None and not entry_source_ids and confidence != "unknown":
            errors.append(f"{key}: 已评分维度至少需要一个有效来源")

    maximum_signature_reuse = catalog.get("evidence_quality_rules", {}).get(
        "maximum_identical_dimension_evidence_signatures", 3
    )
    for reused_by in evidence_signature_counts.values():
        if len(reused_by) > maximum_signature_reuse:
            errors.append(
                "维度级证据被机械复用，涉及: " + ", ".join(reused_by)
            )

    minimum_scored = catalog.get("minimum_scored_dimensions", 20)
    if len(scored_keys) < minimum_scored:
        errors.append(
            f"有效评分维度至少需要{minimum_scored}项，当前为{len(scored_keys)}项"
        )
    missing_critical_scores = sorted(
        set(catalog.get("critical_dimension_keys", [])) - scored_keys
    )
    if missing_critical_scores:
        errors.append("核心维度不得未知: " + ", ".join(missing_critical_scores))

    player_assessments = analysis.get("player_assessments", {})
    if not isinstance(player_assessments, dict):
        errors.append("player_assessments 必须是对象")
    else:
        required_player_fields = set(catalog.get("required_player_fields", []))
        for team in ("team_a", "team_b"):
            players = player_assessments.get(team)
            if not isinstance(players, list) or len(players) < 3:
                errors.append(f"player_assessments.{team} 至少需要3名关键球员")
                continue
            for index, player in enumerate(players):
                prefix = f"player_assessments.{team}[{index}]"
                if not isinstance(player, dict):
                    errors.append(f"{prefix} 必须是对象")
                    continue
                missing_player_fields = sorted(required_player_fields - set(player))
                if missing_player_fields:
                    errors.append(f"{prefix} 缺少字段 {missing_player_fields}")
                    continue
                for field in ("player_name", "position", "player_type", "status", "conclusion"):
                    if not nonempty_text(player.get(field)):
                        errors.append(f"{prefix}.{field} 不能为空")
                if not isinstance(player.get("expected_starter"), bool):
                    errors.append(f"{prefix}.expected_starter 必须是布尔值")
                minutes = player.get("expected_minutes")
                if not isinstance(minutes, int) or isinstance(minutes, bool) or not 0 <= minutes <= 120:
                    errors.append(f"{prefix}.expected_minutes 必须是0至120的整数")
                player_evidence = player.get("evidence")
                if not isinstance(player_evidence, list) or not any(
                    nonempty_text(item) for item in player_evidence
                ):
                    errors.append(f"{prefix}.evidence 至少需要一条证据")
                player_sources = player.get("source_ids")
                if not isinstance(player_sources, list) or not player_sources:
                    errors.append(f"{prefix}.source_ids 至少需要一个来源")
                else:
                    invalid_player_sources = sorted(
                        source_id
                        for source_id in player_sources
                        if source_id not in known_source_ids
                    )
                    if invalid_player_sources:
                        errors.append(
                            f"{prefix} 引用了不存在的来源 {invalid_player_sources}"
                        )

    errors.extend(validate_final_prediction(catalog, analysis.get("final_prediction")))
    return errors, warnings


def validate_final_prediction(catalog: dict[str, Any], prediction: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(prediction, dict):
        return ["final_prediction 必须是对象"]
    required = {
        "win_tendency",
        "main_score_range",
        "primary_score",
        "alternative_scores",
        "total_goals_min",
        "total_goals_max",
        "both_teams_to_score",
        "strong_second_goal",
        "strong_third_goal",
        "weak_first_goal",
        "weak_second_goal",
        "clean_sheet",
        "draw_type",
        "trigger_conditions",
        "tail_scores",
        "event_scenarios",
        "confidence",
    }
    missing = sorted(required - set(prediction))
    if missing:
        return [f"final_prediction 缺少字段 {missing}"]

    primary = prediction.get("primary_score")
    match = SCORE_RE.fullmatch(primary) if isinstance(primary, str) else None
    if not match:
        errors.append("final_prediction.primary_score 必须采用 N-N 格式")
    minimum = prediction.get("total_goals_min")
    maximum = prediction.get("total_goals_max")
    if not isinstance(minimum, int) or not isinstance(maximum, int) or minimum > maximum:
        errors.append("总进球上下限必须是有效整数且 min <= max")
    elif match:
        total = int(match.group(1)) + int(match.group(2))
        if not minimum <= total <= maximum:
            errors.append("首选比分总进球数不在预测总进球区间内")

    for field in (
        "both_teams_to_score",
        "strong_second_goal",
        "strong_third_goal",
        "weak_first_goal",
        "weak_second_goal",
        "clean_sheet",
        "confidence",
    ):
        if prediction.get(field) not in {"high", "medium", "low"}:
            errors.append(f"final_prediction.{field} 必须是 high、medium 或 low")
    if not isinstance(prediction.get("trigger_conditions"), list) or len(
        prediction["trigger_conditions"]
    ) < 3:
        errors.append("final_prediction.trigger_conditions 至少需要三项")

    tail_scores = prediction.get("tail_scores")
    if not isinstance(tail_scores, list) or not tail_scores:
        errors.append("final_prediction.tail_scores 至少需要一个极端比分尾部")
    elif any(not isinstance(score, str) or not SCORE_RE.fullmatch(score) for score in tail_scores):
        errors.append("final_prediction.tail_scores 必须全部采用 N-N 格式")
    else:
        regular_scores = {prediction.get("primary_score")}
        regular_scores.update(prediction.get("alternative_scores", []))
        if all(score in regular_scores for score in tail_scores):
            errors.append("极端比分尾部不得与首选和次选比分完全重复")

    scenarios = prediction.get("event_scenarios")
    required_scenarios = set(catalog.get("required_event_scenarios", []))
    if not isinstance(scenarios, dict):
        errors.append("final_prediction.event_scenarios 必须是对象")
    else:
        missing_scenarios = sorted(required_scenarios - set(scenarios))
        if missing_scenarios:
            errors.append(f"event_scenarios 缺少情景 {missing_scenarios}")
        for scenario in required_scenarios & set(scenarios):
            if not nonempty_text(scenarios[scenario]):
                errors.append(f"event_scenarios.{scenario} 不能为空")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验世界杯比分预测结构化分析")
    parser.add_argument("analysis", nargs="?", type=Path, help="逐场分析 JSON 文件")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="维度目录 JSON")
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="只校验维度目录及其与 CSV、SQLite 的一致性",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        catalog = load_json(args.catalog)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误: 无法读取维度目录: {exc}", file=sys.stderr)
        return 2

    errors = validate_catalog(catalog)
    errors.extend(validate_asset_alignment(catalog))
    warnings: list[str] = []

    if not args.catalog_only:
        if args.analysis is None:
            print("错误: 请提供逐场分析 JSON，或使用 --catalog-only", file=sys.stderr)
            return 2
        try:
            analysis = load_json(args.analysis)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"错误: 无法读取逐场分析: {exc}", file=sys.stderr)
            return 2
        analysis_errors, warnings = validate_analysis(catalog, analysis)
        errors.extend(analysis_errors)

    for warning in warnings:
        print(f"警告: {warning}")
    if errors:
        for error in errors:
            print(f"错误: {error}", file=sys.stderr)
        print(f"校验失败: {len(errors)} 个错误，{len(warnings)} 个警告", file=sys.stderr)
        return 1

    print(f"校验通过: 26 个必选维度，{len(warnings)} 个警告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
