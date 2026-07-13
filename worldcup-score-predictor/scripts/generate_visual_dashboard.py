#!/usr/bin/env python3
"""根据结构化预测 JSON 生成轻量 SVG 看板。"""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any


def load_analysis(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("分析文件顶层必须是 JSON 对象")
    return value


def score_entries(analysis: dict[str, Any]) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    for item in analysis.get("dimension_analyses", []):
        if not isinstance(item, dict):
            continue
        key = item.get("dimension_key")
        score = item.get("score")
        if isinstance(key, str) and isinstance(score, int) and not isinstance(score, bool):
            entries.append((key, max(1, min(score, 5))))
    return entries


def polar_point(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def build_radar_svg(analysis: dict[str, Any], width: int = 720, height: int = 720) -> str:
    entries = score_entries(analysis)[:26]
    if not entries:
        entries = [("unknown", 1)]

    cx = width / 2
    cy = height / 2
    radius = min(width, height) * 0.34
    label_radius = radius + 36
    count = len(entries)
    angles = [(-math.pi / 2) + (2 * math.pi * index / count) for index in range(count)]

    grid_parts: list[str] = []
    for level in range(1, 6):
        level_radius = radius * level / 5
        points = [
            "{:.1f},{:.1f}".format(*polar_point(cx, cy, level_radius, angle))
            for angle in angles
        ]
        grid_parts.append(
            f'<polygon points="{" ".join(points)}" fill="none" stroke="#d7dde8" stroke-width="1" />'
        )

    axis_parts: list[str] = []
    label_parts: list[str] = []
    data_points: list[str] = []
    for (label, score), angle in zip(entries, angles):
        axis_x, axis_y = polar_point(cx, cy, radius, angle)
        label_x, label_y = polar_point(cx, cy, label_radius, angle)
        point_x, point_y = polar_point(cx, cy, radius * score / 5, angle)
        anchor = "middle"
        if label_x < cx - 20:
            anchor = "end"
        elif label_x > cx + 20:
            anchor = "start"
        axis_parts.append(
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{axis_x:.1f}" y2="{axis_y:.1f}" stroke="#e6ebf2" />'
        )
        label_parts.append(
            '<text x="{:.1f}" y="{:.1f}" text-anchor="{}" font-size="11" fill="#283142">{}</text>'.format(
                label_x,
                label_y,
                anchor,
                html.escape(label),
            )
        )
        data_points.append(f"{point_x:.1f},{point_y:.1f}")

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#f8fafc" />',
            *grid_parts,
            *axis_parts,
            f'<polygon points="{" ".join(data_points)}" fill="#2563eb" fill-opacity="0.20" stroke="#2563eb" stroke-width="2" />',
            *label_parts,
            "</svg>",
        ]
    )


def percent(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value * 100:.1f}%"
    return "未知"


def quant_baseline_rows(analysis: dict[str, Any], start_y: int = 126) -> list[str]:
    baseline = analysis.get("quant_baseline")
    if not isinstance(baseline, dict):
        return []
    expected = baseline.get("expected_goals", {})
    poisson = baseline.get("poisson", {})
    gates = analysis.get("prediction_gates", {})
    gate = gates.get("quant_baseline_gate", {}) if isinstance(gates, dict) else {}
    if not isinstance(expected, dict) or not isinstance(poisson, dict):
        return []

    lambda_a = expected.get("team_a_lambda", "未知")
    lambda_b = expected.get("team_b_lambda", "未知")
    top_scores: list[str] = []
    for item in poisson.get("top_scores", [])[:5]:
        if not isinstance(item, dict):
            continue
        score = str(item.get("score", ""))
        top_scores.append(f"{score} {percent(item.get('probability'))}")
    gate_status = gate.get("status", "unknown") if isinstance(gate, dict) else "unknown"
    gate_action = gate.get("action", "") if isinstance(gate, dict) else ""
    lines = [
        f"量化基线: λ A={lambda_a} / B={lambda_b} | BTTS {percent(poisson.get('btts_probability'))} | O2.5 {percent(poisson.get('over_2_5_probability'))}",
        "量化Top5: " + (", ".join(top_scores) if top_scores else "未知"),
        f"量化闸门: {gate_status} - {gate_action}",
    ]
    return [
        f'<text x="40" y="{start_y + index * 24}" font-size="14" fill="#283142">{html.escape(line)}</text>'
        for index, line in enumerate(lines)
    ]


def score_path_rows(analysis: dict[str, Any], start_y: int = 150) -> list[str]:
    distribution = analysis.get("score_distribution", {})
    if not isinstance(distribution, dict):
        return []
    rows: list[str] = []
    for group_name, title in (
        ("main_paths", "主路径"),
        ("low_block_paths", "闷局"),
        ("big_win_paths", "大胜"),
        ("btts_paths", "双方进球"),
    ):
        for item in distribution.get(group_name, []):
            if not isinstance(item, dict):
                continue
            score = html.escape(str(item.get("score", "")))
            condition = html.escape(str(item.get("condition") or item.get("reason") or ""))
            rows.append(
                f'<text x="40" y="{start_y + len(rows) * 24}" font-size="14" fill="#283142">{title}: {score} - {condition}</text>'
            )
    return rows


def write_dashboard(analysis: dict[str, Any], output: Path) -> None:
    match = analysis.get("match", {})
    team_a = match.get("team_a", "Team A") if isinstance(match, dict) else "Team A"
    team_b = match.get("team_b", "Team B") if isinstance(match, dict) else "Team B"
    title = f"{team_a} vs {team_b}"
    radar = build_radar_svg(analysis, width=560, height=560)
    quant_rows = quant_baseline_rows(analysis)
    score_rows = score_path_rows(analysis, start_y=220 if quant_rows else 150)
    rows = quant_rows + score_rows
    height = max(720, 240 + len(rows) * 24)
    content = "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}">',
            '<rect width="100%" height="100%" fill="#ffffff" />',
            f'<text x="40" y="56" font-size="28" font-weight="700" fill="#111827">{html.escape(title)}</text>',
            '<text x="40" y="92" font-size="14" fill="#526071">维度雷达图与比分路径摘要</text>',
            '<g transform="translate(360, 80)">',
            radar.replace('<svg xmlns="http://www.w3.org/2000/svg" width="560" height="560" viewBox="0 0 560 560">', '<g>')
            .replace("</svg>", "</g>"),
            "</g>",
            *rows,
            "</svg>",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成世界杯预测 SVG 可视化看板")
    parser.add_argument("analysis", type=Path, help="结构化预测 JSON")
    parser.add_argument("output", type=Path, help="输出 SVG 路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analysis = load_analysis(args.analysis)
    write_dashboard(analysis, args.output)
    print(f"已生成看板: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
