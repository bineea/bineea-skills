# -*- coding: utf-8 -*-
"""TDD: SKILL.md 必须规定“对用户不回显 judge JSON”。

目标：
- 运行时内部仍可产生 judge_decision JSON
- 但对用户侧：
  - sufficient=false -> 仅展示自然语言澄清问题（1-2 个），不展示 JSON
  - sufficient=true -> 仅展示最终回答（由 kb_answer_with_citations.md 生成），不展示 JSON

运行方式：
  python C:/Users/guowb1/.claude/skills/kb-qa-loop/tests/test_skill_user_facing_output_policy.py

说明：
- 该测试只能约束 SKILL.md 的“输出策略”文档要求（无法直接测试 Claude Code UI）。
"""

from __future__ import annotations

from pathlib import Path


def test_skill_user_facing_output_policy() -> None:
    skill_path = Path(r"C:\Users\guowb1\.claude\skills\kb-qa-loop\SKILL.md")
    assert skill_path.exists(), f"SKILL.md 不存在: {skill_path}"

    content = skill_path.read_text(encoding="utf-8")
    normalized = content.replace(" ", "")

    assert "judge" in content and "JSON" in content, "缺少：提到 judge JSON 的存在与内部处理"
    assert ("不回显" in content) or ("不展示" in content) or ("不要输出" in content), "缺少：不向用户展示 judge JSON 的约束"
    assert ("仅" in content) and ("自然语言" in content) and ("追问" in content or "澄清" in content), "缺少：insufficient 时仅自然语言追问的约束"
    assert "kb_answer_with_citations.md" in content, "缺少：最终回答仍必须由 kb_answer_with_citations.md 生成"

    # 防止写成“输出 judge JSON 给用户”
    assert "直接输出" not in normalized or "judge" not in normalized, "疑似仍要求直接对用户输出 judge JSON"


if __name__ == "__main__":
    try:
        test_skill_user_facing_output_policy()
    except AssertionError as e:
        raise SystemExit(f"TEST FAILED: {e}")

    print("OK")
