#!/usr/bin/env python3
"""将已结束比赛及球员逐场表现事务化写入 SQLite。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = SKILL_ROOT / "data" / "worldcup_prediction_knowledge.sqlite"
SCHEMA_FILE = SKILL_ROOT / "schema.sql"
MIGRATION_KEY = "2026-06-18-player-match-stats-v1"

TEAM_STAT_FIELDS = [
    "shots_a",
    "shots_b",
    "shots_on_target_a",
    "shots_on_target_b",
    "xg_a",
    "xg_b",
    "possession_a",
    "possession_b",
    "corners_a",
    "corners_b",
    "set_piece_goals",
    "penalty_goals",
    "own_goals",
    "red_cards",
    "goalkeeper_errors",
    "stoppage_time_goals",
]

PLAYER_STAT_FIELDS = [
    "shirt_number",
    "position",
    "lineup_status",
    "started",
    "captain",
    "minutes_played",
    "substituted_on_minute",
    "substituted_off_minute",
    "goals",
    "assists",
    "shots",
    "shots_on_target",
    "xg",
    "xa",
    "key_passes",
    "big_chances_created",
    "touches",
    "touches_in_opposition_box",
    "passes_attempted",
    "passes_completed",
    "dribbles_attempted",
    "dribbles_completed",
    "tackles",
    "interceptions",
    "clearances",
    "blocks",
    "recoveries",
    "duels_total",
    "duels_won",
    "aerial_duels_total",
    "aerial_duels_won",
    "fouls_committed",
    "fouls_drawn",
    "offsides",
    "saves",
    "goals_conceded",
    "penalties_saved",
    "yellow_cards",
    "red_cards",
    "own_goals",
    "rating",
    "source_ids_json",
    "notes",
]

NONNEGATIVE_PLAYER_FIELDS = {
    field
    for field in PLAYER_STAT_FIELDS
    if field
    not in {
        "position",
        "lineup_status",
        "started",
        "captain",
        "source_ids_json",
        "notes",
        "rating",
    }
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("赛后数据顶层必须是 JSON 对象")
    return data


def require_text(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} 不能为空")


def validate_nonnegative(value: Any, field: str, errors: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        errors.append(f"{field} 必须是非负数字或 null")


def validate_input(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    match = data.get("match")
    if not isinstance(match, dict):
        return ["match 必须是对象"]

    for field in ("match_id", "competition", "match_date", "team_a", "team_b"):
        require_text(match.get(field), f"match.{field}", errors)
    for field in ("actual_score_a", "actual_score_b"):
        value = match.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"match.{field} 必须是非负整数")

    completeness = data.get("data_completeness")
    if completeness not in {"full", "partial"}:
        errors.append("data_completeness 必须是 full 或 partial")

    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources 至少需要一个来源")
        sources = []
    source_refs: list[str] = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"sources[{index}] 必须是对象")
            continue
        require_text(source.get("source_ref"), f"sources[{index}].source_ref", errors)
        require_text(source.get("source_title"), f"sources[{index}].source_title", errors)
        if isinstance(source.get("source_ref"), str):
            source_refs.append(source["source_ref"])
    if len(source_refs) != len(set(source_refs)):
        errors.append("sources.source_ref 不得重复")
    known_sources = set(source_refs)

    players = data.get("players")
    if not isinstance(players, list) or not players:
        errors.append("players 至少需要一名球员")
        players = []

    allowed_teams = {match.get("team_a"), match.get("team_b")}
    player_keys: list[tuple[str, str]] = []
    active_counts: Counter[str] = Counter()
    goals_by_team: Counter[str] = Counter()
    own_goals_by_team: Counter[str] = Counter()

    for index, player in enumerate(players):
        prefix = f"players[{index}]"
        if not isinstance(player, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        for field in ("team_name", "player_name", "lineup_status"):
            require_text(player.get(field), f"{prefix}.{field}", errors)
        team_name = player.get("team_name")
        player_name = player.get("player_name")
        if team_name not in allowed_teams:
            errors.append(f"{prefix}.team_name 必须等于 match.team_a 或 match.team_b")
        if isinstance(team_name, str) and isinstance(player_name, str):
            player_keys.append((team_name, player_name))

        status = player.get("lineup_status")
        if status not in {"starter", "substitute", "unused"}:
            errors.append(f"{prefix}.lineup_status 值无效")
        started = player.get("started")
        if not isinstance(started, bool):
            errors.append(f"{prefix}.started 必须是布尔值")
        elif status == "starter" and not started:
            errors.append(f"{prefix}: starter 必须 started=true")
        elif status != "starter" and started:
            errors.append(f"{prefix}: 非 starter 必须 started=false")

        minutes = player.get("minutes_played")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 <= minutes <= 130:
            errors.append(f"{prefix}.minutes_played 必须是0至130的整数")
        elif minutes > 0 and isinstance(team_name, str):
            active_counts[team_name] += 1
        if status == "unused" and minutes != 0:
            errors.append(f"{prefix}: unused 球员出场时间必须为0")

        for field in NONNEGATIVE_PLAYER_FIELDS:
            validate_nonnegative(player.get(field), f"{prefix}.{field}", errors)
        for completed, attempted in (
            ("shots_on_target", "shots"),
            ("passes_completed", "passes_attempted"),
            ("dribbles_completed", "dribbles_attempted"),
            ("duels_won", "duels_total"),
            ("aerial_duels_won", "aerial_duels_total"),
        ):
            left, right = player.get(completed), player.get(attempted)
            if left is not None and right is not None and left > right:
                errors.append(f"{prefix}.{completed} 不得大于 {attempted}")

        ids = player.get("source_ids")
        if not isinstance(ids, list) or not ids:
            errors.append(f"{prefix}.source_ids 至少需要一个来源")
        else:
            unknown = sorted(set(ids) - known_sources)
            if unknown:
                errors.append(f"{prefix}.source_ids 引用了未知来源 {unknown}")

        if isinstance(team_name, str):
            goals_by_team[team_name] += player.get("goals") or 0
            own_goals_by_team[team_name] += player.get("own_goals") or 0

    if len(player_keys) != len(set(player_keys)):
        errors.append("同一球队的球员不得重复")
    if completeness == "full":
        for team in allowed_teams:
            if isinstance(team, str) and active_counts[team] < 11:
                errors.append(f"完整数据中 {team} 至少需要11名实际出场球员")
        team_a, team_b = match.get("team_a"), match.get("team_b")
        if isinstance(team_a, str) and isinstance(team_b, str):
            calculated_a = goals_by_team[team_a] + own_goals_by_team[team_b]
            calculated_b = goals_by_team[team_b] + own_goals_by_team[team_a]
            if calculated_a != match.get("actual_score_a"):
                errors.append(
                    f"A队球员进球归因合计为{calculated_a}，与实际比分{match.get('actual_score_a')}不一致"
                )
            if calculated_b != match.get("actual_score_b"):
                errors.append(
                    f"B队球员进球归因合计为{calculated_b}，与实际比分{match.get('actual_score_b')}不一致"
                )

    events = data.get("events", [])
    if not isinstance(events, list):
        errors.append("events 必须是数组")
        events = []
    event_refs: list[str] = []
    for index, event in enumerate(events):
        prefix = f"events[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        for field in ("event_ref", "team_name", "event_type"):
            require_text(event.get(field), f"{prefix}.{field}", errors)
        if event.get("team_name") not in allowed_teams:
            errors.append(f"{prefix}.team_name 必须属于本场球队")
        minute = event.get("minute")
        stoppage = event.get("stoppage_minute", 0)
        if isinstance(minute, bool) or not isinstance(minute, int) or not 0 <= minute <= 130:
            errors.append(f"{prefix}.minute 必须是0至130的整数")
        if isinstance(stoppage, bool) or not isinstance(stoppage, int) or not 0 <= stoppage <= 30:
            errors.append(f"{prefix}.stoppage_minute 必须是0至30的整数")
        ids = event.get("source_ids")
        if not isinstance(ids, list) or not ids:
            errors.append(f"{prefix}.source_ids 至少需要一个来源")
        elif set(ids) - known_sources:
            errors.append(f"{prefix}.source_ids 引用了未知来源")
        if isinstance(event.get("event_ref"), str):
            event_refs.append(event["event_ref"])
    if len(event_refs) != len(set(event_refs)):
        errors.append("events.event_ref 不得重复")
    return errors


def column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in connection.execute(f"PRAGMA table_info({table})"))


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )


def migrate_schema(connection: sqlite3.Connection) -> None:
    if table_exists(connection, "match_sources") and not column_exists(
        connection, "match_sources", "source_ref"
    ):
        connection.execute("ALTER TABLE match_sources ADD COLUMN source_ref TEXT")
    connection.execute("DROP INDEX IF EXISTS idx_match_sources_ref")
    connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8-sig"))
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations(migration_key, applied_at) VALUES (?, ?)",
        (MIGRATION_KEY, now_iso()),
    )


def upsert_team(connection: sqlite3.Connection, team_name: str, timestamp: str) -> int:
    connection.execute(
        """
        INSERT INTO teams(team_name, updated_at) VALUES (?, ?)
        ON CONFLICT(team_name) DO UPDATE SET updated_at=excluded.updated_at
        """,
        (team_name, timestamp),
    )
    row = connection.execute(
        "SELECT team_id FROM teams WHERE team_name=?", (team_name,)
    ).fetchone()
    assert row is not None
    return int(row[0])


def upsert_player(
    connection: sqlite3.Connection,
    team_id: int,
    player: dict[str, Any],
    timestamp: str,
) -> int:
    connection.execute(
        """
        INSERT INTO players(
            team_id, player_name, position, player_type, current_status,
            evidence, updated_at
        ) VALUES (?, ?, ?, ?, 'active', ?, ?)
        ON CONFLICT(team_id, player_name) DO UPDATE SET
            position=COALESCE(NULLIF(excluded.position, ''), players.position),
            player_type=COALESCE(NULLIF(excluded.player_type, ''), players.player_type),
            evidence=COALESCE(NULLIF(excluded.evidence, ''), players.evidence),
            updated_at=excluded.updated_at
        """,
        (
            team_id,
            player["player_name"],
            player.get("position"),
            player.get("player_type"),
            player.get("notes"),
            timestamp,
        ),
    )
    row = connection.execute(
        "SELECT player_id FROM players WHERE team_id=? AND player_name=?",
        (team_id, player["player_name"]),
    ).fetchone()
    assert row is not None
    return int(row[0])


def ingest(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, int]:
    timestamp = now_iso()
    match = data["match"]
    match_id = match["match_id"]
    connection.execute(
        """
        INSERT INTO matches(
            match_id, competition, match_date, stage, venue, team_a, team_b,
            actual_score_a, actual_score_b, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id) DO UPDATE SET
            competition=excluded.competition,
            match_date=excluded.match_date,
            stage=excluded.stage,
            venue=excluded.venue,
            team_a=excluded.team_a,
            team_b=excluded.team_b,
            actual_score_a=excluded.actual_score_a,
            actual_score_b=excluded.actual_score_b,
            updated_at=excluded.updated_at
        """,
        (
            match_id,
            match["competition"],
            match["match_date"],
            match.get("stage"),
            match.get("venue"),
            match["team_a"],
            match["team_b"],
            match["actual_score_a"],
            match["actual_score_b"],
            timestamp,
            timestamp,
        ),
    )

    team_ids = {
        name: upsert_team(connection, name, timestamp)
        for name in (match["team_a"], match["team_b"])
    }

    for source in data["sources"]:
        connection.execute(
            """
            INSERT INTO match_sources(
                match_id, source_ref, source_title, source_url, source_type,
                summary, reliability, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, source_ref) DO UPDATE SET
                source_title=excluded.source_title,
                source_url=excluded.source_url,
                source_type=excluded.source_type,
                summary=excluded.summary,
                reliability=excluded.reliability,
                captured_at=excluded.captured_at
            """,
            (
                match_id,
                source["source_ref"],
                source["source_title"],
                source.get("source_url"),
                source.get("source_type"),
                source.get("summary"),
                source.get("reliability", "medium"),
                timestamp,
            ),
        )

    team_stats = data.get("team_stats")
    if isinstance(team_stats, dict):
        columns = ["match_id", *TEAM_STAT_FIELDS, "notes", "updated_at"]
        values = [match_id, *[team_stats.get(field) for field in TEAM_STAT_FIELDS]]
        values.extend([team_stats.get("notes"), timestamp])
        updates = [
            f"{field}=COALESCE(excluded.{field}, post_match_stats.{field})"
            for field in TEAM_STAT_FIELDS
        ]
        updates.extend(
            [
                "notes=COALESCE(NULLIF(excluded.notes, ''), post_match_stats.notes)",
                "updated_at=excluded.updated_at",
            ]
        )
        placeholders = ", ".join("?" for _ in columns)
        connection.execute(
            f"""
            INSERT INTO post_match_stats({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(match_id) DO UPDATE SET {", ".join(updates)}
            """,
            values,
        )

    player_ids: dict[tuple[str, str], int] = {}
    for player in data["players"]:
        team_name = player["team_name"]
        player_id = upsert_player(connection, team_ids[team_name], player, timestamp)
        player_ids[(team_name, player["player_name"])] = player_id

        normalized = dict(player)
        normalized["started"] = int(player["started"])
        normalized["captain"] = int(player.get("captain", False))
        normalized["source_ids_json"] = json.dumps(
            player.get("source_ids", []), ensure_ascii=False
        )
        columns = [
            "match_id",
            "player_id",
            "team_id",
            "team_name",
            "player_name",
            *PLAYER_STAT_FIELDS,
            "updated_at",
        ]
        values = [
            match_id,
            player_id,
            team_ids[team_name],
            team_name,
            player["player_name"],
            *[normalized.get(field) for field in PLAYER_STAT_FIELDS],
            timestamp,
        ]
        updates = []
        for field in PLAYER_STAT_FIELDS:
            if field in {"lineup_status", "started", "captain", "minutes_played"}:
                updates.append(f"{field}=excluded.{field}")
            elif field in {"position", "notes"}:
                updates.append(
                    f"{field}=COALESCE(NULLIF(excluded.{field}, ''), player_match_stats.{field})"
                )
            else:
                updates.append(
                    f"{field}=COALESCE(excluded.{field}, player_match_stats.{field})"
                )
        updates.append("updated_at=excluded.updated_at")
        placeholders = ", ".join("?" for _ in columns)
        connection.execute(
            f"""
            INSERT INTO player_match_stats({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(match_id, player_id) DO UPDATE SET {", ".join(updates)}
            """,
            values,
        )

    for event in data.get("events", []):
        team_name = event["team_name"]
        player_name = event.get("player_name")
        related_name = event.get("related_player_name")
        player_id = (
            player_ids.get((team_name, player_name)) if player_name else None
        )
        related_player_id = (
            player_ids.get((team_name, related_name)) if related_name else None
        )
        if player_name and player_id is None:
            raise ValueError(f"事件球员不在 players 中: {team_name} / {player_name}")
        if related_name and related_player_id is None:
            raise ValueError(f"关联球员不在 players 中: {team_name} / {related_name}")
        connection.execute(
            """
            INSERT INTO player_match_events(
                match_id, event_ref, team_id, player_id, related_player_id,
                event_type, minute, stoppage_minute, outcome, xg,
                source_ids_json, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, event_ref) DO UPDATE SET
                team_id=excluded.team_id,
                player_id=excluded.player_id,
                related_player_id=excluded.related_player_id,
                event_type=excluded.event_type,
                minute=excluded.minute,
                stoppage_minute=excluded.stoppage_minute,
                outcome=excluded.outcome,
                xg=excluded.xg,
                source_ids_json=excluded.source_ids_json,
                notes=excluded.notes
            """,
            (
                match_id,
                event["event_ref"],
                team_ids[team_name],
                player_id,
                related_player_id,
                event["event_type"],
                event["minute"],
                event.get("stoppage_minute", 0),
                event.get("outcome"),
                event.get("xg"),
                json.dumps(event.get("source_ids", []), ensure_ascii=False),
                event.get("notes"),
                timestamp,
            ),
        )

    active_by_team = {
        team_name: sum(
            1
            for player in data["players"]
            if player["team_name"] == team_name and player["minutes_played"] > 0
        )
        for team_name in (match["team_a"], match["team_b"])
    }
    connection.execute(
        """
        INSERT INTO post_match_data_imports(
            match_id, data_completeness, player_rows,
            team_a_active_players, team_b_active_players,
            event_rows, source_rows, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id) DO UPDATE SET
            data_completeness=excluded.data_completeness,
            player_rows=excluded.player_rows,
            team_a_active_players=excluded.team_a_active_players,
            team_b_active_players=excluded.team_b_active_players,
            event_rows=excluded.event_rows,
            source_rows=excluded.source_rows,
            imported_at=excluded.imported_at
        """,
        (
            match_id,
            data["data_completeness"],
            len(data["players"]),
            active_by_team[match["team_a"]],
            active_by_team[match["team_b"]],
            len(data.get("events", [])),
            len(data["sources"]),
            timestamp,
        ),
    )

    return {
        "sources": len(data["sources"]),
        "players": len(data["players"]),
        "events": len(data.get("events", [])),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="写入已完成比赛和球员逐场表现")
    parser.add_argument("input", nargs="?", type=Path, help="赛后球员数据 JSON")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 数据库")
    parser.add_argument(
        "--migrate-only", action="store_true", help="只迁移数据库结构，不写入比赛数据"
    )
    parser.add_argument(
        "--validate-only", action="store_true", help="只校验输入 JSON，不写入数据库"
    )
    parser.add_argument(
        "--audit", action="store_true", help="审计所有已完成比赛的球员数据覆盖率"
    )
    return parser.parse_args()


def audit_database(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        """
        SELECT
            m.match_id,
            m.team_a,
            m.team_b,
            CASE
                WHEN i.match_id IS NULL THEN 'missing'
                ELSE i.data_completeness
            END AS coverage,
            COALESCE(i.player_rows, 0),
            COALESCE(i.team_a_active_players, 0),
            COALESCE(i.team_b_active_players, 0),
            COALESCE(i.event_rows, 0)
        FROM matches m
        LEFT JOIN post_match_data_imports i ON i.match_id = m.match_id
        WHERE m.actual_score_a IS NOT NULL AND m.actual_score_b IS NOT NULL
        ORDER BY m.match_date, m.match_id
        """
    ).fetchall()
    full_count = sum(1 for row in rows if row[3] == "full")
    partial_count = sum(1 for row in rows if row[3] == "partial")
    missing_count = sum(1 for row in rows if row[3] == "missing")
    for row in rows:
        print(
            f"{row[0]} | {row[1]} vs {row[2]} | {row[3]} | "
            f"球员{row[4]} | 实际出场{row[5]}/{row[6]} | 事件{row[7]}"
        )
    print(
        f"覆盖汇总: full={full_count}, partial={partial_count}, "
        f"missing={missing_count}, total={len(rows)}"
    )
    return 0 if missing_count == 0 and partial_count == 0 else 1


def main() -> int:
    args = parse_args()
    if not args.migrate_only and not args.audit and args.input is None:
        print(
            "错误: 请提供赛后球员数据 JSON，或使用 --migrate-only / --audit",
            file=sys.stderr,
        )
        return 2

    data: dict[str, Any] | None = None
    if args.input is not None:
        try:
            data = load_json(args.input)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"错误: 无法读取输入文件: {exc}", file=sys.stderr)
            return 2
        errors = validate_input(data)
        if errors:
            for error in errors:
                print(f"错误: {error}", file=sys.stderr)
            print(f"校验失败: {len(errors)} 个错误", file=sys.stderr)
            return 1
        if args.validate_only:
            print(f"校验通过: {len(data['players'])} 名球员")
            return 0

    args.db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.db)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            migrate_schema(connection)
            if args.migrate_only:
                print(f"数据库迁移完成: {args.db}")
                return 0
            if args.audit:
                return audit_database(connection)
            assert data is not None
            counts = ingest(connection, data)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            print(f"错误: 数据库完整性检查失败: {integrity}", file=sys.stderr)
            return 1
        print(
            "写入完成: "
            f"{data['match']['match_id']}，"
            f"{counts['players']} 名球员，"
            f"{counts['events']} 个事件，"
            f"{counts['sources']} 个来源"
        )
        return 0
    except (sqlite3.Error, ValueError) as exc:
        print(f"错误: 写入失败并已回滚: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
