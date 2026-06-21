# -*- coding: utf-8 -*-
"""TDD: 针对 kb_answer_with_citations 提示词模板的最小测试。

运行方式：
  python C:/Users/guowb1/.claude/skills/kb-qa-loop/tests/test_kb_answer_prompt.py

说明：
- 该测试不依赖 pytest，仅做纯文本断言。
- 目标是确保提示词包含：只基于 items[]、禁止编造、必须引用 id=、以及固定 Markdown 结构标题。
"""

from __future__ import annotations

from pathlib import Path


def test_prompt_constraints() -> None:
    prompt_path = Path(r"C:\Users\guowb1\.claude\skills\kb-qa-loop\prompts\kb_answer_with_citations.md")
    assert prompt_path.exists(), f"提示词文件不存在: {prompt_path}"

    content = prompt_path.read_text(encoding="utf-8")
    normalized = content.replace(" ", "")

    # 1) 强约束：只能基于 items[]，禁止编造
    assert "items[]" in content or "items" in content, "缺少：输入 items[] 的提及"
    assert ("只能" in content) and ("基于" in content) and ("items" in content), "缺少：只能基于 items[] 的硬性约束"
    assert ("禁止编造" in content) or ("不得编造" in content) or ("严禁编造" in content), "缺少：禁止编造/不得编造 的硬性约束"
    assert ("无法从知识库确认" in content) or ("无法从知识库" in content), "缺少：证据不足时必须声明无法从知识库确认"

    # 1.1) 门禁：未通过 judge 不得输出最终答案
    assert "judge_decision" in content, "缺少：需要输入 judge_decision 的门禁信息"
    assert ("未通过" in content) and ("不能给出最终结论" in content or "不得生成" in content), "缺少：未通过 judge 时不得给出最终结论的约束"

    # 2) 强约束：必须输出引用，至少包含 id=...
    assert "依据（来自知识库）" in content, "缺少：固定结构标题 '## 依据（来自知识库）'"
    assert "id=" in content, "缺少：引用格式中必须包含 id=..."
    assert ("docId" in content) or ("docName" in content) or ("origin_path" in content), "缺少：引用需包含 docId/docName/origin_path 之一的要求"

    # 3) 固定 Markdown 结构（四个二级标题，顺序不强制但必须存在）
    for heading in [
        "## 结论",
        "## 依据（来自知识库）",
        "## 推理过程（仅基于证据）",
        "## 仍需确认（如适用）",
    ]:
        assert heading in content, f"缺少固定结构标题: {heading}"

    # 4) 明确输出为 Markdown
    assert ("Markdown" in content) or ("markdown" in content), "缺少：输出为 Markdown 的说明"


if __name__ == "__main__":
    # 简易运行器（不依赖 pytest）
    try:
        test_prompt_constraints()
    except AssertionError as e:
        raise SystemExit(f"TEST FAILED: {e}")

    print("OK")
