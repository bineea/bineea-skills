---
name: worldcup-score-predictor
description: 使用结构化知识库预测、分析和复盘世界杯及足球比赛，并自动更新已结束比赛的球队统计、完整阵容、球员逐场表现和关键事件。用户提到世界杯比分预测、足球比分预测、赛前分析、赛后复盘、更新已结束比赛、补录赛后数据、球员表现、历史样本、维度评分、强队第二球或第三球、弱队进球、零封能力或巨星超额进球时使用。
---

# 世界杯比分预测

使用本 Skill 内的分析框架、SQLite 数据库、历史样本和模板完成结构化预测或赛后复盘。

本 Skill 不是自动预测程序。由 Codex 搜集最新事实、读取结构化数据、逐维度推理并生成报告。

## 资源索引

所有路径均相对于本 `SKILL.md` 所在目录：

| 资源 | 路径 | 用途 |
|---|---|---|
| 分析方法论 | `references/world-cup-score-prediction-dimensions.md` | 解释维度、判断方法和修正规则 |
| 机器维度目录 | `config/dimensions.json` | 26个必选维度与子检查项的执行标准 |
| 调用流程 | `references/codex_usage.md` | 数据读取和预测步骤 |
| 赛后更新规范 | `references/post-match-data-update-workflow.md` | 自动确定范围、采集字段、来源和写入步骤 |
| 知识库说明 | `references/knowledge_overview.md` | 数据资产和目录职责 |
| SQLite 数据库 | `data/worldcup_prediction_knowledge.sqlite` | 历史比赛、评分、预测与复盘 |
| 数据库结构 | `schema.sql` | SQLite 表结构 |
| 比赛输入模板 | `templates/match_input_template.json` | 赛前事实输入 |
| 结构化分析模板 | `templates/dimension_analysis_template.json` | 逐场维度分析结果 |
| 维度评分展示模板 | `templates/dimension_scorecard_template.md` | 人类可读评分表 |
| 预测报告模板 | `templates/prediction_report_template.md` | 固定预测输出 |
| 赛后复盘模板 | `templates/post_match_review_template.md` | 误差分析与经验沉淀 |
| 球员赛后数据模板 | `templates/post_match_player_data_template.json` | 逐场球员表现和事件输入 |
| 历史样本检索 SQL | `queries/historical_sample_retrieval.sql` | 查询相似样本 |
| 球员状态检索 SQL | `queries/player_form_retrieval.sql` | 查询最近比赛出场和表现 |
| 历史样本 JSONL | `seed/historical_samples.jsonl` | 无需数据库时读取样本 |
| 标准维度种子 | `seed/dimensions.csv` | 初始化维度目录 |
| 完整性校验器 | `scripts/validate_analysis.py` | 校验维度、证据和比分一致性 |
| 量化基线生成器 | `scripts/quant_baseline.py` | 根据 xG/进球率/桑格 adapter 生成双泊松比分分布 |
| 可视化看板生成器 | `scripts/generate_visual_dashboard.py` | 根据通过校验的分析 JSON 生成 SVG 雷达图和比分路径看板 |
| 赛后数据写入器 | `scripts/update_post_match_data.py` | 校验并事务化写入球队和球员赛后数据 |

采用三层结构：

1. MD 解释为什么分析以及如何判断。
2. `config/dimensions.json` 定义必须执行的维度和子检查项，是机器执行清单的唯一事实来源。
3. `scripts/validate_analysis.py` 阻止漏项、空依据和比分逻辑冲突进入最终报告。

不要在 `SKILL.md` 或报告模板中复制完整维度清单。修改维度时，先更新 JSON，再同步
MD 方法说明、CSV 和 SQLite；校验器会检查三者的维度键是否一致。

## 赛前预测

按以下顺序执行：

1. 完整读取 `references/world-cup-score-prediction-dimensions.md`。
2. 读取 `config/dimensions.json`、`references/codex_usage.md` 和预测报告模板。
3. 获取或整理本场比赛输入；缺少输入文件时，根据比赛信息自行建立临时结构化输入。
4. 浏览并核实具有时效性的事实，包括赛程、排名、近期状态、伤停、预计首发、赔率、球员状态和场地环境。
5. 读取 `seed/historical_samples.jsonl`，并优先使用 SQLite 与检索 SQL 查找相似样本。
6. 使用 `queries/player_form_retrieval.sql` 检索双方关键球员最近5场的出场时间、首发、进球、助攻、射门、xG、xA和评分；每名关键球员还必须记录至少3个高阶指标，并形成至少3组球员对位边。
7. 在派发 Agent 前运行或手动等价生成 `quant_baseline`：用 direct xG/xGA 与进球/失球率建立 λ，再用双泊松输出比分分布；桑格只作为可插拔 adapter，未配置公式时保持 `unavailable`，不得伪造。
8. 必须启用 `references/codex_usage.md` 中的真实多 Agent 合议流程：先建立 Match Evidence Pack 和量化基线，再实际调用多个独立子 Agent，由 attack、defense_risk、market_history、anti_btts、tail_score、skeptic 和 consensus_arbiter 分工评审、质疑并仲裁。不得由单个 Agent 角色扮演或模拟这些角色。
9. 各专业 Agent 必须在独立运行中输出结构化维度 patch、比分信号和待质疑 claim，不直接生成最终报告；仲裁 Agent 负责合并为唯一的 `templates/dimension_analysis_template.json` 兼容 JSON。
10. 每队至少评估3名关键球员，逐项记录当前状态、类型、对位和来源。
11. 建立 `dynamic_weighting`：根据比赛阶段、天气、休息差、临场阵容和历史误差样本调整维度权重。淘汰赛必须复核 `stage_psychology` 与 `draw_risk`；高温场景必须复核 `environment_schedule`。
12. 建立 `market_calibration.odds_snapshots` 和 `late_market_watch`，覆盖赛前1-2小时赔率变化；异常波动必须写明修正动作或拒绝理由。
13. 至少20个维度必须形成有效评分，且 JSON 中指定的14个核心攻防维度不得为未知。
14. 仲裁时先判断总进球区间，再判断双方进球、强队第二球和第三球、弱队第一球和第二球、零封及平局类型。同时给出至少一个极端比分尾部，并分别说明强队红牌、弱队红牌、弱队两张红牌、点球或门将失误发生后的量化改判。
15. 执行量化基线软闸门：若最终比分、BTTS、大球、第三球或零封判断偏离 `quant_baseline`，必须在 `prediction_gates.quant_baseline_gate` 中写明接受、调整或拒绝量化信号的理由；量化基线不得替代26维、多 Agent 仲裁或历史失败样本路由。
16. 最终 JSON 必须保留 `review_metadata`，记录参与角色、真实独立 Agent 执行轨迹、分歧裁决、被拒绝判断和未知项处理；`review_metadata.agent_execution.execution_mode` 必须为 `independent_subagents`，`tooling` 必须来自白名单，每个必需角色必须有独立 `agent_run_id`、`tool_call_id`、本地 `artifact_ref` 和匹配的 `summary_hash`。`final_prediction.score_orientation` 必须锁定 `team_a-team_b` 的比分顺序。
17. 运行 `py -3.13 scripts/validate_analysis.py <逐场分析.json>`。
18. 校验失败时只回补失败维度或失败合议项；不得绕过校验直接生成最终比分报告。
19. 校验通过后，可运行 `py -3.13 scripts/generate_visual_dashboard.py <逐场分析.json> <输出.svg>` 生成雷达图看板，再使用 `templates/prediction_report_template.md` 生成中文报告，并包含仲裁摘要。

当前比赛事实必须引用可靠来源。社媒和队内关系只能作为低权重修正项，除非有权威报道或场上行为支持。
多 Agent 合议只改变赛前预测和评分过程，不改变赛后复盘与历史比赛数据更新流程。
如果当前运行环境没有可调用的多 Agent / 子 Agent 工具，赛前预测必须报告“严格多 Agent 合议无法执行”，不得降级为单 Agent 角色模拟并声称已完成合议。每个子 Agent 的产物必须保存为技能目录内的本地文件，校验器会读取 `artifact_ref` 并校验 SHA-256。

## 强制预测输出

每场预测必须包含：

- 胜负倾向
- 主比分区间
- 首选比分
- 次选比分
- 总进球区间
- 双方进球概率
- 强队第二球概率
- 强队第三球概率
- 弱队第一球概率
- 弱队第二球概率
- 零封概率
- 平局类型
- 极端比分尾部
- 四类事件情景改判
- 关键触发条件
- 置信度
- 每个维度的分析结果、评分、置信度和依据
- 动态权重调整依据与历史误差学习反馈
- 赛前1-2小时赔率快照、异常波动判断和市场校准动作
- 每队关键球员高阶指标与至少3组球员对位边
- 历史相似样本对本场判断的修正
- 多 Agent 仲裁摘要、关键分歧、被拒绝判断和置信度调整
- 真实独立 Agent 执行摘要，包括每个角色的 `agent_run_id`、产物引用和完成状态
- 校准闸门摘要、比分分布、尾部场景和被闸门修正的判断
- 量化基线摘要，包括 xG/进球率 λ、泊松 Top 比分、BTTS/Over2.5、桑格 adapter 状态和量化软闸门裁决
- 当前事实的引用来源
- 若生成了 SVG 雷达图或看板，报告中必须列出文件路径

维度较多时使用紧凑矩阵，不得只给比分。

结构化分析必须先通过：

```bash
python scripts/validate_analysis.py path/to/match-analysis.json
```

## 历史样本路由

根据当前比赛的高分维度选择样本：

- 强队第三球或巨星超额能力高：检索法国 3-1 塞内加尔。
- 高空、定位球或压迫失误路径明显：检索伊拉克 1-4 挪威。
- 弱队第二球和平局风险高：检索伊朗 2-2 新西兰。
- 弱队进攻核心不首发或出场受限：检索阿根廷 3-0 阿尔及利亚。
- 热门球队第二球不稳定：检索比利时 1-1 埃及。
- 强队领先后收缩、点球导致被追平：检索捷克 1-1 南非。
- 持续机会压力转化为尾段第三球和第四球：检索瑞士 4-1 波黑。
- 弱队两张红牌导致极端比分：检索加拿大 6-0 卡塔尔。
- 明星攻击线被整体控场切断或门将失误决定小比分：检索墨西哥 1-0 韩国。

历史样本只用于校正推理，不能替代当前比赛事实。

## 赛后复盘

用户提供实际比分或指出预测失败时：

1. 完整读取 `references/post-match-data-update-workflow.md`。
2. 不要求用户逐项提供公开数据；自动确定更新范围并联网采集。
3. 读取赛后球员数据模板和复盘模板。
4. 自动更新实际比分、球队统计、完整出场名单、球员逐场表现和关键事件。
5. 使用写入器事务化写入 SQLite，并完成覆盖审计。
6. 对比预测与实际，定位错误维度，生成复盘、历史样本和权重建议。

赛后写入完成后必须运行覆盖审计：

```bash
python scripts/update_post_match_data.py --audit
```

只有显示 `full` 的比赛，才可作为完整球员近期状态样本；`partial` 只能用于已有字段，
`missing` 不得用于球员趋势判断。

### 用户未指定详细要求时的默认行为

- 指定具体比赛：自动补齐该场全部可获得数据。
- 指定日期或轮次：自动更新该范围内全部已结束比赛。
- 只说“更新已结束比赛数据”：运行审计并更新数据库中全部 `missing` 和 `partial` 比赛。
- 自动尝试达到 `full`；无法取得完整可靠数据时保存为 `partial` 并报告缺口。
- 除比赛范围无法识别外，不向用户追问字段、来源或处理步骤。

## 判断约束

- 不得只依据 FIFA 排名或球队名气预测。
- 不得机械给弱队一球，必须验证核心是否首发以及真实进球路径。
- 不得机械把强队上限压在两球；健康巨星、替补深度、定位球错位和压迫失误可能推高到三球或四球。
- 预计首发未确认时，必须降低相关结论置信度。
- 事实、推断和不确定信息必须明确区分。
- 不得用同一段证据覆盖不同子检查项；校验器会拒绝证据克隆式分析。
- 极端比分不是首选比分的替代品，但必须作为条件尾部保留，尤其是红牌、点球、门将失误和持续围攻同时存在时。

## 推荐调用

```text
请使用 worldcup-score-predictor skill，预测 XXX vs YYY。
先检索历史相似样本，再按全部维度评分，并按预测报告模板输出。
```

更新已结束比赛时，用户只需说：

```text
请使用 worldcup-score-predictor skill，更新已结束比赛数据。
```
