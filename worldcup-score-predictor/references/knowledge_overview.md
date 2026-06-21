# 世界杯比分预测 Skill 知识库

本目录不是 Agent 工具，而是 `worldcup-score-predictor` Skill 内供 Codex 调用的结构化知识资产。

目标：

1. 用结构化数据库沉淀赛前输入、维度评分、预测结论、赛后实际数据和复盘结论。
2. 用标准模板保证每场比赛分析口径一致。
3. 用历史样本检索，让 Codex 在预测新比赛前先参考相似比赛和过往误差。
4. 由 Codex 读取这些数据，按 MD 方法论推理、按 JSON 清单执行，并在脚本校验通过后输出预测。

## 目录结构

| 路径 | 用途 |
|---|---|
| `SKILL.md` | Skill 执行协议与资源索引 |
| `references/world-cup-score-prediction-dimensions.md` | 分析方法论与详细判断规则 |
| `references/codex_usage.md` | Codex 调用数据进行预测的流程 |
| `references/post-match-data-update-workflow.md` | 已结束比赛自动更新规范 |
| `config/dimensions.json` | 机器可读的必选维度与子检查项 |
| `schema.sql` | SQLite 数据库结构 |
| `data/worldcup_prediction_knowledge.sqlite` | 持续积累的结构化数据 |
| `templates/match_input_template.json` | 单场比赛赛前输入模板 |
| `templates/dimension_analysis_template.json` | 逐场结构化分析模板 |
| `templates/dimension_scorecard_template.md` | 人类可读的维度评分展示模板 |
| `templates/prediction_report_template.md` | 预测报告模板 |
| `templates/post_match_review_template.md` | 赛后复盘模板 |
| `templates/post_match_player_data_template.json` | 球员逐场表现和比赛事件模板 |
| `queries/historical_sample_retrieval.sql` | 历史样本检索 SQL |
| `queries/player_form_retrieval.sql` | 球员最近比赛表现检索 SQL |
| `seed/dimensions.csv` | 标准维度清单 |
| `seed/historical_samples.jsonl` | 已沉淀历史预测/复盘样本 |
| `seed/seed_data.sql` | 可直接写入 SQLite 的维度目录与历史样本 |
| `scripts/validate_analysis.py` | 完整性和比分逻辑校验 |
| `scripts/update_post_match_data.py` | 事务化写入赛后球队和球员数据 |

## 使用方式

推荐流程：

1. 按 `schema.sql` 创建 SQLite 数据库，并执行 `seed/seed_data.sql` 写入基础维度和历史样本。
2. 赛前按 `match_input_template.json` 填写比赛资料。
3. 按 `dimension_analysis_template.json` 填写全部维度、子检查项、证据和来源。
4. 运行 `scripts/validate_analysis.py`，未通过时不得生成最终报告。
5. 让 Codex 读取比赛输入、结构化分析和历史样本，生成 `prediction_report_template.md` 格式的预测报告。
6. 赛后先按 `post_match_player_data_template.json` 写入球队和球员逐场数据，再按 `post_match_review_template.md` 复盘。
7. 把复盘结论沉淀回数据库和 `historical_samples.jsonl`。

球员数据覆盖状态：

- `full`：双方完整实际出场阵容已录入，进球归因与比分一致。
- `partial`：仅录入部分球员或部分统计，不可冒充完整样本。
- `missing`：尚未录入球员逐场数据。

使用 `python scripts/update_post_match_data.py --audit` 检查全部已完成比赛。

用户无需列出赛后字段。Skill 应自行读取赛后更新规范、检索可靠来源并完成采集、写入、复盘和审计。

## 关键原则

- 不依赖球队排名直接给比分。
- 每个关键判断必须有依据，缺证据时标注“不确定”。
- 至少20个维度必须有效评分，14个核心维度不得未知。
- 双方各至少评估3名关键球员。
- 预测前先检索相似历史样本。
- 赛后必须记录预测误差类型，避免同类错误反复发生。
