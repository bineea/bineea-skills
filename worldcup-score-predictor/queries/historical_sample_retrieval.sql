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
   OR s.tags_json LIKE '%强队零封能力%'
   OR s.tags_json LIKE '%巨星超额进球%'
   OR s.tags_json LIKE '%领先后收缩%'
   OR s.tags_json LIKE '%双红牌%'
   OR s.tags_json LIKE '%极端比分%'
   OR s.tags_json LIKE '%门将失误%'
   OR s.tags_json LIKE '%持续机会压力%'
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
    '强队零封能力',
    '巨星超额进球'
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
ORDER BY r.reviewed_at DESC;

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
