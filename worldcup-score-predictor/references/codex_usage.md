# Codex 调用知识库进行预测的流程

Codex 预测新比赛时，不需要运行专门 Agent，只需要读取以下数据并按流程推理。

## 需要读取的资料

1. `references/world-cup-score-prediction-dimensions.md`
2. `config/dimensions.json`
3. `templates/match_input_template.json`
4. 本场已填写的比赛输入 JSON
5. `templates/dimension_analysis_template.json`
6. `seed/historical_samples.jsonl`
7. 如已建立 SQLite 数据库，再用 `queries/historical_sample_retrieval.sql` 检索相似样本
8. 用 `queries/player_form_retrieval.sql` 检索关键球员近期逐场表现

## Codex 预测步骤

1. 确认比赛基础事实：日期、阶段、场地、双方球队。
2. 阅读本场输入模板，提取球队、球员、伤停、赔率、社媒/队内关系、环境信息。
3. 按 `config/dimensions.json` 填写结构化分析，覆盖26个维度及全部子检查项。每个子检查项使用与问题直接相关的证据，不能复制同一段概括凑齐校验。
4. 检索历史样本：
   - 如果强队第三球评分高，参考法国 3-1 塞内加尔。
   - 如果高空/定位球错位高，参考伊拉克 1-4 挪威。
   - 如果弱队第二球评分高，参考伊朗 2-2 新西兰。
   - 如果弱队核心不首发且强队控场强，参考阿根廷 3-0 阿尔及利亚。
   - 如果热门强队第二球不足，参考比利时 1-1 埃及。
5. 先判断总进球区间。
6. 判断双方进球概率。
7. 判断强队第二球、强队第三球、弱队第一球、弱队第二球、零封概率。
8. 输出首选比分、备选比分、极端比分尾部和四类事件情景改判。
9. 运行 `python scripts/validate_analysis.py <逐场分析.json>`。
10. 只有校验通过后，才按 `prediction_report_template.md` 生成中文预测报告。

## Codex 预测提示词模板

```text
请严格按照以下资料预测比分：

1. 读取 `references/world-cup-score-prediction-dimensions.md`
2. 读取 `config/dimensions.json`
3. 读取本场比赛输入 JSON
4. 按 `templates/dimension_analysis_template.json` 填写全部维度
5. 读取 `seed/historical_samples.jsonl`
6. 如有 SQLite 数据库，先用 `queries/historical_sample_retrieval.sql` 检索相似样本
7. 运行 `scripts/validate_analysis.py`，校验通过后再输出报告

输出必须包含：
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
- 关键触发条件
- 置信度
- 每个维度的分析结果和依据
- 历史相似样本如何修正本场判断
- 极端比分尾部及其成立条件
- 强队红牌、弱队红牌、弱队两张红牌、点球或门将失误后的量化改判

禁止：
- 只根据球队排名预测
- 没有依据就给结论
- 忽略历史预测失败样本
- 用同一段证据覆盖不同子检查项
```

## 赛后复盘步骤

用户只需提出更新比赛数据，不需要指定字段和步骤。Codex 必须：

1. 读取 `references/post-match-data-update-workflow.md`。
2. 运行 `python scripts/update_post_match_data.py --audit`。
3. 根据用户指定范围或审计结果自动选择要处理的比赛。
4. 联网采集正式赛果、球队统计、完整出场名单、球员表现和关键事件。
5. 按 `post_match_player_data_template.json` 生成 `data/imports/<match_id>.json`。
6. 运行 `python scripts/update_post_match_data.py data/imports/<match_id>.json` 写入 SQLite。
7. 再次运行覆盖审计。
8. 按 `post_match_review_template.md` 对比预测和实际。
9. 标记误差类型、提炼经验并更新历史样本。

如果未指定比赛范围，默认更新数据库中全部 `missing` 和 `partial` 的已结束比赛。
