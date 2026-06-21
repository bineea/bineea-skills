# -*- coding: utf-8 -*-
"""TDD: 针对 kb_qa_loop 的“起手式/输入方式”文本约束测试。

目标：不再提示“原始问题选择器”，而是把 slash 后面的文本直接当作 original_question。

运行方式：
  python C:/Users/guowb1/.claude/skills/kb-qa-loop/tests/test_skill_uses_slash_arg_as_question.py

说明：
- 这里无法自动测试 Claude Code UI 行为，只能测试 SKILL.md 是否明确写出该交互约束。
"""

from __future__ import annotations

from pathlib import Path


def test_skill_uses_slash_arg_as_question() -> None:
    skill_path = Path(r"C:\Users\guowb1\.claude\skills\kb-qa-loop\SKILL.md")
    assert skill_path.exists(), f"SKILL.md 不存在: {skill_path}"

    content = skill_path.read_text(encoding="utf-8")

    assert "slash" in content or "Slash" in content or "/kb_qa_loop" in content, "缺少：说明 slash 调用方式（/kb_qa_loop ...）"
    assert "后面" in content and ("直接" in content or "视为" in content), "缺少：slash 后面文本直接作为问题的规则"
    assert "原始问题" in content and ("不再" in content or "不需要" in content) and ("选择器" in content or "选项" in content), "缺少：不再弹原始问题选择器的说明"


if __name__ == "__main__":
    try:
        test_skill_uses_slash_arg_as_question()
    except AssertionError as e:
        raise SystemExit(f"TEST FAILED: {e}")

    print("OK")
