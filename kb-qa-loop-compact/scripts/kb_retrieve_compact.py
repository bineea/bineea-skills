#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高性能 KB 检索包装器。

该脚本不修改原 kb-qa-loop 的 vector_retrieval.py，而是复用它的 retrieve()
和 build_request_payload()，在新 skill 目录内增加：
- SQLite 响应缓存
- 来源去重
- text 片段裁剪
- 默认不输出 raw
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_BASE_RETRIEVAL = Path(r"C:\Users\guowb1\.claude\skills\kb-qa-loop\vector_retrieval.py")

SCOPE_SIGNAL_RE = re.compile(
    r"(适用|范围|口径|条件|前提|资格|对象|地区|地域|城市|北京|上海|京外|当地|各地|以.*为准|"
    r"正式|实习|外包|劳务派遣|签约主体|员工类型|人群|自.*起|截至|最新|修订|版本|政策|制度|"
    r"不同|差异|除外|例外|限制|需确认|须满足)"
)


def _load_base_module(path: Path) -> Any:
    if not path.exists():
        raise RuntimeError(f"找不到原始检索脚本：{path}")
    spec = importlib.util.spec_from_file_location("kb_base_vector_retrieval", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载原始检索脚本：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cache_path() -> Path:
    configured = os.environ.get("KB_COMPACT_CACHE_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1] / ".cache" / "kb_retrieval.sqlite3"


def _cache_key(payload: Dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _cache_get(key: str, ttl_s: int) -> Optional[Dict[str, Any]]:
    if ttl_s <= 0:
        return None
    path = _cache_path()
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT created_at, response_json FROM responses WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        created_at, response_json = row
        if time.time() - float(created_at) > ttl_s:
            return None
        return json.loads(response_json)
    except Exception:
        return None


def _cache_put(key: str, response: Dict[str, Any]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS responses (
                    cache_key TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    response_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO responses(cache_key, created_at, response_json)
                VALUES (?, ?, ?)
                """,
                (key, time.time(), json.dumps(response, ensure_ascii=False)),
            )
    except Exception:
        return


def _window(value: str, center: int, width: int) -> str:
    half = max(1, width // 2)
    start = max(0, center - half)
    end = min(len(value), start + width)
    start = max(0, end - width)
    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < len(value) else ""
    return prefix + value[start:end].strip() + suffix


def _scope_signal_windows(value: str, max_windows: int = 3, window_chars: int = 420) -> List[str]:
    windows: List[str] = []
    seen = set()
    for match in SCOPE_SIGNAL_RE.finditer(value):
        snippet = _window(value, match.start(), window_chars)
        key = snippet[:80]
        if key in seen:
            continue
        seen.add(key)
        windows.append(snippet)
        if len(windows) >= max_windows:
            break
    return windows


def _clip_text(text: Any, query: str, max_chars: int) -> str:
    value = "" if text is None else str(text)
    if max_chars <= 0 or len(value) <= max_chars:
        return value

    parts: List[str] = []
    # 保留开头，很多制度类文档会在开头说明适用范围/版本/人群。
    parts.append(value[: min(700, max_chars // 3)].strip())

    terms = [t for t in re.split(r"\s+", query.strip()) if len(t) >= 2]
    hit_index = -1
    lower_value = value.lower()
    for term in terms:
        idx = lower_value.find(term.lower())
        if idx >= 0:
            hit_index = idx
            break

    if hit_index >= 0:
        parts.append(_window(value, hit_index, min(900, max_chars // 2)))

    parts.extend(_scope_signal_windows(value))

    merged = "\n...\n".join(part for part in parts if part)
    if len(merged) > max_chars:
        merged = merged[:max_chars].rstrip()
    return merged + f"\n...(已截断，原文 {len(value)} 字符)"


def _compact_metadata(metadata: Dict[str, Any], text: Any) -> Dict[str, Any]:
    value = "" if text is None else str(text)
    out = dict(metadata)
    signals = sorted(set(match.group(0) for match in SCOPE_SIGNAL_RE.finditer(value)))
    out["_compact"] = {
        "original_text_chars": len(value),
        "truncated": False,
        "scope_signals": signals[:20],
    }
    return out


def _source_key(item: Dict[str, Any]) -> tuple:
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return (
        source.get("docId"),
        source.get("docName"),
        source.get("origin_path"),
        metadata.get("chunk_id") or metadata.get("page") or metadata.get("paragraph"),
    )


def compact_items(
    items: List[Dict[str, Any]],
    query: str,
    max_items: int,
    max_text_chars: int,
    max_total_text_chars: int,
    dedupe_source: bool,
) -> List[Dict[str, Any]]:
    compacted: List[Dict[str, Any]] = []
    seen_sources = set()
    used_chars = 0

    for item in items:
        if len(compacted) >= max_items:
            break
        key = _source_key(item)
        if dedupe_source and key in seen_sources:
            continue
        seen_sources.add(key)

        remaining = max_total_text_chars - used_chars
        if remaining <= 0:
            break
        limit = min(max_text_chars, remaining)
        original_text = item.get("text")
        text = _clip_text(original_text, query=query, max_chars=limit)
        used_chars += len(text)
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        compact_metadata = _compact_metadata(metadata, original_text)
        compact_metadata["_compact"]["truncated"] = len(text) < len("" if original_text is None else str(original_text))

        compacted.append(
            {
                "id": item.get("id"),
                "score": item.get("score"),
                "text": text,
                "metadata": compact_metadata,
                "source": item.get("source") if isinstance(item.get("source"), dict) else {},
            }
        )

    return compacted


def retrieve_compact(args: argparse.Namespace) -> Dict[str, Any]:
    base_path = Path(args.base_retrieval).expanduser()
    base = _load_base_module(base_path)
    payload = {
        "base_retrieval": str(base_path),
        "request": base.build_request_payload(query=args.query, topk=args.topk),
        "limits": {
            "max_items": args.max_items,
            "max_text_chars": args.max_text_chars,
            "max_total_text_chars": args.max_total_text_chars,
            "dedupe_source": args.dedupe_source,
        },
    }
    key = _cache_key(payload)

    cached = _cache_get(key, ttl_s=args.cache_ttl_s) if not args.no_cache else None
    if cached is not None:
        cached["cache"] = {"hit": True, "key": key, "ttl_s": args.cache_ttl_s}
        return cached

    result = base.retrieve(query=args.query, topk=args.topk)
    items = compact_items(
        result.get("items", []),
        query=args.query,
        max_items=args.max_items,
        max_text_chars=args.max_text_chars,
        max_total_text_chars=args.max_total_text_chars,
        dedupe_source=args.dedupe_source,
    )
    output: Dict[str, Any] = {
        "items": items,
        "cache": {"hit": False, "key": key, "ttl_s": args.cache_ttl_s},
        "limits": payload["limits"],
    }
    if args.include_raw_preview:
        raw_text = json.dumps(result.get("raw"), ensure_ascii=False)
        output["raw_preview"] = raw_text[: args.raw_preview_chars]

    if not args.no_cache:
        _cache_put(key, output)
    return output


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="KB compact 检索：缓存、去重、裁剪后输出 items[]")
    parser.add_argument("--query", required=True, help="检索问题/查询文本")
    parser.add_argument("--topk", type=int, default=10, help="远程检索条数")
    parser.add_argument("--max-items", type=int, default=10, help="输出证据条数上限")
    parser.add_argument("--max-text-chars", type=int, default=2200, help="每条 text 字符数上限")
    parser.add_argument("--max-total-text-chars", type=int, default=18000, help="所有 text 总字符数上限")
    parser.add_argument("--dedupe-source", action=argparse.BooleanOptionalAction, default=False, help="按来源去重")
    parser.add_argument("--cache-ttl-s", type=int, default=3600, help="缓存 TTL 秒数")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    parser.add_argument("--base-retrieval", default=str(DEFAULT_BASE_RETRIEVAL), help="原始 vector_retrieval.py 路径")
    parser.add_argument("--include-raw-preview", action="store_true", help="输出极短 raw 预览，仅用于诊断")
    parser.add_argument("--raw-preview-chars", type=int, default=1000, help="raw 预览最大字符数")
    parser.add_argument("--pretty", action="store_true", help="美化 JSON 输出")
    args = parser.parse_args(argv)

    try:
        output = retrieve_compact(args)
        if args.pretty:
            sys.stdout.write(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(json.dumps(output, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        sys.stdout.write(json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
