#!/usr/bin/env python3
"""根据历史样本和已导入赛后数据生成复盘并同步数据库。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = SKILL_ROOT / "data" / "worldcup_prediction_knowledge.sqlite"
REVIEW_DIR = SKILL_ROOT / "data" / "reviews"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def result_type(score: str) -> str:
    left, right = (int(value) for value in score.split("-", 1))
    return "胜" if left > right else "负" if left < right else "平"


def display(value: object) -> str:
    return "未知" if value is None else str(value)


def build_review(
    match: sqlite3.Row,
    stats: sqlite3.Row,
    sample: sqlite3.Row,
    key_players: list[sqlite3.Row],
) -> tuple[str, list[str], list[str], list[str], list[str]]:
    actual_score = f"{match['actual_score_a']}-{match['actual_score_b']}"
    predicted_score = sample["predicted_score"] or "未知"
    errors = (
        json.loads(sample["error_types_json"])
        if sample["error_types_json"]
        else []
    )
    lessons = (
        json.loads(sample["reusable_lessons_json"])
        if sample["reusable_lessons_json"]
        else []
    )
    tags = json.loads(sample["tags_json"]) if sample["tags_json"] else []
    result_hit = (
        "是" if predicted_score != "未知" and result_type(predicted_score) == result_type(actual_score) else "否"
    )
    btts_hit = "未知"
    if predicted_score != "未知":
        predicted_btts = all(int(value) > 0 for value in predicted_score.split("-", 1))
        actual_btts = match["actual_score_a"] > 0 and match["actual_score_b"] > 0
        btts_hit = "是" if predicted_btts == actual_btts else "否"

    timeline_rows = []
    for row in match["goal_events"]:
        clock = (
            f"{row['minute']}+{row['stoppage_minute']}'"
            if row["stoppage_minute"]
            else f"{row['minute']}'"
        )
        event_text = "乌龙" if row["event_type"] == "own_goal" else "进球"
        timeline_rows.append(f"{clock} {row['team_name']} {row['player_name']}（{event_text}）")
    timeline = "；".join(timeline_rows) or "无可用事件"

    player_rows = []
    for row in key_players:
        player_rows.append(
            "| {player} | {team} | {started} | {minutes} | {goals} | {assists} | "
            "{shots}/{sot} | {own_goals} |".format(
                player=row["player_name"],
                team=row["team_name"],
                started="是" if row["started"] else "否",
                minutes=row["minutes_played"],
                goals=row["goals"] or 0,
                assists=row["assists"] or 0,
                shots=display(row["shots"]),
                sot=display(row["shots_on_target"]),
                own_goals=row["own_goals"] or 0,
            )
        )
    if not player_rows:
        player_rows.append("| 无 |  |  |  |  |  |  |  |")

    failure_reasons = (
        [sample["notes"]] + [f"误差标签：{error}" for error in errors]
        if sample["predicted_score"]
        else ["数据库中没有本场赛前预测，因此只完成事实复盘，不进行预测误差归因。"]
    )
    suggestions = [f"在出现“{tag}”条件时小幅提高相应路径权重。" for tag in tags]
    error_markdown = (
        "\n".join(f"- [x] {error}" for error in errors)
        if errors
        else "- [ ] 无赛前预测，未做误差归因"
    )
    lesson_markdown = (
        "\n".join(
            f"| {lesson} | 在相似阵容和比赛路径下提高对应比分分支权重。 |"
            for lesson in lessons
        )
        if lessons
        else "| 无赛前预测样本 | 本场暂不形成预测权重修正。 |"
    )
    tag_markdown = (
        "\n".join(f"- {tag}" for tag in tags)
        if tags
        else "- 无（缺少赛前预测，不生成误差标签）"
    )
    markdown = f"""# 赛后复盘：{match['team_a']} vs {match['team_b']}

## 1. 基础对照

- 预测首选比分：{predicted_score}
- 预测备选比分：数据库未保存
- 实际比分：{actual_score}
- 是否命中胜平负：{result_hit}
- 是否命中总进球区间：数据库未保存
- 是否命中双方进球：{btts_hit}

## 2. 实际比赛数据

| 指标 | {match['team_a']} | {match['team_b']} |
|---|---:|---:|
| 射门 | {display(stats['shots_a'])} | {display(stats['shots_b'])} |
| 射正 | {display(stats['shots_on_target_a'])} | {display(stats['shots_on_target_b'])} |
| xG | {display(stats['xg_a'])} | {display(stats['xg_b'])} |
| 控球率 | {display(stats['possession_a'])} | {display(stats['possession_b'])} |
| 角球 | {display(stats['corners_a'])} | {display(stats['corners_b'])} |
| 红牌 | {display(stats['red_cards'])} | 合计字段 |

补充事件：

- 进球时间线：{timeline}
- 点球：{display(stats['penalty_goals'])}
- 乌龙：{display(stats['own_goals'])}
- 补时进球：{display(stats['stoppage_time_goals'])}

## 3. 关键球员逐场表现

| 球员 | 球队 | 首发 | 分钟 | 进球 | 助攻 | 射门/射正 | 乌龙 |
|---|---|---|---:|---:|---:|---|---:|
{chr(10).join(player_rows)}

## 4. 误差类型

{error_markdown}

## 5. 具体失败原因

{chr(10).join(f'{index}. {reason}' for index, reason in enumerate(failure_reasons, 1))}

## 6. 可沉淀经验

| 经验 | 下次如何修正 |
|---|---|
{lesson_markdown}

## 7. 建议写入历史样本标签

{tag_markdown}

数据来源：ESPN FIFA World Cup 比赛中心；高级统计缺失项保持为未知。
"""
    return markdown, errors, failure_reasons, lessons, suggestions


def main() -> int:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        matches = connection.execute(
            """
            SELECT m.*, h.predicted_score, h.error_types_json,
                   h.reusable_lessons_json, h.tags_json, h.notes
            FROM matches m
            LEFT JOIN historical_samples h ON h.match_id=m.match_id
            ORDER BY m.match_date, m.match_id
            """
        ).fetchall()
        with connection:
            for row in matches:
                stats = connection.execute(
                    "SELECT * FROM post_match_stats WHERE match_id=?",
                    (row["match_id"],),
                ).fetchone()
                if stats is None:
                    raise ValueError(f"缺少 post_match_stats: {row['match_id']}")
                key_players = connection.execute(
                    """
                    SELECT team_name, player_name, started, minutes_played,
                           goals, assists, shots, shots_on_target, own_goals
                    FROM player_match_stats
                    WHERE match_id=?
                      AND (
                        COALESCE(goals, 0)>0 OR
                        COALESCE(assists, 0)>0 OR
                        COALESCE(own_goals, 0)>0
                      )
                    ORDER BY goals DESC, assists DESC, player_name
                    """,
                    (row["match_id"],),
                ).fetchall()
                goal_events = connection.execute(
                    """
                    SELECT t.team_name, p.player_name, e.event_type,
                           e.minute, e.stoppage_minute
                    FROM player_match_events e
                    JOIN teams t ON t.team_id=e.team_id
                    LEFT JOIN players p ON p.player_id=e.player_id
                    WHERE e.match_id=? AND e.event_type IN ('goal', 'own_goal')
                    ORDER BY e.minute, e.stoppage_minute
                    """,
                    (row["match_id"],),
                ).fetchall()
                match = dict(row)
                match["goal_events"] = goal_events
                markdown, errors, reasons, lessons, suggestions = build_review(
                    match, stats, row, key_players
                )
                review_path = REVIEW_DIR / f"{row['match_id']}.md"
                review_path.write_text(markdown, encoding="utf-8")

                connection.execute(
                    "DELETE FROM post_match_reviews WHERE match_id=?",
                    (row["match_id"],),
                )
                connection.execute(
                    """
                    INSERT INTO post_match_reviews(
                        match_id, reviewed_at, predicted_score, actual_score,
                        error_types_json, failure_reasons_json,
                        reusable_lessons_json, rule_weight_suggestions_json,
                        review_markdown
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["match_id"],
                        now_iso(),
                        row["predicted_score"],
                        f"{row['actual_score_a']}-{row['actual_score_b']}",
                        json.dumps(errors, ensure_ascii=False),
                        json.dumps(reasons, ensure_ascii=False),
                        json.dumps(lessons, ensure_ascii=False),
                        json.dumps(suggestions, ensure_ascii=False),
                        markdown,
                    ),
                )
                for tag in json.loads(row["tags_json"] or "[]"):
                    connection.execute(
                        """
                        INSERT INTO historical_sample_tags(match_id, tag, note)
                        VALUES (?, ?, ?)
                        ON CONFLICT(match_id, tag) DO UPDATE SET note=excluded.note
                        """,
                        (row["match_id"], tag, "由赛后复盘同步"),
                    )
                print(f"已同步复盘: {row['match_id']}")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"数据库完整性检查失败: {integrity}")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
