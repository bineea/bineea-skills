# Codex 调用知识库进行预测的流程

Codex 预测新比赛时，默认启用受控多 Agent 合议流程。多 Agent 只用于分工、质疑和共识，不改变最终 JSON、校验器和报告模板的交付要求。

赛后复盘和历史比赛数据更新不使用本流程，继续按 `references/post-match-data-update-workflow.md` 和 `scripts/update_post_match_data.py` 执行。

## 需要读取的资料

1. `references/world-cup-score-prediction-dimensions.md`
2. `config/dimensions.json`
3. `templates/match_input_template.json`
4. 本场已填写的比赛输入 JSON
5. `templates/dimension_analysis_template.json`
6. `seed/historical_samples.jsonl`
7. 如已建立 SQLite 数据库，再用 `queries/historical_sample_retrieval.sql` 检索相似样本
8. 用 `queries/player_form_retrieval.sql` 检索关键球员近期逐场表现

## 上下文控制原则

- Coordinator 读取完整 Skill 说明、方法论、模板、维度目录和历史样本。
- 其他 Agent 只接收 Match Evidence Pack、自己负责的维度键、对应 required_checks 和必要历史样本摘要。
- 不让每个 Agent 重复读取完整 26 维说明。
- 不保存自由聊天全文，只保留结构化分歧账本和仲裁摘要。
- 每个 Agent 输出 JSON patch 或短表格，不输出长篇报告。
- 讨论最多两轮：初评、质疑、定向回应、仲裁。
- 校验失败时只回补失败维度或失败合议项，不重新跑全量流程。

## Match Evidence Pack

Coordinator 先建立统一事实包。后续 Agent 只能引用其中的 `source_id`；需要新增事实时提交 `fact_request`，由 Coordinator 补证后更新事实包。

```json
{
  "job_id": "YYYY-MM-DD_TEAM_A_TEAM_B",
  "match": {},
  "sources": [],
  "facts": {
    "schedule": [],
    "ranking_elo": [],
    "recent_form": [],
    "lineups_injuries": [],
    "player_form": [],
    "odds_market": [],
    "weather_pitch": [],
    "referee": [],
    "team_context": []
  },
  "historical_samples": [],
  "uncertainties": []
}
```

`sources` 中的来源必须统一编号，建议使用 `src_fixture_001`、`src_odds_001`、`src_lineup_001`、`src_player_form_001` 等稳定 ID。

## 角色与维度分工

| 维度 | 主责 Agent | 复核 Agent |
|---|---|---|
| `base_strength` | `market_history_agent` | `attack_agent`, `defense_risk_agent` |
| `player_status` | `attack_agent` | `defense_risk_agent` |
| `player_type_structure` | `attack_agent` | `defense_risk_agent` |
| `key_matchups` | `attack_agent` | `defense_risk_agent` |
| `historical_style` | `market_history_agent` | `defense_risk_agent` |
| `style_counter` | `defense_risk_agent` | `attack_agent` |
| `recent_form` | `market_history_agent` | `attack_agent` |
| `goal_distribution` | `attack_agent` | `market_history_agent` |
| `strong_second_goal` | `attack_agent` | `market_history_agent` |
| `strong_third_goal` | `attack_agent` | `market_history_agent` |
| `weak_first_goal` | `attack_agent` | `defense_risk_agent` |
| `weak_second_goal` | `attack_agent` | `defense_risk_agent` |
| `favorite_defense` | `defense_risk_agent` | `attack_agent` |
| `clean_sheet` | `defense_risk_agent` | `attack_agent` |
| `tactical_matchup` | `defense_risk_agent` | `attack_agent` |
| `stage_psychology` | `defense_risk_agent` | `market_history_agent` |
| `draw_risk` | `defense_risk_agent` | `market_history_agent` |
| `lineup_injuries` | `defense_risk_agent` | `attack_agent` |
| `team_harmony_social` | `defense_risk_agent` | `market_history_agent` |
| `environment_schedule` | `defense_risk_agent` | `market_history_agent` |
| `referee_events` | `defense_risk_agent` | `attack_agent` |
| `market_odds` | `market_history_agent` | `defense_risk_agent` |
| `dynamic_triggers` | `defense_risk_agent` | `attack_agent` |
| `star_overperformance` | `attack_agent` | `market_history_agent` |
| `set_piece_aerial` | `attack_agent` | `defense_risk_agent` |
| `pressing_error_path` | `attack_agent` | `defense_risk_agent` |

`anti_btts_agent` 只审查双方进球和弱队进球路径。它必须反对机械给弱队一球，并检查弱队是否至少具备两条独立进球路径。

`tail_score_agent` 只审查被主路径压掉的尾部比分。它必须寻找 4-0/5-0、0-0/1-0、1-1 等大胜或闷局路径，并说明是否进入主区间、次选或条件尾部。

`skeptic_agent` 不负责生成完整维度，只审查高影响 claim：强队第二/第三球、弱队进球、零封、平局、极端比分尾部、红牌/点球/门将失误改判。

`consensus_arbiter` 不新增事实，只合并 patch、处理冲突、统一强弱方口径并生成最终 JSON。

## 专业 Agent 输入

```json
{
  "job_id": "",
  "schema_version": "role-review-1.0",
  "catalog_version": "",
  "match_evidence_pack": {},
  "dimension_catalog_excerpt": {},
  "role_policy": {
    "role_id": "attack_agent",
    "primary_dimension_keys": [],
    "review_dimension_keys": [],
    "must_return_all_required_checks_for_primary": true
  }
}
```

## 专业 Agent 输出

```json
{
  "schema_version": "role-result-1.0",
  "job_id": "",
  "role_id": "attack_agent",
  "coverage": {
    "primary_dimension_keys": [],
    "review_dimension_keys": [],
    "completed_dimension_keys": [],
    "incomplete_dimension_keys": []
  },
  "player_assessment_patches": {
    "team_a": [],
    "team_b": []
  },
  "dimension_patches": [
    {
      "dimension_key": "",
      "ownership": "primary",
      "score": 3,
      "confidence": "medium",
      "conclusion": "",
      "check_results": {},
      "evidence": [],
      "source_ids": [],
      "unknown_items": [],
      "conflict_flags": [],
      "score_effects": {
        "team_a_goals_delta": 0,
        "team_b_goals_delta": 0,
        "total_goals_delta": 0,
        "btts_delta": 0,
        "clean_sheet_delta": 0
      }
    }
  ],
  "prediction_signals": {
    "total_goals_range": [],
    "both_teams_to_score": "unknown",
    "strong_second_goal": "unknown",
    "strong_third_goal": "unknown",
    "weak_first_goal": "unknown",
    "weak_second_goal": "unknown",
    "clean_sheet": "unknown",
    "draw_type": "",
    "tail_scores": [],
    "trigger_conditions": []
  },
  "claims_for_review": []
}
```

`dimension_patches[].check_results` 必须使用 `dimensions.json` 中对应维度的原始子检查项 key，不得新增 key。

## 分歧账本

Coordinator 合并初稿后，必须生成 Disagreement Ledger。只有会改变比分区间、强弱队进球概率、零封概率、强队第三球、平局类型或极端尾部的分歧进入复议。

```json
{
  "issue_id": "D1",
  "issue_type": "score_gap",
  "topic": "强队第三球是否进入主预测区间",
  "affected_dimensions": ["strong_third_goal"],
  "affected_prediction_fields": ["strong_third_goal", "tail_scores", "total_goals_max"],
  "positions": [
    {
      "role_id": "attack_agent",
      "position": "medium",
      "evidence_source_ids": ["src_player_form_001"]
    },
    {
      "role_id": "skeptic_agent",
      "position": "low",
      "objection": "替补攻击质量证据不足，且大小球市场不支持明显大胜"
    }
  ],
  "resolution": "降为 medium，保留 3-0 或 3-1 为尾部，不作为唯一主路径",
  "confidence_change": "high -> medium"
}
```

## 仲裁规则

- 主责 Agent 的完整维度 patch 优先进入候选。
- 复核 Agent 若提出相反结论，必须有更高质量来源或更具体证据，否则只记入被拒绝判断。
- 赔率和历史样本只能做校准，不能覆盖当前阵容、伤停和对位事实。
- 核心维度缺证据时不得硬填中性分，必须补证或降低整场预测置信度。
- `weak_first_goal` 为 high 或 medium 时，主比分区间至少保留一个弱队进球比分；若 `clean_sheet` 为 high，必须解释弱队路径为何被切断。
- 阵容未确认、伤停来源弱或预计首发缺证时，不得给相关维度 high confidence。
- 仲裁输出必须包含 `review_metadata`，记录 `role_results_used`、`conflicts_resolved`、`claims_rejected` 和 `unknown_rationale`。

## 赛前校准闸门

仲裁前必须执行五个校准闸门，并写入 `prediction_gates`、`score_distribution`、`market_calibration` 和 `tail_scenarios`。

| 闸门 | 必须判断 | 失败时动作 |
|---|---|---|
| `weak_goal_gate` | 弱队第一球为 medium/high 时，是否至少有两条独立进球路径 | 不足两条时降级弱队第一球，并下调双方进球 |
| `clean_sheet_gate` | 零封和弱队第一球同时 medium/high 时，冲突是否已裁决 | 无裁决不得生成最终报告 |
| `market_calibration_gate` | 市场让球明显支持强队大胜时，模型是否保留 3 球以上比分 | 未保留时上调强队第三球或登记拒绝理由 |
| `low_block_draw_gate` | 强队阵地战风险高、对手低位结构强时，是否保留 0-0/1-0/1-1 | 至少一个闷局比分必须进入分布 |
| `tail_score_gate` | 是否检查大胜、闷局、双方进球三类尾部 | 缺少任一类尾部说明不得通过 |

弱队进球路径必须是相互独立的事实路径，例如“核心首发反击 + 定位球高点”算两条；“同一名前锋速度快 + 同一名前锋能反击”只能算一条。

比分分布必须包含：

- `main_paths`：2-3 个主路径比分。
- `low_block_paths`：0-0、1-0、1-1 中至少判断一个是否成立。
- `big_win_paths`：3 球以上大胜比分是否进入主区间或尾部。
- `btts_paths`：双方进球路径是否通过弱队进球闸门。

## Codex 预测步骤

1. 确认比赛基础事实：日期、阶段、场地、双方球队。
2. 阅读本场输入模板，提取球队、球员、伤停、赔率、社媒/队内关系、环境信息。
3. 建立 Match Evidence Pack，统一来源 ID。
4. 检索历史样本：
   - 强队第三球或巨星超额能力高：参考法国 3-1 塞内加尔。
   - 高空、定位球或压迫失误路径明显：参考伊拉克 1-4 挪威。
   - 弱队第二球和平局风险高：参考伊朗 2-2 新西兰。
   - 弱队进攻核心不首发或出场受限：参考阿根廷 3-0 阿尔及利亚。
   - 热门球队第二球不稳定：参考比利时 1-1 埃及。
5. 启动 `attack_agent`、`defense_risk_agent`、`market_history_agent` 并行初评。
6. 合并初评 patch，检查 26 个维度、所有 required_checks、来源 ID 和关键球员覆盖。
7. 启动 `anti_btts_agent`、`tail_score_agent` 和 `skeptic_agent` 审查高影响 claim、弱队进球、零封、闷局和尾部比分。
8. 执行五个赛前校准闸门，写入分布和闸门修正动作。
9. 对 Disagreement Ledger 中的高影响分歧进行一轮定向回应。
10. `consensus_arbiter` 生成最终结构化分析 JSON。
11. 运行 `python scripts/validate_analysis.py <逐场分析.json>`。
12. 校验失败时只回补失败维度或失败合议项。
13. 校验通过后，按 `prediction_report_template.md` 生成中文预测报告。

## Codex 预测提示词模板

```text
请使用 worldcup-score-predictor skill，按默认多 Agent 合议流程预测 XXX vs YYY。

必须：
1. 读取 `references/world-cup-score-prediction-dimensions.md`
2. 读取 `config/dimensions.json`
3. 读取 `references/codex_usage.md`
4. 建立 Match Evidence Pack 并统一 source_id
5. 让 attack、defense_risk、market_history 三个专业视角提交结构化 patch
6. 让 anti_btts、tail_score 和 skeptic 质疑高影响 claim
7. 执行 weak_goal、clean_sheet、market_calibration、low_block_draw、tail_score 五个校准闸门
8. 由 consensus_arbiter 生成最终 `dimension_analysis_template.json` 兼容 JSON
9. 运行 `scripts/validate_analysis.py`
10. 校验通过后输出报告

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
- 仲裁摘要、关键分歧、被拒绝判断和置信度调整
- 校准闸门摘要、比分分布和被闸门修正的判断

禁止：
- 只根据球队排名预测
- 没有依据就给结论
- 忽略历史预测失败样本
- 用同一段证据覆盖不同子检查项
- 让专业 Agent 直接生成最终报告
- 让市场或历史样本覆盖当前阵容、伤停和对位事实
- 弱队只有单一路径时机械给双方进球 medium/high
- 市场明显支持大胜时仍不保留 3 球以上比分
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
