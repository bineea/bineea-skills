-- 世界杯比分预测知识库 SQLite Schema
-- 只定义数据结构，不包含预测执行逻辑。

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS teams (
    team_id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL UNIQUE,
    fifa_rank INTEGER,
    elo_rating REAL,
    historical_style TEXT,
    strengths_json TEXT DEFAULT '[]',
    weaknesses_json TEXT DEFAULT '[]',
    notes TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    position TEXT,
    player_type TEXT,
    current_status TEXT,
    is_expected_starter INTEGER,
    expected_minutes INTEGER,
    form_score INTEGER CHECK(form_score BETWEEN 1 AND 5),
    ability_tags_json TEXT DEFAULT '[]',
    risk_tags_json TEXT DEFAULT '[]',
    evidence TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(team_id, player_name),
    FOREIGN KEY(team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    competition TEXT NOT NULL,
    match_date TEXT NOT NULL,
    stage TEXT,
    venue TEXT,
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    actual_score_a INTEGER,
    actual_score_b INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dimension_catalog (
    dimension_key TEXT PRIMARY KEY,
    dimension_name TEXT NOT NULL,
    default_score INTEGER NOT NULL DEFAULT 3 CHECK(default_score BETWEEN 1 AND 5),
    description TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_sources (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    source_ref TEXT,
    source_title TEXT,
    source_url TEXT,
    source_type TEXT,
    summary TEXT,
    reliability TEXT DEFAULT 'medium',
    captured_at TEXT NOT NULL,
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_match_sources_ref
ON match_sources(match_id, source_ref);

CREATE TABLE IF NOT EXISTS dimension_scores (
    score_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    dimension_key TEXT NOT NULL,
    dimension_name TEXT NOT NULL,
    score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
    confidence TEXT NOT NULL,
    evidence TEXT NOT NULL,
    source_ids_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(match_id, dimension_key),
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    predicted_at TEXT NOT NULL,
    primary_score TEXT NOT NULL,
    alternative_scores_json TEXT NOT NULL,
    result_tendency TEXT NOT NULL,
    total_goals_range TEXT NOT NULL,
    both_teams_to_score_level TEXT NOT NULL,
    strong_team_second_goal_level TEXT NOT NULL,
    strong_team_third_goal_level TEXT NOT NULL,
    weak_team_first_goal_level TEXT NOT NULL,
    weak_team_second_goal_level TEXT NOT NULL,
    clean_sheet_level TEXT NOT NULL,
    draw_type TEXT,
    confidence TEXT NOT NULL,
    trigger_conditions_json TEXT DEFAULT '[]',
    rationale TEXT NOT NULL,
    report_markdown TEXT,
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE TABLE IF NOT EXISTS post_match_stats (
    stats_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL UNIQUE,
    shots_a INTEGER,
    shots_b INTEGER,
    shots_on_target_a INTEGER,
    shots_on_target_b INTEGER,
    xg_a REAL,
    xg_b REAL,
    possession_a REAL,
    possession_b REAL,
    corners_a INTEGER,
    corners_b INTEGER,
    set_piece_goals INTEGER DEFAULT 0,
    penalty_goals INTEGER DEFAULT 0,
    own_goals INTEGER DEFAULT 0,
    red_cards INTEGER DEFAULT 0,
    goalkeeper_errors INTEGER DEFAULT 0,
    stoppage_time_goals INTEGER DEFAULT 0,
    goal_timeline_json TEXT DEFAULT '[]',
    substitutions_json TEXT DEFAULT '[]',
    notes TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

-- 每场比赛的球员级表现。未知数据保存为 NULL，不得用 0 代替。
CREATE TABLE IF NOT EXISTS player_match_stats (
    player_match_stats_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    player_name TEXT NOT NULL,
    shirt_number INTEGER,
    position TEXT,
    lineup_status TEXT NOT NULL CHECK(lineup_status IN ('starter', 'substitute', 'unused')),
    started INTEGER NOT NULL CHECK(started IN (0, 1)),
    captain INTEGER NOT NULL DEFAULT 0 CHECK(captain IN (0, 1)),
    minutes_played INTEGER NOT NULL CHECK(minutes_played BETWEEN 0 AND 130),
    substituted_on_minute INTEGER CHECK(substituted_on_minute BETWEEN 0 AND 130),
    substituted_off_minute INTEGER CHECK(substituted_off_minute BETWEEN 0 AND 130),
    goals INTEGER,
    assists INTEGER,
    shots INTEGER,
    shots_on_target INTEGER,
    xg REAL,
    xa REAL,
    key_passes INTEGER,
    big_chances_created INTEGER,
    touches INTEGER,
    touches_in_opposition_box INTEGER,
    passes_attempted INTEGER,
    passes_completed INTEGER,
    dribbles_attempted INTEGER,
    dribbles_completed INTEGER,
    tackles INTEGER,
    interceptions INTEGER,
    clearances INTEGER,
    blocks INTEGER,
    recoveries INTEGER,
    duels_total INTEGER,
    duels_won INTEGER,
    aerial_duels_total INTEGER,
    aerial_duels_won INTEGER,
    fouls_committed INTEGER,
    fouls_drawn INTEGER,
    offsides INTEGER,
    saves INTEGER,
    goals_conceded INTEGER,
    penalties_saved INTEGER,
    yellow_cards INTEGER,
    red_cards INTEGER,
    own_goals INTEGER,
    rating REAL,
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(match_id, player_id),
    FOREIGN KEY(match_id) REFERENCES matches(match_id),
    FOREIGN KEY(player_id) REFERENCES players(player_id),
    FOREIGN KEY(team_id) REFERENCES teams(team_id)
);

-- 保存进球、助攻、换人、牌和关键失误等可归因事件。
CREATE TABLE IF NOT EXISTS player_match_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    event_ref TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    player_id INTEGER,
    related_player_id INTEGER,
    event_type TEXT NOT NULL,
    minute INTEGER NOT NULL CHECK(minute BETWEEN 0 AND 130),
    stoppage_minute INTEGER NOT NULL DEFAULT 0 CHECK(stoppage_minute BETWEEN 0 AND 30),
    outcome TEXT,
    xg REAL,
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(match_id, event_ref),
    FOREIGN KEY(match_id) REFERENCES matches(match_id),
    FOREIGN KEY(team_id) REFERENCES teams(team_id),
    FOREIGN KEY(player_id) REFERENCES players(player_id),
    FOREIGN KEY(related_player_id) REFERENCES players(player_id)
);

-- 记录每场球员数据是否完整，供预测前和复盘后审计。
CREATE TABLE IF NOT EXISTS post_match_data_imports (
    match_id TEXT PRIMARY KEY,
    data_completeness TEXT NOT NULL CHECK(data_completeness IN ('full', 'partial')),
    player_rows INTEGER NOT NULL,
    team_a_active_players INTEGER NOT NULL,
    team_b_active_players INTEGER NOT NULL,
    event_rows INTEGER NOT NULL,
    source_rows INTEGER NOT NULL,
    imported_at TEXT NOT NULL,
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_key TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_match_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    predicted_score TEXT,
    actual_score TEXT NOT NULL,
    error_types_json TEXT NOT NULL,
    failure_reasons_json TEXT NOT NULL,
    reusable_lessons_json TEXT NOT NULL,
    rule_weight_suggestions_json TEXT NOT NULL,
    review_markdown TEXT,
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE TABLE IF NOT EXISTS historical_samples (
    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL UNIQUE,
    teams_text TEXT NOT NULL,
    predicted_score TEXT,
    actual_score TEXT NOT NULL,
    error_types_json TEXT NOT NULL,
    reusable_lessons_json TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_sample_tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    note TEXT,
    UNIQUE(match_id, tag),
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE INDEX IF NOT EXISTS idx_dimension_scores_match ON dimension_scores(match_id);
CREATE INDEX IF NOT EXISTS idx_dimension_scores_key_score ON dimension_scores(dimension_key, score);
CREATE INDEX IF NOT EXISTS idx_reviews_match ON post_match_reviews(match_id);
CREATE INDEX IF NOT EXISTS idx_sample_tags_tag ON historical_sample_tags(tag);
CREATE INDEX IF NOT EXISTS idx_historical_samples_match ON historical_samples(match_id);
CREATE INDEX IF NOT EXISTS idx_player_match_stats_match ON player_match_stats(match_id);
CREATE INDEX IF NOT EXISTS idx_player_match_stats_player_date ON player_match_stats(player_id, match_id);
CREATE INDEX IF NOT EXISTS idx_player_match_stats_team ON player_match_stats(team_id, match_id);
CREATE INDEX IF NOT EXISTS idx_player_match_events_match_minute ON player_match_events(match_id, minute);
CREATE INDEX IF NOT EXISTS idx_player_match_events_player ON player_match_events(player_id, match_id);
CREATE INDEX IF NOT EXISTS idx_post_match_data_imports_completeness
ON post_match_data_imports(data_completeness);
