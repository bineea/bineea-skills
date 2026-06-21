# -*- coding: utf-8 -*-
"""TDD: 针对 kb_judge_sufficiency 提示词模板的最小测试。

运行方式：
  python C:/Users/guowb1/.claude/skills/kb-qa-loop/tests/test_kb_judge_prompt.py
"""

from __future__ import annotations

from pathlib import Path


def test_prompt_constraints() -> None:
    prompt_path = Path(r"C:\Users\guowb1\.claude\skills\kb-qa-loop\prompts\kb_judge_sufficiency.md")
    assert prompt_path.exists(), f"提示词文件不存在: {prompt_path}"

    content = prompt_path.read_text(encoding="utf-8")

    # 1) 必须包含“只输出 JSON 不要 markdown”约束
    assert "只输出JSON" in content or "只输出 JSON" in content, "缺少：只输出 JSON 的硬性约束"
    assert "不要" in content and ("Markdown" in content or "markdown" in content), "缺少：不要 markdown/Markdown 的硬性约束"

    # 2) 必须包含 clarifying_questions 数量约束 + sufficient=true 时为空数组
    assert "clarifying_questions" in content, "缺少字段名 clarifying_questions"
    assert ("最多2" in content) or ("最多 2" in content) or ("不超过2" in content) or ("不超过 2" in content), "缺少：clarifying_questions 最多 2 条的约束"
    normalized = content.replace(" ", "")
    assert "sufficient=true" in normalized or "sufficient为true" in normalized or "sufficient==true" in normalized, "缺少：sufficient=true 的说明"
    assert ("空数组" in content) and ("[]" in content), "缺少：sufficient=true 时 clarifying_questions 必须为空数组 [] 的约束"

    # 3) 只要存在“需要补充确认的问题”就必须判定为 insufficient
    assert "需要补充确认" in content, "缺少：需要补充确认 的关键规则"
    assert "必须 `sufficient=false`" in content or "必须sufficient=false" in normalized, "缺少：需要补充确认时必须 sufficient=false"

    # 3) 必须包含避免重复追问的规则（已有 clarifications[]/asked_questions[] 不得重复提同类问题）
    assert "clarifications" in content, "缺少输入字段 clarifications[] 的提及"
    assert "asked_questions" in content, "缺少输入字段 asked_questions[] 的提及"
    assert ("不得重复" in content) or ("避免重复" in content), "缺少：避免重复追问的表述"
    assert ("同类" in content) or ("同一" in content) or ("类似" in content), "缺少：不得重复提同类问题的约束"
if __name__ == "__main__":
    # 简易运行器（不依赖 pytest）
    try:
        test_prompt_constraints()
    except AssertionError as e:
        raise SystemExit(f"TEST FAILED: {e}")

    print("OK")
