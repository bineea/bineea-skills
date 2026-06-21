#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""读取 diff.txt，生成空白/模板化的 review.json。

目的：
- 固化 review.json 结构
- 根据 diff hunks 推断更合理的 new_line，占位生成 inline 项（仍不保证 100% 精确）
- 便于后续人工/Claude 填充内容，再用 glab_mr_writeback.py 回写

用法：
  python glab_mr_review_draft.py --diff mr_review_out/diff.txt --out review.json

说明：
- 该脚本不会联网、不会调用 glab，只做本地文本解析。
- inline 的 new_line 会从 diff hunks 自动推断（优先取每个 hunk 的第一条新增行/起始新增行）；仍建议你在回写前人工核对。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


# glab mr diff 输出不一定带 a/ b/ 前缀：同时兼容 "+++ b/path" 与 "+++ path"
DIFF_FILE_RE = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<new_start>\d+)(?:,(?P<new_len>\d+))? @@")


def extract_files(diff_text: str) -> List[str]:
    files: List[str] = []
    seen = set()
    for line in diff_text.splitlines():
        m = DIFF_FILE_RE.match(line)
        if not m:
            continue
        path = m.group(1).strip()
        if path == "/dev/null":
            continue
        if path not in seen:
            seen.add(path)
            files.append(path)
    return files


def infer_new_lines_by_file(diff_text: str) -> Dict[str, List[int]]:
    """从 unified diff 中推断每个文件的可用 new_line 候选（优先新增行）。

    策略（更贴合 GitLab inline 定位）：
    - 逐个解析 hunk（@@ ... +new_start,... @@）。
    - **优先只从“存在新增行（+）”的 hunk 中取候选**：记录该 hunk 内第一条新增行对应的 new_line。
    - 若某文件所有 hunk 都没有新增行（例如纯删除），则回退到各 hunk 的 new_start 作为候选。

    返回：{new_path: [line1, line2, ...]}（按出现顺序，去重）
    """

    current_file: str | None = None

    # 每个文件的候选列表：优先新增行候选；fallback 为 new_start 候选
    plus_candidates: Dict[str, List[int]] = {}
    start_candidates: Dict[str, List[int]] = {}

    hunk_new_line: int | None = None  # 当前 hunk 的 new 文件行游标
    hunk_has_plus = False

    def _push(map_: Dict[str, List[int]], path: str, line_no: int) -> None:
        lst = map_.setdefault(path, [])
        if line_no not in lst:
            lst.append(line_no)

    for raw in diff_text.splitlines():
        line = raw.rstrip("\n")

        m_file = DIFF_FILE_RE.match(line)
        if m_file:
            path = m_file.group(1).strip()
            if path == "/dev/null":
                current_file = None
                hunk_new_line = None
                hunk_has_plus = False
                continue
            current_file = path
            hunk_new_line = None
            hunk_has_plus = False
            continue

        if current_file is None:
            continue

        m_hunk = DIFF_HUNK_RE.match(line)
        if m_hunk:
            new_start = int(m_hunk.group("new_start"))
            _push(start_candidates, current_file, new_start)
            hunk_new_line = new_start
            hunk_has_plus = False
            continue

        if hunk_new_line is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            if not hunk_has_plus:
                _push(plus_candidates, current_file, hunk_new_line)
                hunk_has_plus = True
            hunk_new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass
        else:
            hunk_new_line += 1

    # 合并结果：有新增行候选就用它；否则用 new_start 候选
    results: Dict[str, List[int]] = {}
    for path in set(list(plus_candidates.keys()) + list(start_candidates.keys())):
        if plus_candidates.get(path):
            results[path] = plus_candidates[path]
        else:
            results[path] = start_candidates.get(path, [])

    return results


def build_note_template() -> str:
    return (
        "## 总体结论\n"
        "- 风险等级：P0 ×0 / P1 ×0 / P2 ×0\n"
        "- 关注范围：仅基于本 MR 的已变更代码（diff）\n\n"
        "## P0（阻断合并）\n"
        "- （待填写）\n\n"
        "## P1（建议修复）\n"
        "- （待填写）\n\n"
        "## P2（可选优化）\n"
        "- （待填写）\n\n"
        "## 复用性/质量/效率概览\n"
        "- 复用性：（待填写，按模块归类）\n"
        "- 质量：（待填写：可维护性/边界处理/测试缺口）\n"
        "- 效率：（待填写：热路径/浪费点，写清触发条件）\n"
    )


def build_inline_template(new_path: str, new_line: int) -> Dict[str, Any]:
    body = (
        "**问题**：（待填写：这里新增了 X——重复逻辑/复杂分支/潜在 N+1/热路径阻塞 等）\n\n"
        "**影响**：（待填写：会导致 Y——维护成本/一致性风险/性能回归/难测/回归风险 等）\n\n"
        "**建议**：\n"
        "- 优先：（待填写：复用/替换为现有 util/模块/模式；或抽取为函数/统一抽象）\n"
        "- 次选：（待填写：若保留现实现，至少加 guard/缓存/并发/测试/常量化 等）\n"
    )
    return {"new_path": new_path, "new_line": int(new_line), "body": body}


def main() -> None:
    ap = argparse.ArgumentParser(description="从 diff.txt 生成模板 review.json")
    ap.add_argument("--diff", required=True, help="diff.txt 路径（由 glab_mr_fetch.py 生成）")
    ap.add_argument("--out", default="review.json", help="输出 review.json 路径（默认：review.json）")
    ap.add_argument(
        "--inline-per-file",
        type=int,
        default=1,
        help="每个文件生成几条 inline 占位（默认 1）",
    )
    args = ap.parse_args()

    diff_path = Path(args.diff)
    diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
    files = extract_files(diff_text)
    new_lines_by_file = infer_new_lines_by_file(diff_text)

    inline: List[Dict[str, Any]] = []
    for f in files:
        candidates = new_lines_by_file.get(f) or [1]
        for i in range(max(1, args.inline_per_file)):
            new_line = candidates[min(i, len(candidates) - 1)]
            inline.append(build_inline_template(f, new_line))

    review = {
        "note": build_note_template(),
        "inline": inline,
        "meta": {
            "generated_from": str(diff_path),
            "files": files,
            "inline_per_file": args.inline_per_file,
            "warning": "new_line 已从 diff hunks 推断生成；回写前仍建议人工核对行号是否可在 GitLab 上正确定位。",
        },
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成模板：{out_path}")
    print(f"- 文件数：{len(files)}")
    print(f"- inline 占位条数：{len(inline)}")


if __name__ == "__main__":
    main()
