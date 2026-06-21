---
name: kb_qa_loop_compact
description: |
  高性能多轮知识库问答 / 向量库检索 / 需要追问澄清 时使用该 skill：先用 compact 检索脚本在工具内完成远程结果缓存、来源去重、证据裁剪，再进行 sufficiency judge 和带引用最终回答。适用于远程知识库返回内容很大、Claude Code 倾向落盘再 read/grep、需要减少重复检索和上下文膨胀的 RAG 场景。
---

# kb_qa_loop_compact（高性能多轮 RAG）

本 skill 是 `kb_qa_loop` 的性能优化版。核心目标是：**不要把远程知识库的大响应交给模型再落盘搜索**，而是在检索脚本内完成缓存、去重、裁剪，只把可引用的最小证据包交给 judge/answer。

## 硬性门禁（必须遵守，禁止跳步）

1) **禁止直答**：除非已经完成 sufficiency judge 并得到严格 JSON 决策对象，否则不得向用户输出任何结论性答案（包括具体数值、天数、可执行规则）。
2) **judge 是放行条件**：追问或最终回答只能在 judge 成功产出 JSON 后执行；不得凭主观判断跳过 judge。
3) **最终回答唯一出口**：任何“最终回答”必须由 `prompts/kb_answer_with_citations.md` 生成；不得自行组织最终答复。
4) **追问不可人为绕过**：只要 judge 输出 `sufficient=false`，就必须向用户追问并进入下一轮检索；即使用户要求“不要追问/直接给结论/先给个大概”，也不得跳过追问进入最终回答。
5) **必须传 asked_questions**：每轮 judge 必须接收 `asked_questions` 以去重追问；追问必须从 judge 输出的 `clarifying_questions` 里选择。
6) **禁止大结果落盘再搜**：不得因为检索输出较大，就写入本地文件再用 read/grep/Select-String 搜索。需要定位相关片段时，调整 query、topk 或 compact 参数重新检索。
7) **compact 不等于降低追问标准**：如果 compact `items[]` 被截断、存在 `_compact.scope_signals`、或用户问题缺少地区/人群/时间/适用范围等关键条件，必须把这些信息交给 judge；不得因为证据包较短就默认 sufficient=true。

## 状态（state）初始化

开始时初始化 state（在内部记录即可）：

- `original_question`: 用户的原始问题（原样保留）
- `current_query`: 初始等于 `original_question`
- `turn`: 0
- `max_turns`: 8（默认）
- `max_elapsed_seconds`: 120（默认）
- `started_at`: 当前时间戳
- `clarifications`: `[]`（用于累计用户澄清信息；建议每项为 `{question, user_answer}`）
- `asked_questions`: `[]`（记录已问过的澄清问题，避免重复追问）

## 用户可见输出策略（必须）

- judge 仍需产出严格 JSON（`judge_decision`）供内部流程判断与下一轮查询改写。
- 对用户侧：**不回显/不展示 judge 的 JSON**。
  - 当 `sufficient=false`：仅用自然语言向用户追问 1-2 个澄清问题（必须来自 `clarifying_questions`），不要把 JSON 整段打印给用户。
  - 当 `sufficient=true`：仅输出最终回答（必须由 `prompts/kb_answer_with_citations.md` 生成），不要输出 judge JSON。

## 可用资源

- compact 检索脚本：`scripts/kb_retrieve_compact.py`
- 可执行充分性判断脚本：`scripts/kb_judge_sufficiency.py`
- 原始检索适配器：默认复用 `C:/Users/guowb1/.claude/skills/kb-qa-loop/vector_retrieval.py`（只读调用，不修改）
- sufficiency judge 提示词：`prompts/kb_judge_sufficiency.md`
- 最终回答提示词：`prompts/kb_answer_with_citations.md`

## Windows/Bash 路径规则（必须）

Claude Code 在 Windows 上可能通过 Bash 执行命令。Bash 会把 `C:\Users\...` 中的反斜杠当作转义字符，导致路径变成类似 `C:\Users\guowb1\Usersguowb1.claudeskills...` 的错误形式。

因此，所有可执行命令必须使用**带引号的正斜杠路径**：

- 正确：`python "C:/Users/guowb1/.claude/skills/kb-qa-loop-compact/scripts/kb_retrieve_compact.py" --query "护理假" --topk 10`
- 错误：裸露的 `C:\...\script.py` 反斜杠路径，尤其是在 Bash 命令中未加引号时。

## 每轮检索

默认命令：

```bash
python "C:/Users/guowb1/.claude/skills/kb-qa-loop-compact/scripts/kb_retrieve_compact.py" --query "<current_query>" --topk 10
```

默认输出结构：

```json
{
  "items": [
    {"id": "...", "score": 0.0, "text": "...", "metadata": {}, "source": {}}
  ],
  "cache": {"hit": false, "key": "...", "ttl_s": 3600},
  "limits": {"max_items": 10, "max_text_chars": 2200, "max_total_text_chars": 18000}
}
```

把输出中的 `items[]` 作为本轮唯一证据输入 judge/answer。不要传 `raw`。

注意：脚本会在 `metadata._compact` 中保留裁剪诊断信息，例如：

- `original_text_chars`
- `truncated`
- `scope_signals`

这些字段必须随 `items[]` 一起送入 judge。若 `scope_signals` 包含适用范围、地区、人群、时间口径等信号，而 `clarifications[]` 尚未覆盖这些条件，应倾向触发追问。

## 调参顺序

当证据不足或不相关时，按顺序处理：

1. 改写 `current_query`，加入用户澄清条件和缺失信息点。
2. 小幅调整 `--topk`，例如 6、10、15。
3. 小幅调整 compact 限制，例如 `--max-items 10 --max-text-chars 3000 --max-total-text-chars 24000`。
4. 仅在诊断上游响应结构时，使用 `--include-raw-preview` 查看极短 raw 预览；仍不得落盘再全文搜索。

## 每轮循环步骤（turn = 0..）

每一轮都按以下顺序执行。

### 0) 硬停止检查

若满足任一条件，立即停止并输出“无法确认 + 已有证据 + 仍需确认项”：

- `turn >= max_turns`
- `elapsed_seconds >= max_elapsed_seconds`

### 1) 运行 compact 向量检索

调用 `scripts/kb_retrieve_compact.py` 获取证据。默认使用 `topk=10`，且只使用输出中的 compact `items[]`。

### 2) 判断证据是否“已足够回答”（sufficiency judge）

推荐直接调用可执行 judge 脚本的一步模式，确保一定能得到严格 JSON 决策对象，同时避免在 shell 中搬运 JSON：

```bash
python "C:/Users/guowb1/.claude/skills/kb-qa-loop-compact/scripts/kb_judge_sufficiency.py" --retrieve-query "<current_query>"
```

该模式会自动执行 compact 检索并立即 judge，适合第一轮或无需额外澄清上下文的轮次。

如果已经有 `judge_input.json` 文件，也可以使用文件输入：

```bash
python "C:/Users/guowb1/.claude/skills/kb-qa-loop-compact/scripts/kb_judge_sufficiency.py" --input "<judge_input.json>"
```

也可以从 stdin 传入 JSON，此时必须使用 `--input -`：

```bash
printf '%s' '<judge_input_json>' | python "C:/Users/guowb1/.claude/skills/kb-qa-loop-compact/scripts/kb_judge_sufficiency.py" --input -
```

如果上一轮检索结果已经在当前上下文中，也可以直接把检索结果 JSON 作为 `--items-json` 传入。但在 Windows/Bash/PowerShell 混合环境中，命令行 JSON 容易被引号拆坏，因此这只是备用方式，不作为推荐主路径：

```bash
python "C:/Users/guowb1/.claude/skills/kb-qa-loop-compact/scripts/kb_judge_sufficiency.py" --question "<original_question>" --items-json '<retrieval_result_json>'
```

不要调用没有输入的 judge 命令，例如不要只运行 `python ".../kb_judge_sufficiency.py"`。不要使用 `/tmp/judge_input.json` 这类 Linux 临时路径；在 Windows/Bash 混合环境中它经常不存在。若必须使用文件，放在当前工作目录或 `C:/Users/guowb1/AppData/Local/Temp/`，并使用正斜杠路径。

`judge_input.json` 必须包含：

- `question`: 用户原始问题
- `clarifications[]`: 已获得的澄清信息
- `asked_questions[]`: 已问过的问题
- `items[]`: compact 检索输出的证据，必须包含 `metadata._compact` 诊断字段

脚本必须输出严格 JSON：`{"sufficient": boolean, "reason": string, "clarifying_questions": string[], "query_rewrite": string}`。

说明：`prompts/kb_judge_sufficiency.md` 仍保留为模型 judge 的完整提示词；当运行环境可以直接让模型按该 prompt 进行判断时，可以使用它。但如果执行流程需要“可调用工具”，必须使用 `scripts/kb_judge_sufficiency.py`。

### 3A) 若 sufficient=false：向用户追问（1-2 个）

- 从 `clarifying_questions` 中选择不在 `asked_questions` 里的 1-2 个进行提问。
- 将提问追加到 `asked_questions`。
- 等待用户回答后，将 `{question, user_answer}` 追加进 `clarifications[]`。
- 使用 judge 输出的 `query_rewrite` 生成下一轮查询：
  - `current_query = query_rewrite`
  - `turn += 1`
  - 回到硬停止检查。

### 3B) 若 sufficient=true：生成最终回答（带引用）

只有当 `judge_decision.sufficient=true` 时，才将以下信息送入 `prompts/kb_answer_with_citations.md`：

- `question`
- `clarifications[]`
- `judge_decision`
- `items[]`

最终回答必须使用 Markdown，并对关键断言列出知识库引用。引用至少包含 `id=...`，并尽量补充 `docId/docName/origin_path`。

## 关键约束与最佳实践

1) **优先追问关键适用条件**：
   - 只要仍缺少会影响“结论是否对提问者有意义/是否适用/结论内容”的关键适用条件，即使检索结果包含具体数值或结论，也应优先追问补齐后再回答。
2) **裁剪导致不确定时，不要放行**：
   - 如果关键证据被截断，或 `_compact.scope_signals` 暗示存在适用范围差异，而当前问题没有明确这些条件，应让 judge 判定不足并追问。
3) **避免重复追问**：
   - 用 `asked_questions` 和 `clarifications` 去重；每轮最多问 1-2 个，且只问对结论影响最大的缺口。
4) **查询融合（query rewrite）**：
   - 必须把用户澄清信息融合进 `query_rewrite`；避免只做同义改写而不注入新约束。
