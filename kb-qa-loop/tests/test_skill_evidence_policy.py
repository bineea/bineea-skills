# -*- coding: utf-8 -*-
"""TDD: 针对 SKILL.md 中“证据裁剪策略”的最小测试。

目标：把证据策略固定为
- 检索 topk=10
- 进入 judge/answer 的 items_min 最多 10 条
- 不做 text 截断

运行方式：
  python C:/Users/guowb1/.claude/skills/kb-qa-loop/tests/test_skill_evidence_policy.py

说明：
- 不依赖 pytest，仅做纯文本断言。
- 该测试用于防止 SKILL.md 被改回“最多 3 条 + 截断 1200 字”。
"""

from __future__ import annotations

from pathlib import Path


def test_skill_evidence_policy() -> None:
    skill_path = Path(r"C:\Users\guowb1\.claude\skills\kb-qa-loop\SKILL.md")
    assert skill_path.exists(), f"SKILL.md 不存在: {skill_path}"

    content = skill_path.read_text(encoding="utf-8")
    normalized = content.replace(" ", "")

    assert "--topk" in content, "缺少：检索命令中使用 --topk"
    assert "topk=10" in normalized or "--topk10" in normalized, "缺少：topk 固定为 10（topk=10 或 --topk 10）"

    assert "items_min" in content, "缺少：items_min[] 的产物要求"
    assert "最多10" in normalized or "最多10条" in normalized or "最多10條" in normalized, "缺少：items_min[] 最多 10 条的要求"

    assert "截断" in content, "缺少：提到 text 截断策略（用于明确本策略不截断）"
    assert ("不截断" in content) or ("不做截断" in content), "缺少：明确声明不截断"


if __name__ == "__main__":
    try:
        test_skill_evidence_policy()
    except AssertionError as e:
        raise SystemExit(f"TEST FAILED: {e}")

    print("OK")
