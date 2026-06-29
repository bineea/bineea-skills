# Bineea Skills 集合仓库

本仓库是一个 **Codex/Agent 技能合集**，包含多个可独立使用的技能模块。每个模块都有独立的 `SKILL.md`，用于定义触发条件、流程约束、使用路径与输出规范。

当前代码按目录组织，均以“可解释流程 + 可回放脚本”优先。  
仓库遵循 **Apache-2.0** 许可（见 `LICENSE`）。

---

## 目录结构

```text
bineea-skills/
├─ deep-research/
├─ gitlab-mr-review-with-glab/
├─ kb-qa-loop/
├─ kb-qa-loop-compact/
└─ worldcup-score-predictor/
```

## 各模块说明

### 1) deep-research

用于复杂研究类场景（深度调研、市场/竞品/技术选型、政策与行业解读、研究报告等）的工作流技能。

- 适合场景：需要多源证据、结构化分析、有引用的研究结论。
- 关键文件：
  - `SKILL.md`（技能流程与约束）
  - `references/`（方法论、模板、报告样例）

### 2) gitlab-mr-review-with-glab

用于 GitLab MR 的评审流程：抓取 MR、生成 review、将评论回写到 GitLab（默认 note，按需 inline discussions）。

- 适合场景：Windows 环境下 `glab` 调用不稳定、需结构化评审输出。
- 关键文件：
  - `SKILL.md`（调用流程与评分维度）
  - `glab_mr_fetch.py`（拉取 MR）
  - `glab_mr_review_draft.py`（评审草稿生成）
  - `glab_mr_writeback.py`（回写 note/inline）
  - `validate_review.py`（本地校验）

### 3) kb-qa-loop

多轮知识库问答（RAG）技能：先检索、再判断证据充分性，不充分则追问澄清，充分后输出带引用答案。

- 适合场景：需要逐轮追问、保证证据支撑的对话式问答。
- 关键文件：
  - `SKILL.md`（流程约束）
  - `vector_retrieval.py`（检索脚本）
  - `prompts/kb_judge_sufficiency.md`（充分性判断提示词）
  - `prompts/kb_answer_with_citations.md`（最终回答提示词）
- 说明：该模块通过环境变量读取敏感配置（如 API Key、Token、密码），仓库内不应存明文凭据。

### 4) kb-qa-loop-compact

`kb-qa-loop` 的高性能版本：在检索阶段进行缓存、去重和证据裁剪，减少上下文膨胀。

- 适合场景：知识库返回内容较大、希望减少多轮反复展开与落盘搜索。
- 关键文件：
  - `SKILL.md`
  - `scripts/kb_retrieve_compact.py`（compact 检索）
  - `scripts/kb_judge_sufficiency.py`（judge 执行）
  - `prompts/`（同 `kb-qa-loop`）

### 5) worldcup-score-predictor

用于“足球赛事预测与赛后复盘”分析链路的技能模块：包含评分模板、数据库、SQL 查询、数据更新与校验脚本。

- 适合场景：按固定维度输出结构化分析，并结合历史样本和校验器产出可追溯报告。
- 关键文件：
  - `SKILL.md`
  - `config/dimensions.json`（维度定义）
  - `scripts/validate_analysis.py`（分析结构校验，建议优先运行）
  - `scripts/update_post_match_data.py`（赛后数据落库）
  - `schema.sql` 与 `data/`（数据与历史记录）
  - `templates/`（分析/报告模板）
  - `references/`（方法说明）

---

## 运行环境

- 建议使用 Python 3.11（本项目脚本均以标准库为主，但可按需升级到 3.13）。
- 当前仓库内暂无统一的 `requirements.txt` / `pyproject.toml` / `uv.lock`，多数脚本使用标准库即可运行。
- 若某模块依赖额外工具（如 `glab`），需按该模块说明提前安装。

---

## 快速开始

1. 进入仓库

```powershell
cd D:\Project\Other\bineea-skills
```

2. 先按需阅读对应模块文档

```text
deep-research\SKILL.md
gitlab-mr-review-with-glab\SKILL.md
kb-qa-loop\SKILL.md
kb-qa-loop-compact\SKILL.md
worldcup-score-predictor\SKILL.md
```

3. 先做安全检查（防止误提交）

```powershell
rg -uu -n "(password|secret|token|api_key|PRIVATE_KEY|BEGIN PRIVATE KEY)" .
```

4. 按模块说明执行脚本或工作流

例如：  

```powershell
# kb 取证检索（示例）
python "kb-qa-loop\vector_retrieval.py" --query "你要问的问题" --topk 10

# worldcup 结构校验（示例）
python "worldcup-score-predictor\scripts\validate_analysis.py" "worldcup-score-predictor\some_analysis.json"
```

> 注：Windows + Bash 环境下，路径中斜杠与引号的处理不稳定时，请使用双引号包裹绝对路径。

---

## 贡献建议

- 修改技能流程前，先同步更新对应 `SKILL.md` 与提示词文件。
- 如果引入新依赖，请补充到项目级依赖说明中并更新 `.gitignore` 与文档。
- 保持脚本输出的结构化和可追踪性（JSON 字段、引用、评分原因等）。
- 提交前尽量保留一次全量扫描，避免敏感信息进入版本库。

## 安全与隐私

- 不要提交任何真实口令、Token、`.env`、证书、私钥文件。
- 数据库文件与分析样本可能包含历史记录，可在 PR 时说明是否包含隐私数据。
- 如需对外发布，建议先清理 `data/` 下非必要历史和冗余产物。

## 常见问题（FAQ）

- Q：是否能直接执行脚本？  
  A：可直接执行，但请以 `SKILL.md` 为准，先确认输入参数和环境变量要求。

- Q：凭据从哪里设置？  
  A：按技能要求通过环境变量注入，不建议硬编码到代码。

- Q：为何有 `__pycache__`、`*.bak`、`data/reviews` 等文件？  
  A：用于本地执行缓存与历史数据沉淀，按需清理后可减少仓库体量。

---

## 版权与许可

本仓库采用 Apache-2.0 许可证，详见 `LICENSE`。

