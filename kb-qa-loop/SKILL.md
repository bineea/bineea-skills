---
name: kb_qa_loop
description: |
  多轮知识库问答 / 向量库检索 / 需要追问澄清 时使用该 skill：先检索，再判断证据是否充分；不充分则向用户追问并改写查询，循环直到能给出带引用的最终回答或触发硬停止。
---

# kb_qa_loop（多轮交互 RAG）

本 skill 用于“检索 -> 判断是否充分 -> 追问澄清 -> 融合查询 -> 再检索 -> 最终回答”的多轮知识库问答流程。

## 硬性门禁（必须遵守，禁止跳步）

1) **禁止直答**：除非已经完成步骤2（sufficiency judge）并得到严格 JSON 决策对象，否则不得向用户输出任何结论性答案（包括具体数值、天数、可执行规则）。
2) **judge 是放行条件**：步骤3A/3B 只能在步骤2成功产出 JSON 后执行；不得凭主观判断跳过 judge。
3) **最终回答唯一出口**：任何“最终回答”必须由 `prompts/kb_answer_with_citations.md` 生成；不得自行组织最终答复。
4) **证据过大不得绕过**：若检索输出过大/不可用，必须先做证据裁剪（降低 topk、仅保留最相关 items、截断 text），再运行 judge；不得绕过 judge 直接回答。
5) **必须传 asked_questions**：每轮 judge 必须接收 `asked_questions` 以去重追问；且追问必须从 judge 输出的 `clarifying_questions` 里选择。
6) **追问不可人为绕过**：只要 judge 输出 `sufficient=false`，就必须执行步骤3A追问并进入下一轮检索；即使用户要求“不要追问/直接给结论/先给个大概”，也不得跳过追问进入最终回答。

## 目录内可用资源（必须使用）

- 检索脚本：`vector_retrieval.py`（通过环境变量配置向量库/索引/连接信息）
- 充分性判断提示词：`prompts/kb_judge_sufficiency.md`
- 最终回答提示词（含引用）：`prompts/kb_answer_with_citations.md`

> 注意：本 skill 不要求实现真正“自动循环代码”，而是以可执行的工作流指令形式编排，让 Claude 在对话中按步骤调用工具完成循环。

## Windows/Bash 路径规则（必须）

Claude Code 在 Windows 上可能通过 Bash 执行命令。Bash 会把 `C:\...` 中的反斜杠当作转义字符，导致路径被拼坏或找不到文件。

因此，调用本 skill 的脚本时必须使用**带引号的正斜杠路径**。不要使用裸露的 `C:\...\script.py` 反斜杠路径。

正确示例：

```bash
python "C:/Users/guowb1/.claude/skills/kb-qa-loop/vector_retrieval.py" --query "<current_query>" --topk 10
```

---

## 调用方式与输入约定（必须）

- 直接使用 slash 调用：`/kb_qa_loop <你要问的问题>`
- slash 后面的文本**直接视为** `original_question`（原始问题）。
- 因此：**不再**需要弹出“原始问题”选择器（例如“我来粘贴问题 / 从文件取 / Type something”）。

## 用户可见输出策略（必须）

- judge 仍需产出严格 JSON（`judge_decision`）供内部流程判断与下一轮查询改写。
- 但对用户侧：**不回显/不展示 judge 的 JSON**。
  - 当 `sufficient=false`：仅用**自然语言**向用户追问 1-2 个澄清问题（必须来自 `clarifying_questions`），不要把 JSON 整段打印给用户。
  - 当 `sufficient=true`：仅输出最终回答（必须由 `prompts/kb_answer_with_citations.md` 生成），不要输出 judge JSON。

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

---

## 每轮循环步骤（turn = 0..）

每一轮都按以下顺序执行：

### 0) 硬停止检查（必须）

若满足任一条件，立即停止并输出“无法确认 + 已有证据 + 仍需确认项”：

- `turn >= max_turns`
- `elapsed_seconds >= max_elapsed_seconds`（用当前时间 - `started_at` 计算）

停止时的输出模板建议：

- **结论**：目前无法确认/无法给出可靠结论
- **已有证据**：列出当前已检索到的关键片段（引用 items 的来源）
- **仍需确认**：列出 1-3 个最关键的待澄清点（避免继续追问）

### 1) 运行向量检索（vector retrieval）

调用本目录下检索脚本获取证据：

```bash
python "C:/Users/guowb1/.claude/skills/kb-qa-loop/vector_retrieval.py" --query "<current_query>" --topk 10
```

- 本 skill 默认使用 `topk=10`。
- 记录返回的 `items/raw`（按脚本输出原样保留），并在后续提示词中传入。
- **产物要求（必须）**：为避免信息丢失，你必须生成 `items_min[]`（最多 10 条），每条保留 `{id, score, text, metadata, source}`，并明确：**不截断 text**（即不做 text 截断）；仅将 `items_min[]` 送入 judge/answer（raw 仅用于需要时回溯）。

### 2) 判断证据是否“已足够回答”（sufficiency judge）

把以下信息组织成输入，送入 `prompts/kb_judge_sufficiency.md`（**必须使用 items_min[]**）：

- `original_question`
- `clarifications`（截至当前轮累计的澄清 Q/A）
- 本轮检索得到的 `items`（含必要的元数据，如标题/路径/段落/score 等；以及原始 raw）
- `asked_questions`（用于避免重复追问）

要求模型严格输出一个 JSON 决策对象（字段以提示词为准），并至少包含：

- `sufficient`: boolean
- `clarifying_questions`: string[]（当 `sufficient=false` 时给出，1-2 个问题即可）
- `query_rewrite`: string（当 `sufficient=false` 时给出，用于生成下一轮 `current_query`）
- （可选）`missing_info`: string[]（说明还缺什么信息）

### 3A) 若 sufficient=false：向用户追问（1-2 个）

- 从 `clarifying_questions` 中选择 **不在** `asked_questions` 里的 1-2 个进行提问。
- 将提问追加到 `asked_questions`。
- 等待用户回答后，将 `{question, user_answer}` 追加进 `clarifications[]`。
- 使用 judge 输出的 `query_rewrite` 生成下一轮查询：
  - `current_query = query_rewrite`
  - 并将 `turn += 1`，回到“硬停止检查”。

### 3B) 若 sufficient=true：生成最终回答（带引用）

- **必须**进入最终回答生成流程：将以下信息送入 `prompts/kb_answer_with_citations.md` 输出最终回答（带引用）。
- **不得**仅输出“无需追问/不需要追问”之类的中间态结论而不生成最终回答。

将以下信息送入 `prompts/kb_answer_with_citations.md` 生成最终回答：

- `original_question`
- `clarifications`
- 最终使用的 `current_query`
- 足够的 `items`（用于支撑结论与引用）

输出要求：

- 直接回答用户问题
- 对关键断言给出引用（引用格式以提示词为准）
- 若仍存在不确定性，明确写出不确定点与原因（但不再追问）

---

## 关键约束与最佳实践

1) **优先追问关键适用条件**：
   - 只要仍缺少会影响“结论是否对提问者有意义/是否适用/结论内容”的关键适用条件，即使检索结果包含具体数值或结论，也应优先追问补齐后再回答。

2) **避免重复追问**：
   - 优先依赖 `kb_judge_sufficiency` 提示词中的规则；
   - 同时用 `asked_questions` 去重；
   - 每轮最多问 1-2 个，且只问“对结论影响最大”的缺口。

2) **追问应可操作**：
   - 问题要短、明确、可由用户直接回答；
   - 避免一次性索要大量背景。

3) **查询融合（query rewrite）**：
   - 必须把用户澄清信息融合进 `query_rewrite`；
   - 避免只做同义改写而不注入新约束。

4) **时间与轮次**：
   - 默认 `max_turns=8`、`max_elapsed_seconds=120`；
   - 若用户明确希望更快/更慢，可在不违反硬停止精神的前提下调整，但需显式说明。
