-- 球员近期逐场表现检索

-- 1. 指定球员最近5场表现
SELECT
    m.match_date,
    m.competition,
    m.team_a,
    m.team_b,
    pms.team_name,
    pms.player_name,
    pms.started,
    pms.minutes_played,
    pms.goals,
    pms.assists,
    pms.shots,
    pms.shots_on_target,
    pms.xg,
    pms.xa,
    pms.key_passes,
    pms.tackles,
    pms.interceptions,
    pms.saves,
    pms.rating
FROM player_match_stats pms
JOIN matches m ON m.match_id = pms.match_id
WHERE pms.player_id = :player_id
ORDER BY m.match_date DESC
LIMIT 5;

-- 2. 指定球员最近5场汇总
WITH recent AS (
    SELECT pms.*
    FROM player_match_stats pms
    JOIN matches m ON m.match_id = pms.match_id
    WHERE pms.player_id = :player_id
    ORDER BY m.match_date DESC
    LIMIT 5
)
SELECT
    player_name,
    COUNT(*) AS appearances,
    SUM(started) AS starts,
    SUM(minutes_played) AS minutes,
    SUM(goals) AS goals,
    SUM(assists) AS assists,
    SUM(shots) AS shots,
    SUM(shots_on_target) AS shots_on_target,
    SUM(xg) AS xg,
    SUM(xa) AS xa,
    AVG(rating) AS average_rating
FROM recent
GROUP BY player_id, player_name;

-- 3. 指定球队最近比赛中的球员使用和产出
SELECT
    m.match_date,
    pms.player_name,
    pms.position,
    pms.started,
    pms.minutes_played,
    pms.goals,
    pms.assists,
    pms.shots_on_target,
    pms.xg,
    pms.key_passes,
    pms.rating
FROM player_match_stats pms
JOIN matches m ON m.match_id = pms.match_id
WHERE pms.team_name = :team_name
ORDER BY m.match_date DESC, pms.started DESC, pms.minutes_played DESC;

-- 4. 最近5场球队球员贡献汇总
WITH recent_matches AS (
    SELECT match_id
    FROM matches
    WHERE team_a = :team_name OR team_b = :team_name
    ORDER BY match_date DESC
    LIMIT 5
)
SELECT
    pms.player_id,
    pms.player_name,
    COUNT(*) AS appearances,
    SUM(pms.started) AS starts,
    SUM(pms.minutes_played) AS minutes,
    SUM(pms.goals) AS goals,
    SUM(pms.assists) AS assists,
    SUM(pms.shots_on_target) AS shots_on_target,
    SUM(pms.xg) AS xg,
    SUM(pms.xa) AS xa,
    AVG(pms.rating) AS average_rating
FROM player_match_stats pms
JOIN recent_matches rm ON rm.match_id = pms.match_id
WHERE pms.team_name = :team_name
GROUP BY pms.player_id, pms.player_name
ORDER BY minutes DESC, goals DESC, assists DESC;
