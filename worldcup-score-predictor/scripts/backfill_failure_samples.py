#!/usr/bin/env python3
"""从已生成预测 JSON 中补录旧预测失败样本。"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = SKILL_ROOT / "data" / "worldcup_prediction_knowledge.sqlite"
DEFAULT_PREDICTIONS_DIR = SKILL_ROOT / "data" / "generated_predictions"
DEFAULT_BACKFILL_DIR = SKILL_ROOT / "data" / "backfills"
DEFAULT_SEED_PATH = SKILL_ROOT / "seed" / "historical_samples.jsonl"

SCORE_RE = re.compile(r"^(\d+)-(\d+)$")
DATE_RE = re.compile(r"20\d\d-\d\d-\d\d")

ZH_TO_EN = {
    "墨西哥": "Mexico",
    "南非": "South Africa",
    "韩国": "South Korea",
    "捷克": "Czechia",
    "加拿大": "Canada",
    "波黑": "Bosnia-Herzegovina",
    "美国": "United States",
    "巴拉圭": "Paraguay",
    "卡塔尔": "Qatar",
    "瑞士": "Switzerland",
    "巴西": "Brazil",
    "摩洛哥": "Morocco",
    "海地": "Haiti",
    "苏格兰": "Scotland",
    "澳大利亚": "Australia",
    "土耳其": "Türkiye",
    "德国": "Germany",
    "库拉索": "Curaçao",
    "荷兰": "Netherlands",
    "日本": "Japan",
    "科特迪瓦": "Ivory Coast",
    "厄瓜多尔": "Ecuador",
    "瑞典": "Sweden",
    "突尼斯": "Tunisia",
    "西班牙": "Spain",
    "佛得角": "Cape Verde",
    "比利时": "Belgium",
    "埃及": "Egypt",
    "沙特阿拉伯": "Saudi Arabia",
    "乌拉圭": "Uruguay",
    "伊朗": "Iran",
    "新西兰": "New Zealand",
    "法国": "France",
    "塞内加尔": "Senegal",
    "伊拉克": "Iraq",
    "挪威": "Norway",
    "阿根廷": "Argentina",
    "阿尔及利亚": "Algeria",
    "奥地利": "Austria",
    "约旦": "Jordan",
    "葡萄牙": "Portugal",
    "刚果（金）": "Congo DR",
    "英格兰": "England",
    "克罗地亚": "Croatia",
    "加纳": "Ghana",
    "巴拿马": "Panama",
    "乌兹别克斯坦": "Uzbekistan",
    "哥伦比亚": "Colombia",
}
EN_TO_ZH = {value: key for key, value in ZH_TO_EN.items()}
TEAM_ALIASES = {
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Bosnia & Herzegovina": "Bosnia-Herzegovina",
    "Korea Republic": "South Korea",
    "Republic of Korea": "South Korea",
    "DR Congo": "Congo DR",
    "Democratic Republic of Congo": "Congo DR",
    "Congo DR": "Congo DR",
}
ABBR_TO_EN = {
    "MEX": "Mexico",
    "RSA": "South Africa",
    "KOR": "South Korea",
    "CZE": "Czechia",
    "CAN": "Canada",
    "BIH": "Bosnia-Herzegovina",
    "USA": "United States",
    "PAR": "Paraguay",
    "QAT": "Qatar",
    "SUI": "Switzerland",
    "BRA": "Brazil",
    "MAR": "Morocco",
    "HAI": "Haiti",
    "SCO": "Scotland",
    "AUS": "Australia",
    "TUR": "Türkiye",
    "GER": "Germany",
    "CUW": "Curaçao",
    "NED": "Netherlands",
    "JPN": "Japan",
    "CIV": "Ivory Coast",
    "ECU": "Ecuador",
    "SWE": "Sweden",
    "TUN": "Tunisia",
    "ESP": "Spain",
    "CPV": "Cape Verde",
    "BEL": "Belgium",
    "EGY": "Egypt",
    "KSA": "Saudi Arabia",
    "URU": "Uruguay",
    "IRN": "Iran",
    "NZL": "New Zealand",
    "FRA": "France",
    "SEN": "Senegal",
    "IRQ": "Iraq",
    "NOR": "Norway",
    "ARG": "Argentina",
    "ALG": "Algeria",
    "AUT": "Austria",
    "JOR": "Jordan",
    "POR": "Portugal",
    "COD": "Congo DR",
    "ENG": "England",
    "CRO": "Croatia",
    "GHA": "Ghana",
    "PAN": "Panama",
    "UZB": "Uzbekistan",
    "COL": "Colombia",
}

LESSONS_BY_TAG = {
    "精确比分未命中": "首选比分未命中时，后续预测需检查主路径是否过窄，并保留更完整的次选比分簇。",
    "胜平负未命中": "结果方向错误时，必须复核强弱方口径、阵容异动、临场事件和市场校准信号。",
    "热门方向错误": "热门方向与实际相反时，不能只按基础实力外推，需提高对热门防线漏洞和弱队反击/定位球路径的权重。",
    "总进球区间未命中": "实际总进球超出区间时，后续预测必须扩大高波动比赛的总进球范围。",
    "BTTS误判": "双方进球判断错误时，需重新核验弱队独立进球路径和零封冲突闸门。",
    "过度锁定低比分": "淘汰赛或高波动场景不能默认锁死0-0/1-0/1-1，必须保留事件链高比分路径。",
    "低估强队第三球": "强队有巨星、替补冲击或事件收益时，第三球不能只停留在尾部说明。",
    "低估弱队第二球": "弱队具备巨星、反击、定位球或替补供给时，第二球路径必须进入比分分布。",
    "高估弱队进球": "弱队单一攻击点或核心不首发时，不能机械给弱队一球或BTTS中高。",
    "尾部未进入主次": "实际路径已被尾部识别但未进入主次时，仲裁器需解释为何拒绝或上调到次选。",
}


@dataclass
class MatchResult:
    match_id: str
    match_date: str
    team_a: str
    team_b: str
    actual_score: tuple[int, int]
    stage: str | None = None


@dataclass
class PredictionAttempt:
    source_file: str
    absolute_path: Path
    source_mtime: float
    prediction_id: str
    prediction_date: str | None
    team_a: str
    team_b: str
    primary_score: tuple[int, int]
    primary_score_text: str
    alternative_scores: list[tuple[int, int]]
    tail_scores: list[tuple[int, int]]
    final_prediction: dict[str, Any]
    completeness_score: int
    strict_version: bool
    matched_result: MatchResult | None = None
    failure_tags: list[str] | None = None
    failure_reasons: list[str] | None = None
    reusable_lessons: list[str] | None = None
    canonical: bool = False


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_team(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    text = TEAM_ALIASES.get(text, text)
    return ZH_TO_EN.get(text, text)


def display_team(value: str) -> str:
    return EN_TO_ZH.get(value, value)


def score_tuple(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    match = SCORE_RE.fullmatch(value.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def score_text(score: tuple[int, int]) -> str:
    return f"{score[0]}-{score[1]}"


def result_type(score: tuple[int, int]) -> str:
    left, right = score
    return "win" if left > right else "loss" if left < right else "draw"


def btts(score: tuple[int, int]) -> bool:
    return score[0] > 0 and score[1] > 0


def parse_match_id_teams(match_id: str) -> tuple[str, str]:
    codes = [part for part in match_id.split("_") if part in ABBR_TO_EN]
    if len(codes) >= 2:
        return ABBR_TO_EN[codes[-2]], ABBR_TO_EN[codes[-1]]
    return "", ""


def extract_date(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        match = DATE_RE.search(str(value))
        if match:
            return match.group(0)
    return None


def parse_prediction_file(path: Path, root: Path) -> PredictionAttempt | None:
    try:
        analysis = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    final_prediction = analysis.get("final_prediction")
    if not isinstance(final_prediction, dict):
        return None
    primary_text = final_prediction.get("primary_score")
    primary = score_tuple(primary_text)
    if primary is None:
        return None
    match = analysis.get("match") if isinstance(analysis.get("match"), dict) else {}
    prediction_id = str(match.get("match_id") or path.stem)
    team_a = normalize_team(match.get("team_a"))
    team_b = normalize_team(match.get("team_b"))
    if not team_a or not team_b:
        team_a, team_b = parse_match_id_teams(prediction_id)
    if not team_a or not team_b:
        return None

    alternatives = [
        parsed
        for parsed in (score_tuple(item) for item in final_prediction.get("alternative_scores", []))
        if parsed is not None
    ]
    tails = [
        parsed
        for parsed in (score_tuple(item) for item in final_prediction.get("tail_scores", []))
        if parsed is not None
    ]
    completeness = len(final_prediction)
    if isinstance(analysis.get("dimension_analyses"), list):
        completeness += len(analysis["dimension_analyses"])
    if isinstance(analysis.get("review_metadata"), dict):
        completeness += 10
    relative = str(path.relative_to(root))
    return PredictionAttempt(
        source_file=relative,
        absolute_path=path,
        source_mtime=path.stat().st_mtime,
        prediction_id=prediction_id,
        prediction_date=extract_date(match.get("match_date"), prediction_id, relative),
        team_a=team_a,
        team_b=team_b,
        primary_score=primary,
        primary_score_text=str(primary_text),
        alternative_scores=alternatives,
        tail_scores=tails,
        final_prediction=final_prediction,
        completeness_score=completeness,
        strict_version="strict" in relative.lower(),
    )


def load_match_results(db_path: Path) -> list[MatchResult]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT match_id, match_date, team_a, team_b,
                   actual_score_a, actual_score_b, stage
            FROM matches
            WHERE actual_score_a IS NOT NULL AND actual_score_b IS NOT NULL
            """
        ).fetchall()
    finally:
        connection.close()
    return [
        MatchResult(
            match_id=row["match_id"],
            match_date=row["match_date"],
            team_a=normalize_team(row["team_a"]),
            team_b=normalize_team(row["team_b"]),
            actual_score=(int(row["actual_score_a"]), int(row["actual_score_b"])),
            stage=row["stage"],
        )
        for row in rows
    ]


def date_window(value: str | None) -> set[str]:
    if not value:
        return set()
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return {value}
    return {
        (parsed - timedelta(days=1)).isoformat(),
        parsed.isoformat(),
        (parsed + timedelta(days=1)).isoformat(),
    }


def match_prediction_to_actual(
    attempt: PredictionAttempt,
    results: list[MatchResult],
) -> MatchResult | None:
    candidates = [
        result
        for result in results
        if result.team_a == attempt.team_a and result.team_b == attempt.team_b
    ]
    if not candidates:
        return None
    allowed_dates = date_window(attempt.prediction_date)
    if allowed_dates:
        dated = [result for result in candidates if result.match_date in allowed_dates]
        if dated:
            candidates = dated
    return sorted(candidates, key=lambda item: (item.match_date, item.match_id))[-1]


def favorite_side(attempt: PredictionAttempt) -> str:
    orientation = attempt.final_prediction.get("score_orientation")
    if isinstance(orientation, dict):
        side = orientation.get("favorite_side")
        if side in {"team_a", "team_b", "even", "unknown"}:
            return str(side)
    left, right = attempt.primary_score
    if left > right:
        return "team_a"
    if right > left:
        return "team_b"
    return "unknown"


def classify_failure(attempt: PredictionAttempt, actual: MatchResult) -> tuple[list[str], list[str], list[str]]:
    predicted = attempt.primary_score
    actual_score = actual.actual_score
    final_prediction = attempt.final_prediction
    tags: list[str] = []
    reasons: list[str] = []

    def add(tag: str, reason: str) -> None:
        if tag not in tags:
            tags.append(tag)
            reasons.append(reason)

    if predicted != actual_score:
        add("精确比分未命中", f"首选 {score_text(predicted)}，实际 {score_text(actual_score)}。")
    if result_type(predicted) != result_type(actual_score):
        add("胜平负未命中", "首选比分对应的胜平负方向与实际结果不一致。")

    total_min = final_prediction.get("total_goals_min")
    total_max = final_prediction.get("total_goals_max")
    actual_total = sum(actual_score)
    if isinstance(total_min, int) and isinstance(total_max, int) and not total_min <= actual_total <= total_max:
        add("总进球区间未命中", f"预测总进球区间为 {total_min}-{total_max}，实际为 {actual_total}。")

    btts_level = final_prediction.get("both_teams_to_score")
    if (btts_level in {"medium", "high"} and not btts(actual_score)) or (
        btts_level == "low" and btts(actual_score)
    ):
        add("BTTS误判", f"双方进球判断为 {btts_level}，实际 BTTS={btts(actual_score)}。")

    if (
        (isinstance(total_max, int) and total_max <= 2)
        or (predicted[0] <= 1 and predicted[1] <= 1)
    ) and actual_total >= 4:
        add("过度锁定低比分", "低比分主路径遇到实际4球及以上开放局。")

    side = favorite_side(attempt)
    if side in {"team_a", "team_b"}:
        favorite_index = 0 if side == "team_a" else 1
        weak_index = 1 - favorite_index
        if result_type(predicted) in {"win", "loss"} and (
            actual_score[favorite_index] <= actual_score[weak_index]
        ):
            add("热门方向错误", "预测热门方未能兑现胜势或实际出局。")
        if actual_score[favorite_index] >= 3 and predicted[favorite_index] < 3:
            add("低估强队第三球", "热门方实际达到3球，但主预测未覆盖第三球。")
        if actual_score[weak_index] >= 2 and predicted[weak_index] < 2:
            add("低估弱队第二球", "弱势方实际达到2球，但主预测低估第二球路径。")
        if predicted[weak_index] > 0 and actual_score[weak_index] == 0:
            add("高估弱队进球", "主预测给出弱势方进球，但实际被零封。")
    else:
        if actual_score[0] >= 3 and predicted[0] < 3:
            add("低估强队第三球", "A队实际达到3球，但主预测未覆盖第三球。")
        if actual_score[1] >= 3 and predicted[1] < 3:
            add("低估强队第三球", "B队实际达到3球，但主预测未覆盖第三球。")
        if actual_score[0] >= 2 and predicted[0] < 2:
            add("低估弱队第二球", "A队实际达到2球，但主预测低估第二球。")
        if actual_score[1] >= 2 and predicted[1] < 2:
            add("低估弱队第二球", "B队实际达到2球，但主预测低估第二球。")

    actual_in_tail = actual_score in attempt.tail_scores
    actual_in_main_or_alt = actual_score == predicted or actual_score in attempt.alternative_scores
    if actual_in_tail and not actual_in_main_or_alt:
        add("尾部未进入主次", "实际比分曾被列入尾部，但没有进入首选或次选比分。")

    lessons = [LESSONS_BY_TAG[tag] for tag in tags if tag in LESSONS_BY_TAG]
    return tags, reasons, lessons


def select_canonical_attempts(attempts: list[PredictionAttempt]) -> dict[str, PredictionAttempt]:
    grouped: dict[str, list[PredictionAttempt]] = defaultdict(list)
    for attempt in attempts:
        if attempt.matched_result is not None:
            grouped[attempt.matched_result.match_id].append(attempt)

    selected: dict[str, PredictionAttempt] = {}
    for match_id, group in grouped.items():
        selected[match_id] = sorted(
            group,
            key=lambda item: (
                item.strict_version,
                item.source_mtime,
                item.completeness_score,
            ),
            reverse=True,
        )[0]
    return selected


def build_sample(attempt: PredictionAttempt) -> dict[str, Any]:
    assert attempt.matched_result is not None
    tags = attempt.failure_tags or []
    reasons = attempt.failure_reasons or []
    lessons = attempt.reusable_lessons or []
    teams_text = f"{display_team(attempt.team_a)} vs {display_team(attempt.team_b)}"
    actual_text = score_text(attempt.matched_result.actual_score)
    notes = (
        f"自动补录自 {attempt.source_file}；预测 {attempt.primary_score_text}，"
        f"实际 {actual_text}；失败标签：{', '.join(tags) if tags else '无'}。"
    )
    return {
        "match_id": attempt.matched_result.match_id,
        "teams_text": teams_text,
        "teams": teams_text,
        "predicted_score": attempt.primary_score_text,
        "actual_score": actual_text,
        "error_types": tags,
        "failure_reasons": reasons,
        "reusable_lessons": lessons,
        "tags": tags,
        "notes": notes,
        "source_file": attempt.source_file,
    }


def merge_unique(*items: list[str]) -> list[str]:
    merged: list[str] = []
    for group in items:
        for item in group:
            if item not in merged:
                merged.append(item)
    return merged


def load_existing_sample(connection: sqlite3.Connection, match_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT match_id, teams_text, predicted_score, actual_score,
               error_types_json, reusable_lessons_json, tags_json, notes
        FROM historical_samples
        WHERE match_id=?
        """,
        (match_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "match_id": row[0],
        "teams_text": row[1],
        "predicted_score": row[2],
        "actual_score": row[3],
        "error_types": json.loads(row[4] or "[]"),
        "reusable_lessons": json.loads(row[5] or "[]"),
        "tags": json.loads(row[6] or "[]"),
        "notes": row[7] or "",
    }


def upsert_samples(db_path: Path, samples: list[dict[str, Any]]) -> int:
    timestamp = now_iso()
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            for sample in samples:
                existing = load_existing_sample(connection, sample["match_id"])
                error_types = sample["error_types"]
                reusable_lessons = sample["reusable_lessons"]
                tags = sample["tags"]
                notes = sample["notes"]
                predicted_score = sample["predicted_score"]
                actual_score = sample["actual_score"]
                teams_text = sample["teams_text"]
                if existing:
                    error_types = merge_unique(existing["error_types"], error_types)
                    reusable_lessons = merge_unique(existing["reusable_lessons"], reusable_lessons)
                    tags = merge_unique(existing["tags"], tags)
                    notes = existing["notes"] or notes
                    predicted_score = existing["predicted_score"] or predicted_score
                    actual_score = existing["actual_score"] or actual_score
                    teams_text = existing["teams_text"] or teams_text

                connection.execute(
                    """
                    INSERT INTO historical_samples(
                        match_id, teams_text, predicted_score, actual_score,
                        error_types_json, reusable_lessons_json, tags_json,
                        notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id) DO UPDATE SET
                        teams_text=excluded.teams_text,
                        predicted_score=excluded.predicted_score,
                        actual_score=excluded.actual_score,
                        error_types_json=excluded.error_types_json,
                        reusable_lessons_json=excluded.reusable_lessons_json,
                        tags_json=excluded.tags_json,
                        notes=excluded.notes
                    """,
                    (
                        sample["match_id"],
                        teams_text,
                        predicted_score,
                        actual_score,
                        json.dumps(error_types, ensure_ascii=False),
                        json.dumps(reusable_lessons, ensure_ascii=False),
                        json.dumps(tags, ensure_ascii=False),
                        notes,
                        timestamp,
                    ),
                )
                for tag in tags:
                    connection.execute(
                        """
                        INSERT INTO historical_sample_tags(match_id, tag, note)
                        VALUES (?, ?, ?)
                        ON CONFLICT(match_id, tag) DO UPDATE SET note=excluded.note
                        """,
                        (sample["match_id"], tag, "由旧预测失败补录同步"),
                    )
        return len(samples)
    finally:
        connection.close()


def upsert_seed_samples(seed_path: Path, samples: list[dict[str, Any]]) -> int:
    existing: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    if seed_path.exists():
        for line in seed_path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            match_id = item.get("match_id")
            if isinstance(match_id, str) and match_id:
                existing[match_id] = item
                order.append(match_id)

    for sample in samples:
        seed_item = {
            "match_id": sample["match_id"],
            "teams": sample["teams_text"],
            "predicted_score": sample["predicted_score"],
            "actual_score": sample["actual_score"],
            "error_types": sample["error_types"],
            "reusable_lessons": sample["reusable_lessons"],
            "tags": sample["tags"],
            "notes": sample["notes"],
        }
        if sample["match_id"] in existing:
            old = existing[sample["match_id"]]
            seed_item["error_types"] = merge_unique(old.get("error_types", []), seed_item["error_types"])
            seed_item["reusable_lessons"] = merge_unique(
                old.get("reusable_lessons", []), seed_item["reusable_lessons"]
            )
            seed_item["tags"] = merge_unique(old.get("tags", []), seed_item["tags"])
            seed_item["notes"] = old.get("notes") or seed_item["notes"]
        else:
            order.append(sample["match_id"])
        existing[sample["match_id"]] = seed_item

    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(
        "\n".join(json.dumps(existing[match_id], ensure_ascii=False) for match_id in order)
        + ("\n" if order else ""),
        encoding="utf-8",
    )
    return len(samples)


def attempt_to_json(attempt: PredictionAttempt) -> dict[str, Any]:
    actual = attempt.matched_result
    return {
        "source_file": attempt.source_file,
        "prediction_id": attempt.prediction_id,
        "prediction_date": attempt.prediction_date,
        "match_id": actual.match_id if actual else None,
        "teams": f"{display_team(attempt.team_a)} vs {display_team(attempt.team_b)}",
        "predicted_score": attempt.primary_score_text,
        "alternative_scores": [score_text(score) for score in attempt.alternative_scores],
        "tail_scores": [score_text(score) for score in attempt.tail_scores],
        "actual_score": score_text(actual.actual_score) if actual else None,
        "strict_version": attempt.strict_version,
        "canonical": attempt.canonical,
        "failure_tags": attempt.failure_tags or [],
        "failure_reasons": attempt.failure_reasons or [],
    }


def collect_attempts(predictions_dir: Path, db_path: Path) -> tuple[list[PredictionAttempt], list[dict[str, Any]]]:
    results = load_match_results(db_path)
    attempts: list[PredictionAttempt] = []
    unmatched: list[dict[str, Any]] = []
    for path in sorted(predictions_dir.rglob("*.json")):
        attempt = parse_prediction_file(path, predictions_dir)
        if attempt is None:
            continue
        actual = match_prediction_to_actual(attempt, results)
        if actual is None:
            unmatched.append(
                {
                    "source_file": str(path.relative_to(predictions_dir)),
                    "prediction_id": attempt.prediction_id,
                    "teams": f"{display_team(attempt.team_a)} vs {display_team(attempt.team_b)}",
                    "predicted_score": attempt.primary_score_text,
                    "reason": "未匹配到 SQLite 已结束赛果",
                }
            )
        else:
            attempt.matched_result = actual
            tags, reasons, lessons = classify_failure(attempt, actual)
            attempt.failure_tags = tags
            attempt.failure_reasons = reasons
            attempt.reusable_lessons = lessons
            attempts.append(attempt)
    canonical = select_canonical_attempts(attempts)
    for attempt in attempts:
        attempt.canonical = (
            attempt.matched_result is not None
            and canonical.get(attempt.matched_result.match_id) is attempt
        )
    return attempts, unmatched


def build_report(
    attempts: list[PredictionAttempt],
    unmatched: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    tag_counts = Counter(tag for sample in samples for tag in sample["tags"])
    matched_match_ids = {
        attempt.matched_result.match_id
        for attempt in attempts
        if attempt.matched_result is not None
    }
    return {
        "schema_version": "failure-backfill-report-1.0",
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "scanned_prediction_files": len(attempts) + len(unmatched),
        "matched_prediction_attempts": len(attempts),
        "matched_unique_matches": len(matched_match_ids),
        "canonical_failure_samples": len(samples),
        "duplicate_prediction_versions": max(0, len(attempts) - len(matched_match_ids)),
        "unmatched_predictions": unmatched,
        "failure_tag_counts": dict(tag_counts),
    }


def write_backfill_outputs(
    backfill_dir: Path,
    attempts: list[PredictionAttempt],
    report: dict[str, Any],
) -> None:
    backfill_dir.mkdir(parents=True, exist_ok=True)
    attempts_path = backfill_dir / "failure_attempts.jsonl"
    attempts_path.write_text(
        "\n".join(json.dumps(attempt_to_json(attempt), ensure_ascii=False) for attempt in attempts)
        + ("\n" if attempts else ""),
        encoding="utf-8",
    )
    (backfill_dir / "failure_backfill_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="补录旧预测失败样本")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只生成补录报告和尝试明细，不写数据库和 seed")
    mode.add_argument("--apply", action="store_true", help="写入 historical_samples、historical_sample_tags 和 seed JSONL")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 数据库路径")
    parser.add_argument("--predictions-dir", type=Path, default=DEFAULT_PREDICTIONS_DIR, help="预测 JSON 目录")
    parser.add_argument("--backfill-dir", type=Path, default=DEFAULT_BACKFILL_DIR, help="补录输出目录")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED_PATH, help="历史样本 JSONL")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = not args.apply
    attempts, unmatched = collect_attempts(args.predictions_dir, args.db)
    samples = [
        build_sample(attempt)
        for attempt in attempts
        if attempt.canonical and attempt.failure_tags
    ]
    report = build_report(attempts, unmatched, samples, dry_run=dry_run)
    write_backfill_outputs(args.backfill_dir, attempts, report)

    if args.apply:
        db_count = upsert_samples(args.db, samples)
        seed_count = upsert_seed_samples(args.seed, samples)
        print(f"已写入失败样本: db={db_count}, seed={seed_count}")
    else:
        print("dry-run: 未写入数据库或 seed")
    print(
        "补录统计: "
        f"预测文件{report['scanned_prediction_files']}，"
        f"匹配尝试{report['matched_prediction_attempts']}，"
        f"canonical失败样本{report['canonical_failure_samples']}，"
        f"未匹配{len(unmatched)}"
    )
    print(f"报告: {args.backfill_dir / 'failure_backfill_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
