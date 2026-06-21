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
6. 使用 `queries/player_form_retrieval.sql` 检索双方关键球员最近5场的出场时间、首发、进球、助攻、射门、xG、xA和评分。
7. 以 `templates/dimension_analysis_template.json` 为结构，为26个维度及全部子检查项填写结论和证据。缺少可靠证据时明确标记 `unknown` 并写明原因。每个子检查项必须使用针对该问题的事实，不得把球队排名、首轮比分或同一段概括机械复制到整组检查项。
8. 每队至少评估3名关键球员，逐项记录当前状态、类型、对位和来源。
9. 至少20个维度必须形成有效评分，且 JSON 中指定的14个核心攻防维度不得为未知。
10. 先判断总进球区间，再判断双方进球、强队第二球和第三球、弱队第一球和第二球、零封及平局类型。同时给出至少一个极端比分尾部，并分别说明强队红牌、弱队红牌、弱队两张红牌、点球或门将失误发生后的量化改判。
11. 运行 `python scripts/validate_analysis.py <逐场分析.json>`。
12. 校验失败时补齐数据或明确未知原因；不得绕过校验直接生成最终比分报告。
13. 校验通过后，使用 `templates/prediction_report_template.md` 生成中文报告。

当前比赛事实必须引用可靠来源。社媒和队内关系只能作为低权重修正项，除非有权威报道或场上行为支持。

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
- 历史相似样本对本场判断的修正
- 当前事实的引用来源

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
