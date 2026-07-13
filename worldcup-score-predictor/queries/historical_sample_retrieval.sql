-- 历史样本检索 SQL
-- 用法：先根据新比赛的关键标签、维度高分项、误差风险检索相似样本，再让 Codex 参考这些样本进行预测。

-- 1. 按标签检索相似比赛（数据库规范表）
SELECT
    s.match_id,
    s.teams_text,
    s.predicted_score,
    s.actual_score,
    s.error_types_json,
    s.reusable_lessons_json,
    s.tags_json
FROM historical_samples s
WHERE s.tags_json LIKE '%强队第三球%'
   OR s.tags_json LIKE '%高空定位球错位%'
   OR s.tags_json LIKE '%弱队第二球能力%'
   OR s.tags_json LIKE '%弱队第二球%'
   OR s.tags_json LIKE '%强队零封能力%'
   OR s.tags_json LIKE '%巨星超额进球%'
   OR s.tags_json LIKE '%领先后收缩%'
   OR s.tags_json LIKE '%双红牌%'
   OR s.tags_json LIKE '%极端比分%'
   OR s.tags_json LIKE '%门将失误%'
   OR s.tags_json LIKE '%持续机会压力%'
   OR s.tags_json LIKE '%过度锁定低比分%'
   OR s.tags_json LIKE '%低估弱队第二球%'
   OR s.tags_json LIKE '%低估强队第三球%'
   OR s.tags_json LIKE '%高估弱队进球%'
   OR s.tags_json LIKE '%尾部未进入主次%'
   OR s.tags_json LIKE '%热门方向错误%'
   OR s.tags_json LIKE '%BTTS误判%'
   OR s.tags_json LIKE '%淘汰赛热门出局%'
   OR s.tags_json LIKE '%高波动淘汰赛%'
ORDER BY s.created_at DESC;

-- 2. 按标签检索相似比赛（如已把标签拆入 historical_sample_tags）
SELECT
    m.match_id,
    m.team_a,
    m.team_b,
    m.match_date,
    p.primary_score,
    p.alternative_scores_json,
    m.actual_score_a || '-' || m.actual_score_b AS actual_score,
    r.error_types_json,
    r.reusable_lessons_json
FROM historical_sample_tags t
JOIN matches m ON m.match_id = t.match_id
LEFT JOIN predictions p ON p.match_id = m.match_id
LEFT JOIN post_match_reviews r ON r.match_id = m.match_id
WHERE t.tag IN (
    '低估强队第三球',
    '高空定位球错位',
    '弱队第二球能力',
    '弱队第二球',
    '强队零封能力',
    '巨星超额进球',
    '过度锁定低比分',
    '低估弱队第二球',
    '高估弱队进球',
    '尾部未进入主次',
    '热门方向错误',
    'BTTS误判',
    '淘汰赛热门出局',
    '高波动淘汰赛'
)
ORDER BY m.match_date DESC;

-- 3. 检索某个维度高分的历史样本
SELECT
    m.match_id,
    m.team_a,
    m.team_b,
    d.dimension_key,
    d.score,
    d.evidence,
    p.primary_score,
    m.actual_score_a || '-' || m.actual_score_b AS actual_score
FROM dimension_scores d
JOIN matches m ON m.match_id = d.match_id
LEFT JOIN predictions p ON p.match_id = m.match_id
WHERE d.dimension_key = 'strong_third_goal'
  AND d.score >= 4
ORDER BY m.match_date DESC;

-- 4. 检索预测失败样本，用于避免重复犯错
SELECT
    m.match_id,
    m.team_a,
    m.team_b,
    p.primary_score,
    r.actual_score,
    r.error_types_json,
    r.failure_reasons_json,
    r.rule_weight_suggestions_json
FROM post_match_reviews r
JOIN matches m ON m.match_id = r.match_id
LEFT JOIN predictions p ON p.match_id = m.match_id
WHERE r.error_types_json LIKE '%低估强队第三球%'
   OR r.error_types_json LIKE '%高估弱队进球%'
   OR r.error_types_json LIKE '%低估平局%'
   OR r.error_types_json LIKE '%过度锁定低比分%'
   OR r.error_types_json LIKE '%低估弱队第二球%'
   OR r.error_types_json LIKE '%尾部未进入主次%'
   OR r.error_types_json LIKE '%热门方向错误%'
   OR r.error_types_json LIKE '%BTTS误判%'
ORDER BY r.reviewed_at DESC;

-- 6. 失败样本路由：返回失败原因、可复用教训和建议动作
SELECT
    s.match_id,
    s.teams_text,
    s.predicted_score,
    s.actual_score,
    s.error_types_json,
    s.reusable_lessons_json,
    s.tags_json,
    s.notes,
    CASE
        WHEN s.tags_json LIKE '%过度锁定低比分%'
            THEN '不得默认锁死0-0/1-0/1-1，必须保留事件链高比分路径'
        WHEN s.tags_json LIKE '%低估弱队第二球%'
            THEN '弱队存在第二球路径时，至少进入次选或明确尾部'
        WHEN s.tags_json LIKE '%低估强队第三球%'
            THEN '强队巨星/替补/事件收益明显时，必须保留3球比分'
        WHEN s.tags_json LIKE '%高估弱队进球%'
            THEN '弱队只有单一路径或核心不首发时，下调BTTS和弱队一球'
        WHEN s.tags_json LIKE '%尾部未进入主次%'
            THEN '尾部路径若证据充足，仲裁需解释拒绝或上调到次选'
        WHEN s.tags_json LIKE '%热门方向错误%'
            THEN '热门方向需复核防线漏洞、阵容异动和弱队克制点'
        WHEN s.tags_json LIKE '%BTTS误判%'
            THEN '重新裁决弱队进球路径与零封冲突'
        ELSE '按历史误差标签调整对应比分路径'
    END AS suggested_action
FROM historical_samples s
WHERE s.tags_json LIKE '%过度锁定低比分%'
   OR s.tags_json LIKE '%低估弱队第二球%'
   OR s.tags_json LIKE '%低估强队第三球%'
   OR s.tags_json LIKE '%高估弱队进球%'
   OR s.tags_json LIKE '%尾部未进入主次%'
   OR s.tags_json LIKE '%热门方向错误%'
   OR s.tags_json LIKE '%BTTS误判%'
ORDER BY s.created_at DESC;

-- 5. 检索某支球队历史样本
SELECT
    m.match_id,
    m.team_a,
    m.team_b,
    p.primary_score,
    m.actual_score_a || '-' || m.actual_score_b AS actual_score,
    r.error_types_json
FROM matches m
LEFT JOIN predictions p ON p.match_id = m.match_id
LEFT JOIN post_match_reviews r ON r.match_id = m.match_id
WHERE m.team_a = :team_name OR m.team_b = :team_name
ORDER BY m.match_date DESC;
