# -*- coding: utf-8 -*-
"""TDD: 当 judge 判定 sufficient=true 时，必须进入最终回答输出。

目标：防止出现“只说不需要追问，但没有最终回答”的中间态。

运行方式：
  python C:/Users/guowb1/.claude/skills/kb-qa-loop/tests/test_skill_must_answer_when_sufficient.py

说明：
- 只能对 SKILL.md 的流程规范做文本断言（无法直接测试 Claude Code UI）。
"""

from __future__ import annotations

from pathlib import Path


def test_skill_must_answer_when_sufficient() -> None:
    skill_path = Path(r"C:\Users\guowb1\.claude\skills\kb-qa-loop\SKILL.md")
    assert skill_path.exists(), f"SKILL.md 不存在: {skill_path}"

    content = skill_path.read_text(encoding="utf-8")

    assert "sufficient=true" in content or "sufficient为true" in content or "sufficient 为 true" in content, "缺少：提到 sufficient=true 的分支"
    assert ("必须" in content) and ("最终回答" in content) and ("kb_answer_with_citations.md" in content or "prompts/kb_answer_with_citations.md" in content), "缺少：sufficient=true 时必须输出最终回答（且用 kb_answer_with_citations.md）"
    assert "不得" in content and ("仅" in content) and ("不需要追问" in content or "无需追问" in content), "缺少：禁止停在“无需追问/不需要追问”的中间态"


if __name__ == "__main__":
    try:
        test_skill_must_answer_when_sufficient()
    except AssertionError as e:
        raise SystemExit(f"TEST FAILED: {e}")

    print("OK")
