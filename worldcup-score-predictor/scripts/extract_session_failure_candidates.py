#!/usr/bin/env python3
"""从 Codex 会话记录中抽取世界杯预测失败候选。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
CODEX_HOME = SKILL_ROOT.parents[1]
DEFAULT_OUTPUT = SKILL_ROOT / "data" / "backfills" / "session_failure_candidates.jsonl"
DEFAULT_ACCEPTED_OUTPUT = SKILL_ROOT / "data" / "backfills" / "accepted_session_failure_candidates.jsonl"
DEFAULT_REPORT = SKILL_ROOT / "data" / "backfills" / "failure_backfill_report.json"

KEYWORD_RE = re.compile(
    r"世界杯|worldcup-score-predictor|比分预测|预测比分|首选比分|次选比分|实际比分|胜负倾向|总进球|BTTS",
    re.IGNORECASE,
)
STRONG_SIGNAL_RE = re.compile(
    r"worldcup-score-predictor|比分预测|预测比分|首选比分|次选比分|实际比分|胜负倾向|总进球|BTTS|预测",
    re.IGNORECASE,
)
DIRECT_CANDIDATE_SIGNAL_RE = re.compile(
    r"预测比分|首选比分|次选比分|实际比分|原预测|主预测|我们预测|我预测|预测为|预测结论|"
    r"预测[:：]|赛后看|实际赛果|预测\s*(?:vs|VS|/|\|)\s*实际|错在|预测失败|预测误差"
)
SCORE_RE = re.compile(r"\b\d{1,2}-\d{1,2}\b")
MATCH_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z（）()·.\- ]{2,40}?)\s*(?:vs|VS|v\.?|对阵|对)\s*"
    r"([\u4e00-\u9fffA-Za-z（）()·.\- ]{2,40})"
)
SESSION_ID_RE = re.compile(r"(019[0-9a-f]{5,}(?:-[0-9a-f]{4,})+)\.jsonl$", re.IGNORECASE)
NOISE_MARKERS = (
    "<codex_internal_context",
    "<proposed_plan>",
    "PLEASE IMPLEMENT THIS PLAN",
    "## Key Changes",
    "## Test Plan",
    "schema_version",
    "role-result-1.0",
    "\"role_id\"",
    "\"coverage\"",
    "CREATE TABLE",
    "INSERT INTO",
    "UPDATE SET",
    "同一比赛多版本预测去重",
    "软信息维度",
    "重新整理的一版 **世界杯足球比分预测分析维度**",
    "轻量回测脚本的作用",
    "旧失败怎么补",
    "以后怎么避免继续散落",
)
MATCH_TOKEN_BLACKLIST = {
    "数据",
    "对象",
    "用途",
    "字段",
    "预测",
    "实际",
    "比分",
    "candidate",
    "schema",
    "source",
    "coverage",
    "强强",
    "强队",
    "弱队",
    "点球",
    "总进球",
    "球员关系",
    "战术配合",
    "同一比赛多版本预测去重",
}
MATCH_TOKEN_BAD_SUBSTRINGS = (
    "表现",
    "差异",
    "影响",
    "关系",
    "配合",
    "能力",
    "分布",
    "路径",
    "总进球",
    "预测",
    "实际",
    "比分",
)
MATCH_TOKEN_BAD_LOWER_SUBSTRINGS = (
    "prediction",
    "world-cup",
    "match-report",
    "preview",
    "article",
    "http",
    "www",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_thread_index(codex_home: Path) -> dict[str, str]:
    index_path = codex_home / "session_index.jsonl"
    result: dict[str, str] = {}
    if not index_path.exists():
        return result
    for line in index_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = item.get("id")
        thread_name = item.get("thread_name")
        if isinstance(session_id, str) and isinstance(thread_name, str):
            result[session_id] = thread_name
    return result


def session_id_from_path(path: Path) -> str:
    match = SESSION_ID_RE.search(path.name)
    return match.group(1) if match else path.stem


def message_texts(payload: dict[str, Any]) -> tuple[str | None, list[str]]:
    if payload.get("type") != "message":
        return None, []
    role = payload.get("role")
    if role not in {"user", "assistant"}:
        return None, []
    texts: list[str] = []
    for content in payload.get("content") or []:
        if isinstance(content, dict):
            text = content.get("text") or content.get("input_text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return str(role), texts


def extract_match_text(text: str) -> str:
    match = MATCH_RE.search(text)
    if not match:
        return ""
    left = " ".join(match.group(1).split())
    right = " ".join(match.group(2).split())
    if not is_plausible_team_token(left) or not is_plausible_team_token(right):
        return ""
    return f"{left} vs {right}"


def extract_scores(text: str) -> list[str]:
    scores: list[str] = []
    for match in SCORE_RE.finditer(text):
        raw = match.group(0)
        left_text, right_text = raw.split("-", 1)
        # 07-06 这类日期片段会被比分正则命中，但不是预测比分。
        if (len(left_text) == 2 and left_text.startswith("0")) or (
            len(right_text) == 2 and right_text.startswith("0")
        ):
            continue
        left, right = int(left_text), int(right_text)
        if left <= 9 and right <= 9:
            scores.append(f"{left}-{right}")
    return scores


def is_noise_text(text: str) -> bool:
    if any(marker in text for marker in NOISE_MARKERS):
        return True
    if text.lstrip().startswith("已更新完成") and not re.search(
        r"我们预测|我预测|主预测|原预测|首选比分|次选比分|预测\s*(?:vs|VS|/|\|)\s*实际",
        text,
    ):
        return True
    stripped = text.lstrip()
    if stripped.startswith("{") and ("\"match\"" in text or "\"results\"" in text):
        return True
    return False


def is_plausible_team_token(value: str) -> bool:
    cleaned = value.strip(" -:：,，|`\"'[]{}.*•")
    if len(cleaned) < 2 or len(cleaned) > 30:
        return False
    lowered = cleaned.lower()
    if lowered in MATCH_TOKEN_BLACKLIST or cleaned in MATCH_TOKEN_BLACKLIST:
        return False
    if any(token in cleaned for token in MATCH_TOKEN_BLACKLIST):
        return False
    if any(token in cleaned for token in MATCH_TOKEN_BAD_SUBSTRINGS):
        return False
    if any(token in lowered for token in MATCH_TOKEN_BAD_LOWER_SUBSTRINGS):
        return False
    if re.fullmatch(r"[a-z]{1,3}", cleaned):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", cleaned))


def candidate_confidence(text: str, scores: list[str], role: str) -> str:
    if role == "assistant" and scores and ("首选比分" in text or "预测结论" in text):
        return "high"
    if scores and ("预测" in text or "比分" in text):
        return "medium"
    return "low"


def extract_candidates(codex_home: Path) -> list[dict[str, Any]]:
    thread_index = load_thread_index(codex_home)
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.exists():
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for path in sorted(sessions_dir.rglob("*.jsonl")):
        session_id = session_id_from_path(path)
        thread_name = thread_index.get(session_id, "")
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig", errors="ignore").splitlines(),
            start=1,
        ):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            role, texts = message_texts(item.get("payload") or {})
            if role is None:
                continue
            for text in texts:
                if is_noise_text(text):
                    continue
                if not KEYWORD_RE.search(text):
                    continue
                if not DIRECT_CANDIDATE_SIGNAL_RE.search(text):
                    continue
                scores = extract_scores(text)
                if not scores:
                    continue
                match_text = extract_match_text(text)
                if not match_text and not STRONG_SIGNAL_RE.search(text):
                    continue
                snippet = " ".join(text.split())[:1200]
                key = (session_id, role, snippet)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    {
                        "schema_version": "session-failure-candidate-1.0",
                        "status": "needs_review",
                        "thread_id": session_id,
                        "thread_name": thread_name,
                        "session_file": str(path),
                        "line_number": line_number,
                        "timestamp": item.get("timestamp"),
                        "role": role,
                        "candidate_match": match_text,
                        "candidate_scores": scores,
                        "confidence": candidate_confidence(text, scores, role),
                        "raw_snippet": snippet,
                    }
                )
    return candidates


def write_candidates(candidates: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(candidate, ensure_ascii=False) for candidate in candidates)
        + ("\n" if candidates else ""),
        encoding="utf-8",
    )


def update_backfill_report(report_path: Path, candidates: list[dict[str, Any]], output: Path) -> None:
    report: dict[str, Any] = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            report = {}
    report["chat_candidate_count"] = len(candidates)
    report["chat_candidate_output"] = str(output)
    report["chat_candidate_updated_at"] = now_iso()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_backfill_module() -> Any:
    module_path = SKILL_ROOT / "scripts" / "backfill_failure_samples.py"
    spec = importlib.util.spec_from_file_location("backfill_failure_samples", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 backfill_failure_samples.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def accept_reviewed_candidates(reviewed_path: Path, db_path: Path, seed_path: Path, output: Path) -> int:
    if not reviewed_path.exists():
        raise FileNotFoundError(f"reviewed file not found: {reviewed_path}")
    accepted: list[dict[str, Any]] = []
    for line in reviewed_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("status") not in {"accepted", "approved"}:
            continue
        required = {"match_id", "teams_text", "predicted_score", "actual_score"}
        missing = sorted(required - set(item))
        if missing:
            raise ValueError(f"accepted candidate 缺少字段: {missing}")
        tags = item.get("tags") if isinstance(item.get("tags"), list) else ["聊天记录补录"]
        error_types = (
            item.get("error_types")
            if isinstance(item.get("error_types"), list)
            else tags
        )
        lessons = (
            item.get("reusable_lessons")
            if isinstance(item.get("reusable_lessons"), list)
            else ["聊天记录候选经人工确认后补入失败样本库。"]
        )
        accepted.append(
            {
                "match_id": item["match_id"],
                "teams_text": item["teams_text"],
                "predicted_score": item["predicted_score"],
                "actual_score": item["actual_score"],
                "error_types": error_types,
                "reusable_lessons": lessons,
                "tags": tags,
                "notes": item.get("notes") or f"人工确认自聊天候选；accepted_at={now_iso()}",
            }
        )

    module = load_backfill_module()
    module.upsert_samples(db_path, accepted)
    module.upsert_seed_samples(seed_path, accepted)
    write_candidates(accepted, output)
    return len(accepted)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抽取或接收聊天记录中的预测失败候选")
    parser.add_argument("--codex-home", type=Path, default=CODEX_HOME, help="Codex home 目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="候选输出 JSONL")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="补录报告 JSON")
    parser.add_argument(
        "--accept-reviewed",
        type=Path,
        help="导入人工确认后的候选 JSONL；只接受 status=accepted/approved 的行",
    )
    parser.add_argument(
        "--accepted-output",
        type=Path,
        default=DEFAULT_ACCEPTED_OUTPUT,
        help="已接受候选备份 JSONL",
    )
    parser.add_argument("--db", type=Path, default=SKILL_ROOT / "data" / "worldcup_prediction_knowledge.sqlite")
    parser.add_argument("--seed", type=Path, default=SKILL_ROOT / "seed" / "historical_samples.jsonl")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.accept_reviewed:
        count = accept_reviewed_candidates(args.accept_reviewed, args.db, args.seed, args.accepted_output)
        print(f"已导入人工确认聊天候选: {count}")
        return 0

    candidates = extract_candidates(args.codex_home)
    write_candidates(candidates, args.output)
    update_backfill_report(args.report, candidates, args.output)
    print(f"已抽取聊天候选: {len(candidates)}")
    print(f"输出: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
