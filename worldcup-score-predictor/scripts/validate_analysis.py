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

    errors.extend(validate_review_metadata(catalog, analysis.get("review_metadata")))
    errors.extend(validate_prediction_gates(catalog, analysis))
    errors.extend(validate_weak_goal_gate(catalog, analysis))
    errors.extend(validate_market_calibration(catalog, analysis))
    errors.extend(validate_score_distribution(catalog, analysis))
    errors.extend(validate_prediction_consistency(catalog, analysis))
    errors.extend(validate_tail_scenarios(catalog, analysis))
    errors.extend(validate_high_confidence_sources(catalog, analysis, known_source_ids))
    errors.extend(validate_final_prediction(catalog, analysis.get("final_prediction")))
    return errors, warnings


def validate_review_metadata(catalog: dict[str, Any], metadata: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(metadata, dict):
        return ["review_metadata 必须是对象，赛前预测必须保留多 Agent 合议轨迹"]

    rules = catalog.get("discussion_quality_rules", {})
    assignments = catalog.get("dimension_review_assignments", {})
    required_roles = set(rules.get("required_roles", []))
    known_dimensions = {item["key"] for item in catalog.get("dimensions", [])}

    mode = metadata.get("mode")
    required_mode = rules.get("required_mode")
    if required_mode and mode != required_mode:
        errors.append(f"review_metadata.mode 必须是 {required_mode}")

    roles = metadata.get("role_results_used")
    if not isinstance(roles, list) or not all(nonempty_text(role) for role in roles):
        errors.append("review_metadata.role_results_used 必须是非空字符串数组")
        roles = []
    role_set = set(roles)
    minimum_agents = rules.get("minimum_agents", 0)
    if len(role_set) < minimum_agents:
        errors.append(f"review_metadata.role_results_used 至少需要{minimum_agents}个不同角色")
    missing_roles = sorted(required_roles - role_set)
    if missing_roles:
        errors.append("review_metadata.role_results_used 缺少必需角色: " + ", ".join(missing_roles))

    primary = metadata.get("primary_dimension_owners")
    expected_primary = assignments.get("primary", {})
    if not isinstance(primary, dict):
        errors.append("review_metadata.primary_dimension_owners 必须是对象")
        primary = {}
    missing_primary = sorted(set(expected_primary) - set(primary))
    extra_primary = sorted(set(primary) - known_dimensions)
    if missing_primary:
        errors.append("review_metadata.primary_dimension_owners 缺少维度: " + ", ".join(missing_primary))
    if extra_primary:
        errors.append("review_metadata.primary_dimension_owners 存在未知维度: " + ", ".join(extra_primary))
    for dimension_key, expected_role in expected_primary.items():
        actual_role = primary.get(dimension_key)
        if actual_role and actual_role != expected_role:
            errors.append(
                f"review_metadata.primary_dimension_owners.{dimension_key} 应为 {expected_role}"
            )
        if actual_role and actual_role not in role_set:
            errors.append(
                f"review_metadata.primary_dimension_owners.{dimension_key} 引用了未参与角色 {actual_role}"
            )

    review = metadata.get("review_dimension_owners")
    expected_review = assignments.get("review", {})
    if not isinstance(review, dict):
        errors.append("review_metadata.review_dimension_owners 必须是对象")
        review = {}
    missing_review = sorted(set(expected_review) - set(review))
    extra_review = sorted(set(review) - known_dimensions)
    if missing_review:
        errors.append("review_metadata.review_dimension_owners 缺少维度: " + ", ".join(missing_review))
    if extra_review:
        errors.append("review_metadata.review_dimension_owners 存在未知维度: " + ", ".join(extra_review))
    for dimension_key, expected_roles in expected_review.items():
        actual_roles = review.get(dimension_key)
        if not isinstance(actual_roles, list) or not actual_roles:
            errors.append(f"review_metadata.review_dimension_owners.{dimension_key} 必须是非空数组")
            continue
        missing_expected = sorted(set(expected_roles) - set(actual_roles))
        if missing_expected:
            errors.append(
                f"review_metadata.review_dimension_owners.{dimension_key} 缺少复核角色: "
                + ", ".join(missing_expected)
            )
        unknown_roles = sorted(set(actual_roles) - role_set)
        if unknown_roles:
            errors.append(
                f"review_metadata.review_dimension_owners.{dimension_key} 引用了未参与角色: "
                + ", ".join(unknown_roles)
            )

    conflicts = metadata.get("conflicts_resolved")
    if not isinstance(conflicts, list):
        errors.append("review_metadata.conflicts_resolved 必须是数组")
        conflicts = []
    minimum_conflicts = rules.get("minimum_resolved_conflicts", 0)
    if len(conflicts) < minimum_conflicts:
        errors.append(f"review_metadata.conflicts_resolved 至少需要{minimum_conflicts}条已裁决分歧")
    conflict_ids: list[str] = []
    required_conflict_fields = set(rules.get("required_conflict_fields", []))
    for index, conflict in enumerate(conflicts):
        prefix = f"review_metadata.conflicts_resolved[{index}]"
        if not isinstance(conflict, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        missing_fields = sorted(required_conflict_fields - set(conflict))
        if missing_fields:
            errors.append(f"{prefix} 缺少字段 {missing_fields}")
        issue_id = conflict.get("issue_id")
        if nonempty_text(issue_id):
            conflict_ids.append(issue_id)
        else:
            errors.append(f"{prefix}.issue_id 不能为空")
        affected_dimensions = conflict.get("affected_dimensions")
        if not isinstance(affected_dimensions, list) or not affected_dimensions:
            errors.append(f"{prefix}.affected_dimensions 必须是非空数组")
        else:
            unknown_affected = sorted(set(affected_dimensions) - known_dimensions)
            if unknown_affected:
                errors.append(f"{prefix}.affected_dimensions 存在未知维度: " + ", ".join(unknown_affected))
        positions = conflict.get("positions")
        if not isinstance(positions, list) or len(positions) < 2:
            errors.append(f"{prefix}.positions 至少需要两个立场")
        else:
            position_roles = []
            for pos_index, position in enumerate(positions):
                pos_prefix = f"{prefix}.positions[{pos_index}]"
                if not isinstance(position, dict):
                    errors.append(f"{pos_prefix} 必须是对象")
                    continue
                role_id = position.get("role_id")
                if not nonempty_text(role_id):
                    errors.append(f"{pos_prefix}.role_id 不能为空")
                elif role_id not in role_set:
                    errors.append(f"{pos_prefix}.role_id 引用了未参与角色 {role_id}")
                else:
                    position_roles.append(role_id)
                if not nonempty_text(position.get("position")) and not nonempty_text(position.get("objection")):
                    errors.append(f"{pos_prefix} 必须包含 position 或 objection")
            if len(set(position_roles)) < 2:
                errors.append(f"{prefix}.positions 必须来自至少两个不同角色")
        if not nonempty_text(conflict.get("resolution")):
            errors.append(f"{prefix}.resolution 不能为空")
        if not nonempty_text(conflict.get("confidence_change")):
            errors.append(f"{prefix}.confidence_change 不能为空")
    duplicates = sorted({issue_id for issue_id in conflict_ids if conflict_ids.count(issue_id) > 1})
    if duplicates:
        errors.append("review_metadata.conflicts_resolved issue_id 重复: " + ", ".join(duplicates))

    rejected = metadata.get("claims_rejected")
    if not isinstance(rejected, list):
        errors.append("review_metadata.claims_rejected 必须是数组")
        rejected = []
    required_rejected_fields = set(rules.get("required_rejected_claim_fields", []))
    for index, claim in enumerate(rejected):
        prefix = f"review_metadata.claims_rejected[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        missing_fields = sorted(required_rejected_fields - set(claim))
        if missing_fields:
            errors.append(f"{prefix} 缺少字段 {missing_fields}")
        role_id = claim.get("role_id")
        if nonempty_text(role_id) and role_id not in role_set:
            errors.append(f"{prefix}.role_id 引用了未参与角色 {role_id}")
        for field in required_rejected_fields:
            if not nonempty_text(claim.get(field)):
                errors.append(f"{prefix}.{field} 不能为空")

    unknown_rationale = metadata.get("unknown_rationale")
    if not isinstance(unknown_rationale, list):
        errors.append("review_metadata.unknown_rationale 必须是数组")
    return errors


def validate_high_confidence_sources(
    catalog: dict[str, Any],
    analysis: dict[str, Any],
    known_source_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    rules = catalog.get("source_quality_rules", {})
    if not rules.get("high_confidence_requires_multiple_sources"):
        return errors

    minimum_sources = rules.get("minimum_sources_for_high_confidence", 2)
    social_types = set(rules.get("social_media_source_types", []))
    source_types: dict[str, str] = {}
    for source in analysis.get("sources", []):
        if isinstance(source, dict) and nonempty_text(source.get("source_id")):
            source_type = source.get("source_type")
            if nonempty_text(source_type):
                source_types[source["source_id"]] = source_type

    for entry in analysis.get("dimension_analyses", []):
        if not isinstance(entry, dict) or entry.get("confidence") != "high":
            continue
        key = entry.get("dimension_key", "<unknown>")
        source_ids = [
            source_id
            for source_id in entry.get("source_ids", [])
            if source_id in known_source_ids
        ]
        if len(set(source_ids)) < minimum_sources:
            errors.append(
                f"{key}: high confidence 至少需要{minimum_sources}个有效来源"
            )
        typed_sources = [source_types[source_id] for source_id in source_ids if source_id in source_types]
        if typed_sources and all(source_type in social_types for source_type in typed_sources):
            errors.append(f"{key}: 社媒来源不得单独支撑 high confidence")
    return errors


def probability_level(value: Any) -> str | None:
    return value if value in {"high", "medium", "low"} else None


def score_total(score: str) -> int | None:
    match = SCORE_RE.fullmatch(score) if isinstance(score, str) else None
    if not match:
        return None
    return int(match.group(1)) + int(match.group(2))


def score_margin_abs(score: str) -> int | None:
    match = SCORE_RE.fullmatch(score) if isinstance(score, str) else None
    if not match:
        return None
    return abs(int(match.group(1)) - int(match.group(2)))


def score_from_item(item: Any) -> str | None:
    if isinstance(item, str) and SCORE_RE.fullmatch(item):
        return item
    if isinstance(item, dict):
        score = item.get("score")
        if isinstance(score, str) and SCORE_RE.fullmatch(score):
            return score
    return None


def validate_prediction_gates(catalog: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rules = catalog.get("prediction_gate_rules", {})
    required_gates = rules.get("required_gates", [])
    gates = analysis.get("prediction_gates")
    if not isinstance(gates, dict):
        return ["prediction_gates 必须是对象，并记录赛前校准闸门"]

    for gate_name in required_gates:
        gate = gates.get(gate_name)
        if not isinstance(gate, dict):
            errors.append(f"prediction_gates.{gate_name} 必须是对象")
            continue
        status = gate.get("status")
        if status not in {"pass", "adjusted", "rejected", "not_applicable"}:
            errors.append(f"prediction_gates.{gate_name}.status 必须是 pass、adjusted、rejected 或 not_applicable")
        if status != "not_applicable":
            if not nonempty_text(gate.get("action")):
                errors.append(f"prediction_gates.{gate_name}.action 不能为空")
            if not nonempty_text(gate.get("reason")):
                errors.append(f"prediction_gates.{gate_name}.reason 不能为空")

    prediction = analysis.get("final_prediction", {})
    weak_level = prediction.get("weak_first_goal") if isinstance(prediction, dict) else None
    clean_level = prediction.get("clean_sheet") if isinstance(prediction, dict) else None
    clean_gate = gates.get("clean_sheet_gate", {})
    if clean_level in {"medium", "high"} and weak_level in {"medium", "high"}:
        if not isinstance(clean_gate, dict) or clean_gate.get("conflict_resolved") is not True:
            errors.append("clean_sheet_gate: 零封与弱队进球同时为 medium/high 时必须显式裁决冲突")

    low_block_gate = gates.get("low_block_draw_gate", {})
    if isinstance(low_block_gate, dict) and low_block_gate.get("low_block_risk") in {"medium", "high"}:
        selected = low_block_gate.get("selected_score")
        if selected not in {"0-0", "1-0", "0-1", "1-1"}:
            errors.append("low_block_draw_gate: 低位闷局风险为 medium/high 时必须选择 0-0、1-0、0-1 或 1-1")

    tail_gate = gates.get("tail_score_gate", {})
    if isinstance(tail_gate, dict):
        checked = tail_gate.get("tail_scores_checked")
        if not isinstance(checked, list) or not checked:
            errors.append("tail_score_gate.tail_scores_checked 至少需要记录一个已检查尾部比分")
    return errors


def validate_weak_goal_gate(catalog: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rules = catalog.get("prediction_gate_rules", {})
    prediction = analysis.get("final_prediction")
    gates = analysis.get("prediction_gates")
    if not isinstance(prediction, dict) or not isinstance(gates, dict):
        return errors

    weak_level = prediction.get("weak_first_goal")
    btts_level = prediction.get("both_teams_to_score")
    weak_gate = gates.get("weak_goal_gate")
    if weak_level in {"medium", "high"} or btts_level in {"medium", "high"}:
        paths = weak_gate.get("independent_paths") if isinstance(weak_gate, dict) else None
        required_paths = rules.get("minimum_weak_goal_paths_for_medium", 2)
        if not isinstance(paths, list) or len([p for p in paths if nonempty_text(p)]) < required_paths:
            errors.append(
                f"weak_goal_gate: 弱队第一球或双方进球为 medium/high 时至少需要{required_paths}条独立进球路径"
            )
    return errors


def validate_market_calibration(catalog: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rules = catalog.get("prediction_gate_rules", {})
    market = analysis.get("market_calibration")
    if not isinstance(market, dict):
        return ["market_calibration 必须是对象"]

    required_text_fields = ["market_signal", "model_vs_market_gap", "calibration_action"]
    for field in required_text_fields:
        if not nonempty_text(market.get(field)):
            errors.append(f"market_calibration.{field} 不能为空")
    source_ids = market.get("source_ids")
    if not isinstance(source_ids, list):
        errors.append("market_calibration.source_ids 必须是数组")

    handicap = market.get("favorite_handicap")
    prediction = analysis.get("final_prediction", {})
    deep_threshold = rules.get("deep_market_handicap_threshold", 1.5)
    deep_market = (
        isinstance(handicap, (int, float))
        and not isinstance(handicap, bool)
        and abs(handicap) >= deep_threshold
    ) or market.get("market_signal") in {"favorite_big_win", "deep_favorite"}
    if deep_market and isinstance(prediction, dict):
        strong_third = prediction.get("strong_third_goal")
        all_scores = []
        all_scores.extend(prediction.get("main_score_range", []) if isinstance(prediction.get("main_score_range"), list) else [])
        all_scores.extend(prediction.get("alternative_scores", []) if isinstance(prediction.get("alternative_scores"), list) else [])
        all_scores.extend(prediction.get("tail_scores", []) if isinstance(prediction.get("tail_scores"), list) else [])
        has_three_goal_margin = any(
            margin is not None and margin >= 3
            for margin in (score_margin_abs(score) for score in all_scores)
        )
        if strong_third == "low":
            errors.append("market_calibration_gate: 深盘或大胜市场信号下 strong_third_goal 不能为 low")
        if not has_three_goal_margin:
            errors.append("market_calibration_gate: 深盘或大胜市场信号下必须保留至少一个净胜3球以上比分")
    return errors


def validate_score_distribution(catalog: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rules = catalog.get("prediction_gate_rules", {})
    distribution = analysis.get("score_distribution")
    if not isinstance(distribution, dict):
        return ["score_distribution 必须是对象"]

    for field in rules.get("required_score_distribution_fields", []):
        value = distribution.get(field)
        if not isinstance(value, list) or not value:
            errors.append(f"score_distribution.{field} 必须是非空数组")

    main_paths = distribution.get("main_paths", [])
    if isinstance(main_paths, list):
        min_main = rules.get("minimum_main_path_scores", 2)
        max_main = rules.get("maximum_main_path_scores", 3)
        if not min_main <= len(main_paths) <= max_main:
            errors.append(f"score_distribution.main_paths 必须包含{min_main}至{max_main}个比分")
        for index, item in enumerate(main_paths):
            score = score_from_item(item)
            if score is None:
                errors.append(f"score_distribution.main_paths[{index}] 必须包含 N-N 格式比分")
            if isinstance(item, dict) and not nonempty_text(item.get("condition")):
                errors.append(f"score_distribution.main_paths[{index}].condition 不能为空")

    low_block_paths = distribution.get("low_block_paths", [])
    if isinstance(low_block_paths, list) and not any(
        score_from_item(item) in {"0-0", "1-0", "0-1", "1-1"} for item in low_block_paths
    ):
        errors.append("score_distribution.low_block_paths 必须判断 0-0、1-0、0-1 或 1-1 中至少一个比分")

    big_win_paths = distribution.get("big_win_paths", [])
    if isinstance(big_win_paths, list) and not any(
        (score_margin_abs(score_from_item(item) or "") or 0) >= 3 for item in big_win_paths
    ):
        errors.append("score_distribution.big_win_paths 必须包含至少一个净胜3球以上比分或明确的大胜尾部")

    btts_paths = distribution.get("btts_paths", [])
    if isinstance(btts_paths, list):
        for index, item in enumerate(btts_paths):
            if not isinstance(item, dict):
                errors.append(f"score_distribution.btts_paths[{index}] 必须是对象")
                continue
            if item.get("status") not in {"pass", "rejected", "adjusted"}:
                errors.append(f"score_distribution.btts_paths[{index}].status 必须是 pass、rejected 或 adjusted")
            if not nonempty_text(item.get("reason")):
                errors.append(f"score_distribution.btts_paths[{index}].reason 不能为空")
    return errors


def validate_prediction_consistency(catalog: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    prediction = analysis.get("final_prediction")
    distribution = analysis.get("score_distribution")
    gates = analysis.get("prediction_gates")
    if not isinstance(prediction, dict) or not isinstance(distribution, dict) or not isinstance(gates, dict):
        return errors

    main_scores = {score_from_item(item) for item in distribution.get("main_paths", [])}
    main_scores.discard(None)
    primary = prediction.get("primary_score")
    alternatives = prediction.get("alternative_scores", [])
    if isinstance(primary, str) and primary not in main_scores:
        errors.append("score_distribution.main_paths 必须包含 final_prediction.primary_score")
    if isinstance(alternatives, list):
        missing_alts = [score for score in alternatives if score not in main_scores]
        if missing_alts:
            errors.append("score_distribution.main_paths 必须覆盖次选比分: " + ", ".join(missing_alts))

    weak_level = prediction.get("weak_first_goal")
    btts_level = prediction.get("both_teams_to_score")
    weak_gate = gates.get("weak_goal_gate", {})
    if weak_level == "low" and btts_level in {"medium", "high"}:
        errors.append("final_prediction: weak_first_goal 为 low 时 both_teams_to_score 不得为 medium/high")
    if isinstance(weak_gate, dict) and weak_gate.get("final_level") == "low" and weak_level in {"medium", "high"}:
        errors.append("weak_goal_gate.final_level 为 low 时 final_prediction.weak_first_goal 不得为 medium/high")

    clean_level = prediction.get("clean_sheet")
    if clean_level == "high" and btts_level == "high":
        errors.append("final_prediction: clean_sheet 和 both_teams_to_score 不得同时为 high")
    return errors


def validate_tail_scenarios(catalog: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rules = catalog.get("prediction_gate_rules", {})
    scenarios = analysis.get("tail_scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return ["tail_scenarios 必须是非空数组"]

    required_types = set(rules.get("required_tail_scenario_types", []))
    seen_types: set[str] = set()
    for index, scenario in enumerate(scenarios):
        prefix = f"tail_scenarios[{index}]"
        if not isinstance(scenario, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        scenario_type = scenario.get("scenario_type")
        if nonempty_text(scenario_type):
            seen_types.add(scenario_type)
        else:
            errors.append(f"{prefix}.scenario_type 不能为空")
        score = scenario.get("score")
        if not isinstance(score, str) or not SCORE_RE.fullmatch(score):
            errors.append(f"{prefix}.score 必须采用 N-N 格式")
        if scenario.get("status") not in {"main", "tail", "rejected"}:
            errors.append(f"{prefix}.status 必须是 main、tail 或 rejected")
        if not nonempty_text(scenario.get("condition")):
            errors.append(f"{prefix}.condition 不能为空")
    missing_types = sorted(required_types - seen_types)
    if missing_types:
        errors.append("tail_scenarios 缺少类型: " + ", ".join(missing_types))
    return errors


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
