#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""将 review.json 回写到 GitLab MR（note + inline discussions）。

输入：
- --context <context.json>（由 glab_mr_fetch.py 生成）
- --review <review.json>

review.json 结构：
{
  "note": "markdown...",
  "inline": [
    {"new_path": "path/to/file", "new_line": 123, "body": "评论 markdown..."}
  ]
}

行为：
- 仅在 --confirm 传入时才会执行写操作。
- 未传 --confirm：只预览将要写回的内容（不会发任何请求）。
- 回写前会自动刷新最新 MR diff_refs / head_sha。
- inline 只对当前 diff hunk 仍然有效的位置发 discussion；失效项自动降级到 note。
- note 中的 [file:line] 会自动转换为可点击的 GitLab blob 链接。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple
from urllib.parse import quote

from glab_mr_fetch import api_get_json_mr_detail_with_fallback, find_project_id


FILE_LINE_RE = re.compile(r"\[(?P<path>[^\]\n]+):(?P<line>\d+)\](?!\()")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


def normalize_diff_path(p: str) -> str:
    """规范化 diff/path：去掉 a/ b/ 前缀，反斜杠转正斜杠。"""
    s = str(p).strip().replace("\\", "/")
    if s.startswith("a/") or s.startswith("b/"):
        s = s[2:]
    return s


def _which_glab(explicit: str | None) -> str:
    if explicit:
        return explicit
    p = shutil.which("glab")
    if p:
        return p
    raise SystemExit("找不到 glab：请先安装并加入 PATH，或使用 --glab 指定 glab.exe 路径。")


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> Tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    out = p.stdout.decode("utf-8", "replace")
    return p.returncode, out


def _print_json_decode_error(path: Path, text: str, e: json.JSONDecodeError) -> None:
    lines = text.splitlines()
    lineno = max(1, int(getattr(e, "lineno", 1)))
    colno = max(1, int(getattr(e, "colno", 1)))

    start = max(1, lineno - 1)
    end = min(len(lines), lineno + 1)

    print("[ERROR] JSON 解析失败，无法继续。")
    print(f"  文件: {path}")
    print(f"  位置: 第 {lineno} 行, 第 {colno} 列")
    print(f"  原因: {e.msg}")
    print("")
    print("  上下文：")
    for n in range(start, end + 1):
        content = lines[n - 1] if 0 <= n - 1 < len(lines) else ""
        print(f"  {n:>6} | {content}")
        if n == lineno:
            caret = " " * (colno - 1) + "^"
            print(f"  {'':>6} | {caret}")

    print("")
    print("  常见原因排查：")
    print("  - 缺逗号：{\"a\": 1 \"b\": 2}")
    print("  - 引号未闭合：\"body\": \"text")
    print("  - 尾逗号（JSON 不允许）：{\"a\": 1,}")
    print("  - 粘贴多行内容时引入未转义字符")


def load_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        _print_json_decode_error(path, text, e)
        raise SystemExit(2)


def _sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def make_inline_dedupe_marker(new_path: str, new_line: int, body: str) -> str:
    """为“每条 inline 唯一”生成稳定去重 marker。

    约定：marker 形如 `<!-- cc-review:<sha1> -->`
    - sha1 输入：f"{new_path}:{new_line}:{issue_summary}"（issue_summary 基于 body 首个非空行提取）
    - 目的：同一位置同一问题再次运行时可跳过；不同 inline 不会互相误伤。

    注意：这里不使用用户传入的 --dedupe-tag 作为唯一键（它可能是一个固定前缀）。
    """
    norm_path = normalize_diff_path(str(new_path))
    summary = extract_issue_summary(str(body))
    h = _sha1_hex(f"{norm_path}:{int(new_line)}:{summary}")
    return f"<!-- cc-review:{h} -->"


def append_dedupe_tag(body: str, tag: str | None) -> str:
    """兼容旧行为：将用户传入的 tag 追加到 body 末尾。"""
    if not tag:
        return body
    marker = f"<!-- {tag} -->"
    if marker in body:
        return body
    return body.rstrip() + "\n\n" + marker + "\n"


def list_existing_discussion_bodies(glab: str, host: str, project_id: int, iid: int) -> list[str]:
    endpoint = f"/projects/{project_id}/merge_requests/{iid}/discussions?include_diff=true&per_page=100"
    code, out = _run([glab, "api", "--hostname", host, endpoint, "--output", "json"])
    if code != 0:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []

    bodies: list[str] = []
    for d in data or []:
        for n in d.get("notes") or []:
            b = n.get("body")
            if isinstance(b, str):
                bodies.append(b)
    return bodies


def build_blob_url(host: str, repo: str, head_sha: str, file_path: str, line: int) -> str:
    repo_part = quote(repo, safe="/")
    path_part = quote(file_path, safe="/")
    return f"https://{host}/{repo_part}/-/blob/{head_sha}/{path_part}#L{line}"


def rewrite_note_links(note: str, host: str, repo: str, head_sha: str) -> str:
    def repl(match: re.Match[str]) -> str:
        file_path = normalize_diff_path(match.group("path"))
        line = int(match.group("line"))
        label = f"{file_path}:{line}"
        return f"[{label}]({build_blob_url(host, repo, head_sha, file_path, line)})"

    return FILE_LINE_RE.sub(repl, note)


def extract_issue_summary(body: str) -> str:
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\*\*问题\*\*[:：]\s*", "", line)
        return line
    return "该条 inline 在当前 diff 中已失效，已降级为普通评论。"


def append_degraded_inline_section(
    note: str,
    degraded: list[Dict[str, Any]],
    host: str,
    repo: str,
    head_sha: str,
) -> str:
    if not degraded:
        return note

    lines = [
        "",
        "## 未能锚定到当前 diff 的评论（已降级到总体 note）",
        "- 说明：这些评论对应的 `(new_path, new_line)` 已不在当前 MR 最新 diff hunk 中，因此没有再强制发 inline，避免只出现在时间线。",
    ]
    for item in degraded:
        path = normalize_diff_path(str(item["new_path"]))
        line = int(item["new_line"])
        summary = extract_issue_summary(str(item["body"]))
        link = build_blob_url(host, repo, head_sha, path, line)
        lines.append(f"- [{path}:{line}]({link}) {summary}")
    return note.rstrip() + "\n" + "\n".join(lines) + "\n"


def refresh_context(glab: str, context: Dict[str, Any]) -> Dict[str, Any]:
    host = context["host"]
    repo = context["repo"]
    iid = int(context["mr_iid"])
    project_id = int(context.get("project_id") or find_project_id(glab, host, repo))
    mr = api_get_json_mr_detail_with_fallback(glab, host, project_id, iid)
    diff_refs = mr.get("diff_refs") or {}
    return {
        "host": host,
        "repo": repo,
        "mr_iid": iid,
        "project_id": project_id,
        "diff_refs": {
            "base_sha": diff_refs.get("base_sha"),
            "start_sha": diff_refs.get("start_sha"),
            "head_sha": diff_refs.get("head_sha"),
        },
    }


def fetch_mr_changes(glab: str, host: str, project_id: int, iid: int) -> Dict[str, Any]:
    """通过 glab api 拉取 MR changes（统一走 GitLab REST）。"""
    endpoint = f"/projects/{project_id}/merge_requests/{iid}/changes?per_page=100"
    code, out = _run([glab, "api", "--hostname", host, endpoint, "--output", "json"])
    if code != 0:
        raise RuntimeError(f"获取 MR changes 失败：\n{out}")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"解析 MR changes JSON 失败：{e}\n{out[:500]}")


def collect_valid_new_lines_from_diff(diff_text: str) -> Set[int]:
    """从单个文件的 unified diff 中逐行计算“有效 new_line”集合。

    规则（正确的 unified diff hunk 扫描）：
    - 遇到 hunk 头（@@ -old +new @@）时，将 new_line 游标设为 new_start。
    - 随后逐行扫描：
      - 以空格 ' ' 开头（上下文行）：记录当前 new_line，并推进 +1。
      - 以加号 '+' 开头（新增行，排除 +++ 文件头）：记录当前 new_line，并推进 +1。
      - 以减号 '-' 开头（删除行，排除 --- 文件头）：不推进 new_line。
      - 其他元信息行（如 "\\ No newline at end of file"）：不推进。
    - hunk 的边界不依赖 new_len/count，而是以遇到下一个 @@ 或 diff 结束为准。

    说明：GitLab 的 discussion position[new_line] 需要的是“目标文件（new）”的行号。
    """
    valid: set[int] = set()

    new_line_no: int | None = None

    for raw in diff_text.splitlines():
        m = HUNK_RE.match(raw)
        if m:
            new_line_no = int(m.group("start"))
            continue

        # 未进入任何 hunk，则跳过（例如索引/文件头等）
        if new_line_no is None:
            continue

        # diff 内容行通常以 ' ', '+', '-' 开头；也可能是 "\\ No newline..." 这类元信息
        if raw.startswith("+++") or raw.startswith("---"):
            continue

        if raw.startswith("+"):
            valid.add(new_line_no)
            new_line_no += 1
        elif raw.startswith(" "):
            valid.add(new_line_no)
            new_line_no += 1
        elif raw.startswith("-"):
            # 删除行只消耗 old line，不影响 new_line_no
            continue
        else:
            continue

    return valid


def build_valid_new_line_map_from_changes(changes_json: Dict[str, Any]) -> Dict[str, Set[int]]:
    """基于 MR changes[].diff 构建 {path -> set(valid_new_line)}。"""
    valid_map: Dict[str, Set[int]] = {}
    for ch in changes_json.get("changes") or []:
        new_path = ch.get("new_path")
        if not new_path:
            continue
        diff_text = ch.get("diff") or ""
        norm_path = normalize_diff_path(str(new_path))
        valid_map[norm_path] = collect_valid_new_lines_from_diff(str(diff_text))
    return valid_map


def split_inline_items(
    items: Iterable[Dict[str, Any]],
    valid_map: Dict[str, Set[int]],
) -> Tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    valid_items: list[Dict[str, Any]] = []
    degraded_items: list[Dict[str, Any]] = []

    for it in items:
        new_path = it.get("new_path")
        new_line_raw = it.get("new_line")
        body = it.get("body")
        if not (new_path and new_line_raw is not None and body):
            raise SystemExit(f"inline 条目缺字段：{it}")

        try:
            new_line = int(new_line_raw)
        except (TypeError, ValueError):
            raise SystemExit(f"inline 条目 new_line 不是整数：{it}")

        norm_path = normalize_diff_path(str(new_path))
        normalized = {
            "new_path": norm_path,
            "new_line": new_line,
            "body": str(body),
        }

        if new_line in valid_map.get(norm_path, set()):
            valid_items.append(normalized)
        else:
            degraded_items.append(normalized)

    return valid_items, degraded_items


def preview(
    original_context: Dict[str, Any],
    refreshed_context: Dict[str, Any],
    note: str,
    inline_ready: list[Dict[str, Any]],
    inline_degraded: list[Dict[str, Any]],
) -> None:
    host = refreshed_context.get("host")
    repo = refreshed_context.get("repo")
    iid = refreshed_context.get("mr_iid")
    old_refs = (original_context.get("diff_refs") or {})
    new_refs = (refreshed_context.get("diff_refs") or {})

    print("将要回写到 GitLab：")
    print(f"- host: {host}")
    print(f"- repo: {repo}")
    print(f"- mr_iid: {iid}")
    print(
        "- 最新 diff_refs: "
        f"base={new_refs.get('base_sha')} start={new_refs.get('start_sha')} head={new_refs.get('head_sha')}"
    )
    if old_refs != new_refs:
        print("- 已刷新为最新 MR 版本（当前 diff_refs 与输入 context.json 不同）。")
    else:
        print("- 当前 MR 版本与输入 context.json 一致。")
    print(f"- note 长度: {len(note)} 字")
    print(f"- inline 可回写条数: {len(inline_ready)}")
    print(f"- inline 降级到 note 条数: {len(inline_degraded)}")

    if inline_ready:
        print("\nInline 预览（最多 5 条）：")
        for i, it in enumerate(inline_ready[:5], 1):
            print(f"[{i}] {it.get('new_path')}:{it.get('new_line')}  body_len={len(it.get('body') or '')}")

    if inline_degraded:
        print("\n降级项预览（最多 5 条）：")
        for i, it in enumerate(inline_degraded[:5], 1):
            print(f"[{i}] {it.get('new_path')}:{it.get('new_line')}  reason=not_in_current_diff_hunk")


def write_note(glab: str, host: str, repo: str, iid: int, note: str) -> None:
    env = os.environ.copy()
    env["GITLAB_HOST"] = host
    code, out = _run([glab, "mr", "note", str(iid), "-R", repo, "-m", note], env=env)
    if code != 0:
        raise SystemExit(f"回写 MR note 失败：\n{out}")


def write_inline(glab: str, host: str, project_id: int, iid: int, diff_refs: Dict[str, Any], items: list[Dict[str, Any]], *, dedupe_tag: str | None) -> int:
    base_sha = diff_refs.get("base_sha")
    start_sha = diff_refs.get("start_sha")
    head_sha = diff_refs.get("head_sha")
    if not (base_sha and start_sha and head_sha):
        raise SystemExit("最新 MR diff_refs 不完整（base/start/head sha）。")

    endpoint = f"/projects/{project_id}/merge_requests/{iid}/discussions?include_diff=true"
    existing_bodies = list_existing_discussion_bodies(glab, host, project_id, iid) if dedupe_tag else []
    written = 0

    for it in items:
        new_path = it.get("new_path")
        new_line = int(it.get("new_line"))
        body_text = str(it.get("body"))

        unique_marker = make_inline_dedupe_marker(str(new_path), new_line, body_text) if dedupe_tag else None
        if unique_marker and any(unique_marker in b for b in existing_bodies):
            continue

        body = body_text
        if dedupe_tag:
            body = append_dedupe_tag(body, dedupe_tag)
            if unique_marker and unique_marker not in body:
                body = body.rstrip() + "\n\n" + unique_marker + "\n"

        norm_path = normalize_diff_path(str(new_path))
        payload = {
            "body": body,
            "position": {
                "position_type": "text",
                "base_sha": base_sha,
                "start_sha": start_sha,
                "head_sha": head_sha,
                "old_path": norm_path,
                "new_path": norm_path,
                "new_line": new_line,
                "line_range": {
                    "start": {"type": "new", "new_line": new_line},
                    "end": {"type": "new", "new_line": new_line},
                },
            },
        }

        cmd = [
            glab,
            "api",
            "--hostname",
            host,
            "--method",
            "POST",
            endpoint,
            "--header",
            "Content-Type: application/json",
            "--input",
            "-",
            "--output",
            "json",
        ]

        p = subprocess.run(
            cmd,
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        out = p.stdout.decode("utf-8", "replace")
        if p.returncode != 0:
            raise SystemExit(f"回写 inline discussion 失败：{new_path}:{new_line}\n{out}")

        written += 1

    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="回写 GitLab MR review（需要最终确认）")
    ap.add_argument("--context", required=True, help="context.json 路径")
    ap.add_argument("--review", required=True, help="review.json 路径")
    ap.add_argument("--glab", default=None, help="可选：glab 或 glab.exe 绝对路径")
    ap.add_argument("--confirm", action="store_true", help="确认执行回写（未传则只预览）")
    ap.add_argument(
        "--dedupe-tag",
        default=None,
        help="可选：为每条 inline body 追加去重 tag（例如 cc-review:abcd1234）。再次运行会跳过已存在同 tag 的讨论。",
    )
    args = ap.parse_args()

    glab = _which_glab(args.glab)
    original_context = load_json(Path(args.context))
    review = load_json(Path(args.review))
    refreshed_context = refresh_context(glab, original_context)

    host = refreshed_context["host"]
    repo = refreshed_context["repo"]
    iid = int(refreshed_context["mr_iid"])
    project_id = int(refreshed_context["project_id"])
    diff_refs = refreshed_context.get("diff_refs") or {}
    head_sha = diff_refs.get("head_sha")
    if not head_sha:
        raise SystemExit("最新 MR 缺少 head_sha，无法生成 note 链接。")

    note = rewrite_note_links(str(review.get("note") or ""), host, repo, head_sha)
    inline = review.get("inline") or []

    inline_ready: list[Dict[str, Any]] = []
    inline_degraded: list[Dict[str, Any]] = []
    if inline:
        try:
            changes_json = fetch_mr_changes(glab, host, project_id, iid)
            valid_map = build_valid_new_line_map_from_changes(changes_json)
        except RuntimeError as exc:
            print(f"警告：{exc}")
            print("警告：由于无法获取最新 changes，所有 inline 都将降级到总体 note。")
            valid_map = {}

        inline_ready, inline_degraded = split_inline_items(inline, valid_map)
        note = append_degraded_inline_section(note, inline_degraded, host, repo, head_sha)

    preview(original_context, refreshed_context, note, inline_ready, inline_degraded)

    if not args.confirm:
        print("\n未传 --confirm：本次仅预览，不会回写 GitLab。")
        return

    if note.strip():
        write_note(glab, host, repo, iid, note)
        print("已回写 MR note。")

    if inline_ready:
        written = write_inline(glab, host, project_id, iid, diff_refs, inline_ready, dedupe_tag=args.dedupe_tag)
        print(f"已回写 inline discussions：{written} 条。")
    else:
        print("没有可回写的 inline discussions。")

    if inline_degraded:
        print(f"已降级到 note 的 inline：{len(inline_degraded)} 条。")


if __name__ == "__main__":
    main()
