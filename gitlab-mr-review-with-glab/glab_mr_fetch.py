#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""拉取 GitLab MR 元信息与 diff，并产出后续回写所需的关键信息。

输出目录结构（默认 out_dir）：
- mr.json            # MR 详情（含 diff_refs）
- project.json       # 项目详情（含 project_id）
- changes.txt        # mr changes 输出（若可用）
- diff.txt           # mr diff 输出（patch）
- context.json       # 归一化后的上下文：host/repo/iid/project_id/diff_refs

说明：
- 只做读取（GET）；不回写。
- 优先使用 PATH 中的 glab；可用 --glab 指定绝对路径。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Tuple


MR_URL_RE = re.compile(
    r"^https?://(?P<host>[^/]+)/(?P<repo>.+?)/-/merge_requests/(?P<iid>\d+)(?:/.*)?$"
)


DEFAULT_GLAB_WINDOWS = "D:/ProgramFiles/glab/glab.exe"


def _which_glab(explicit: str | None, *, auto: bool) -> str:
    if explicit:
        return explicit

    if auto:
        if Path(DEFAULT_GLAB_WINDOWS).exists():
            return DEFAULT_GLAB_WINDOWS

    p = shutil.which("glab")
    if p:
        return p
    raise SystemExit("找不到 glab：请先安装并加入 PATH，或使用 --glab 指定 glab.exe 路径。")


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> Tuple[int, str, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    return p.returncode, out, err


def parse_mr_url(url: str) -> Tuple[str, str, int]:
    m = MR_URL_RE.match(url.strip())
    if not m:
        raise SystemExit(
            "MR URL 解析失败。期望格式：https://<host>/<group>/<project>/-/merge_requests/<iid>"
        )
    host = m.group("host")
    repo = m.group("repo")
    iid = int(m.group("iid"))
    return host, repo, iid


def ensure_out_dir(out_dir: str) -> Path:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def save_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_json(text: str) -> Dict[str, Any]:
    s = text.strip()
    if not s:
        raise json.JSONDecodeError("empty", text, 0)

    # 直接尝试解析（理想路径）
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # 容错：glab 有时会把提示/telemetry 输出混到 stdout；尝试从最后一个 JSON 对象开始解析
    start = s.rfind("{")
    if start >= 0:
        tail = s[start:]
        return json.loads(tail)

    raise json.JSONDecodeError("no json object", text, 0)


def api_get_json(glab: str, host: str, endpoint: str) -> Dict[str, Any]:
    code, out, err = _run([glab, "api", "--hostname", host, endpoint, "--output", "json"])
    if code != 0:
        raise SystemExit(f"glab api GET 失败：{endpoint}\n{out}{err}")
    try:
        return _extract_json(out)
    except json.JSONDecodeError:
        raise SystemExit(f"API 返回不是 JSON：{endpoint}\n{out}{err}")


def api_get_json_mr_detail_with_fallback(
    glab: str, host: str, project_id: int, iid: int
) -> Dict[str, Any]:
    """获取 MR 详情（含 diff_refs），并处理部分实例“列表可见但详情 404”的情况。"""

    base_ep = f"/projects/{project_id}/merge_requests/{iid}"

    # 1) 直连
    try:
        return api_get_json(glab, host, base_ep)
    except SystemExit as e:
        msg = str(e)
        if "HTTP 404" not in msg:
            raise

    # 2) 探针：列表确认
    _ = api_get_json(glab, host, f"/projects/{project_id}/merge_requests?state=opened&per_page=100")

    # 3) 带 query fallback
    return api_get_json(glab, host, base_ep + "?include_diverged_commits_count=true")


def find_project_id(glab: str, host: str, repo: str) -> int:
    # repo = group/project；GitLab API 中 projects/:id 可用 URL-encoded full path
    encoded = repo.replace("/", "%2F")
    proj = api_get_json(glab, host, f"/projects/{encoded}")
    pid = proj.get("id")
    if not isinstance(pid, int):
        raise SystemExit(f"无法从 /projects/<path> 获取项目 id：repo={repo}")
    return pid


def mr_view(glab: str, host: str, repo: str, iid: int, out_dir: Path) -> None:
    env = os.environ.copy()
    env["GITLAB_HOST"] = host

    # 1) MR 详情：用 API（稳定且含 diff_refs）
    project_id = find_project_id(glab, host, repo)
    project = api_get_json(glab, host, f"/projects/{project_id}")
    mr = api_get_json_mr_detail_with_fallback(glab, host, project_id, iid)

    save_json(out_dir / "project.json", project)
    save_json(out_dir / "mr.json", mr)

    # 2) mr changes（尽量获取；失败不阻断）
    code, changes_out, changes_err = _run([glab, "mr", "changes", str(iid), "-R", repo], env=env)
    if code == 0:
        save_text(out_dir / "changes.txt", changes_out)
        if changes_err.strip():
            save_text(out_dir / "changes.stderr.txt", changes_err)
    else:
        save_text(out_dir / "changes.error.txt", changes_out + changes_err)

    # 3) mr diff（patch 文本）
    code, diff_out, diff_err = _run([glab, "mr", "diff", str(iid), "-R", repo], env=env)
    if code != 0:
        raise SystemExit(f"glab mr diff 失败：\n{diff_out}{diff_err}")
    save_text(out_dir / "diff.txt", diff_out)
    if diff_err.strip():
        save_text(out_dir / "diff.stderr.txt", diff_err)

    diff_refs = mr.get("diff_refs") or {}
    context = {
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
    save_json(out_dir / "context.json", context)


def main() -> None:
    ap = argparse.ArgumentParser(description="拉取 GitLab MR 信息与 diff（只读）")
    ap.add_argument("--mr", required=True, help="MR URL，例如 https://host/group/project/-/merge_requests/123")
    ap.add_argument("--out", default="mr_review_out", help="输出目录（默认：mr_review_out）")
    ap.add_argument("--glab", default=None, help="可选：glab 或 glab.exe 绝对路径")
    ap.add_argument(
        "--glab-auto",
        action="store_true",
        default=True,
        help=f"优先探测 {DEFAULT_GLAB_WINDOWS}（默认开启），找不到再 fallback 到 PATH 中的 glab；如需关闭请输入 --no-glab-auto",
    )
    ap.add_argument(
        "--no-glab-auto",
        action="store_false",
        dest="glab_auto",
        help="禁用默认 glab 自动探测，仅使用 --glab 或 PATH 中的 glab",
    )
    args = ap.parse_args()

    glab = _which_glab(args.glab, auto=bool(args.glab_auto))
    host, repo, iid = parse_mr_url(args.mr)
    out_dir = ensure_out_dir(args.out)

    mr_view(glab, host, repo, iid, out_dir)
    print(f"已写出：{out_dir}")
    print(f"- diff: {out_dir / 'diff.txt'}")
    print(f"- context: {out_dir / 'context.json'}")


if __name__ == "__main__":
    main()
