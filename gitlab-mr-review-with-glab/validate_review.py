#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""验证 review.json 的 JSON/结构，并可选校验 inline 是否命中当前 MR diff hunk。

用法：
  python validate_review.py --review review.json
  python validate_review.py --review review.json --context mr_review_out/context.json --check-diff warn

退出码：
  0 = 通过（可能有 warnings）
  2 = JSON/结构错误
  3 = diff 命中校验失败（仅在 --check-diff fail 时）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from glab_mr_writeback import _which_glab, fetch_latest_diff, line_hits_current_diff, load_json, parse_valid_new_line_ranges


def _as_text(v: Any) -> str:
    if isinstance(v, str):
        return v
    return ""


def _normalize_diff_path(p: str) -> str:
    p = p.strip()
    if p.startswith("b/"):
        return p[2:]
    return p


def validate_schema(review: Any, *, max_items: int) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(review, dict):
        errors.append("$：顶层必须是 JSON object")
        return errors, warnings

    if "note" not in review:
        errors.append("$.note：字段缺失（必须为 string，可为空串）")
    elif not isinstance(review.get("note"), str):
        errors.append(f"$.note：必须为 string（当前: {type(review.get('note')).__name__}）")

    if "inline" not in review:
        errors.append("$.inline：字段缺失（必须为 list，可为空 list）")
        return errors, warnings

    inline = review.get("inline")
    if not isinstance(inline, list):
        errors.append(f"$.inline：必须为 list（当前: {type(inline).__name__}）")
        return errors, warnings

    for i, it in enumerate(inline[: max_items if max_items > 0 else len(inline)]):
        base = f"$.inline[{i}]"
        if not isinstance(it, dict):
            errors.append(f"{base}：必须为 object（当前: {type(it).__name__}）")
            continue

        new_path = it.get("new_path")
        if not isinstance(new_path, str) or not new_path.strip():
            errors.append(f"{base}.new_path：必须为非空 string")

        new_line = it.get("new_line")
        if not isinstance(new_line, int) or new_line < 1:
            errors.append(f"{base}.new_line：必须为 int 且 >= 1")

        body = it.get("body")
        if not isinstance(body, str) or not body.strip():
            errors.append(f"{base}.body：必须为非空 string")

    if max_items > 0 and isinstance(inline, list) and len(inline) > max_items:
        warnings.append(f"$.inline：仅校验前 {max_items} 条（总计 {len(inline)} 条）")

    return errors, warnings


def validate_diff_hits(
    *, glab: str, host: str, repo: str, iid: int, inline: List[Dict[str, Any]], max_items: int
) -> List[Tuple[str, str, int]]:
    diff_text = fetch_latest_diff(glab, host, repo, iid)
    raw_ranges = parse_valid_new_line_ranges(diff_text)
    ranges = { _normalize_diff_path(k): v for k, v in raw_ranges.items() }

    misses: List[Tuple[str, str, int]] = []
    items = inline[: max_items if max_items > 0 else len(inline) ]
    for i, it in enumerate(items):
        p = it.get("new_path")
        ln = it.get("new_line")
        if not isinstance(p, str) or not isinstance(ln, int):
            continue
        p2 = _normalize_diff_path(p)
        if not line_hits_current_diff(ranges, p2, ln):
            misses.append((f"$.inline[{i}]", p, ln))
    return misses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", required=True)
    ap.add_argument("--context")
    ap.add_argument("--glab")
    ap.add_argument("--check-diff", choices=["off", "warn", "fail"], default="off")
    ap.add_argument("--max-items", type=int, default=200)
    args = ap.parse_args()

    review = load_json(Path(args.review))
    errors, warnings = validate_schema(review, max_items=args.max_items)

    diff_misses: List[Tuple[str, str, int]] = []
    if args.check_diff != "off":
        if not args.context:
            errors.append("$：启用 diff 校验需要提供 --context")
        else:
            ctx = load_json(Path(args.context))
            host = _as_text(ctx.get("host"))
            repo = _as_text(ctx.get("repo"))
            iid_raw = ctx.get("mr_iid")
            if not host or not repo or not isinstance(iid_raw, int):
                errors.append("$：context.json 缺少 host/repo/mr_iid")
            else:
                glab = _which_glab(args.glab)
                inline = review.get("inline") if isinstance(review, dict) else None
                if isinstance(inline, list):
                    diff_misses = validate_diff_hits(
                        glab=glab, host=host, repo=repo, iid=iid_raw, inline=inline, max_items=args.max_items
                    )

    ok = len(errors) == 0

    if ok:
        status = "OK"
    else:
        status = "FAILED"

    print(f"Review 校验结果: {status}")
    print(f"  文件: {args.review}")
    print(f"  Errors: {len(errors)}")
    warn_count = len(warnings) + (len(diff_misses) if args.check_diff == 'warn' else 0)
    print(f"  Warnings: {warn_count}")

    for e in errors:
        print(f"[ERROR] {e}")

    for w in warnings:
        print(f"[WARN ] {w}")

    if args.check_diff != "off" and diff_misses:
        for path, p, ln in diff_misses[: min(len(diff_misses), 50)]:
            print(f"[WARN ] {path}：未命中当前 MR diff hunk（{p}:{ln}），可能无法回写为 inline")

        if args.check_diff == "fail":
            raise SystemExit(3)

    if not ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
