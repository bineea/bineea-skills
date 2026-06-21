-- 标准维度目录
INSERT OR REPLACE INTO dimension_catalog(dimension_key, dimension_name, default_score, description, updated_at) VALUES
('base_strength','赛前基础层',3,'排名/Elo/阵容深度/大赛经验/教练稳定性',datetime('now')),
('player_status','球员个体状态与实力层',3,'关键球员状态/是否首发/预计时间/伤停',datetime('now')),
('player_type_structure','球员类型结构层',3,'速度型/支点型/压迫型/组织型等类型结构',datetime('now')),
('key_matchups','关键对位层',3,'边锋对边卫/中锋对中卫/高压对出球等',datetime('now')),
('historical_style','历史球队风格层',3,'长期风格和惯性打法',datetime('now')),
('style_counter','风格克制矩阵',3,'A队弱点是否正好被B队强项击中',datetime('now')),
('recent_form','近期状态层',3,'近5-10场进失球/强弱队表现/下半场表现',datetime('now')),
('goal_distribution','进球分布层',3,'xG/射门/射正/重大机会/非常规进球',datetime('now')),
('strong_second_goal','强队第二球能力',3,'强队能否把优势转化为第二球',datetime('now')),
('strong_third_goal','强队第三球与大胜能力',3,'巨星/替补/下半场调整/对手崩盘',datetime('now')),
('weak_first_goal','弱队第一球能力',3,'弱队是否有明确一球路径',datetime('now')),
('weak_second_goal','弱队第二球能力',3,'弱队是否有多点进攻或第二进球路径',datetime('now')),
('favorite_defense','热门球队防守脆弱度',3,'热门球队是否容易被反击/定位球惩罚',datetime('now')),
('clean_sheet','零封能力',3,'强队控场/反抢/门将/弱队核心状态',datetime('now')),
('tactical_matchup','战术匹配层',3,'控球反击/高压出球/防线高度/定位球对位',datetime('now')),
('stage_psychology','比赛阶段与心理层',3,'小组首轮谨慎/混乱/净胜球需求',datetime('now')),
('draw_risk','平局风险指数',3,'0-0/1-1/2-2不同平局类型',datetime('now')),
('lineup_injuries','阵容与伤停层',3,'中锋/中卫/后腰/门将/核心替补',datetime('now')),
('team_harmony_social','队内关系与社媒层',3,'更衣室/采访/社媒/场上配合信号',datetime('now')),
('environment_schedule','环境与赛程层',3,'天气/开球时间/旅行/休息/补水暂停',datetime('now')),
('referee_events','裁判与事件触发层',3,'点球/红牌/补时/早球/门将失误',datetime('now')),
('market_odds','赔率与市场层',3,'胜平负/让球/大小球/双方进球赔率',datetime('now')),
('dynamic_triggers','动态比分触发器',3,'弱队先进球/强队早球/连续定位球等',datetime('now')),
('star_overperformance','巨星超额进球能力',3,'姆巴佩/梅西/哈兰德式突破均值能力',datetime('now')),
('set_piece_aerial','高空/定位球错位',3,'身高/角球/头球/二点球优势',datetime('now')),
('pressing_error_path','前锋压迫与门将后场失误',3,'逼抢门将中卫/脱手/乌龙/补射',datetime('now'));

-- 已复盘历史样本
INSERT OR REPLACE INTO matches(match_id, competition, match_date, stage, venue, team_a, team_b, actual_score_a, actual_score_b, created_at, updated_at) VALUES
('2026-06-16_BEL_EGY','FIFA World Cup 2026','2026-06-16','Group stage','','比利时','埃及',1,1,datetime('now'),datetime('now')),
('2026-06-16_IRN_NZL','FIFA World Cup 2026','2026-06-16','Group stage','','伊朗','新西兰',2,2,datetime('now'),datetime('now')),
('2026-06-17_FRA_SEN','FIFA World Cup 2026','2026-06-17','Group stage','','法国','塞内加尔',3,1,datetime('now'),datetime('now')),
('2026-06-17_IRQ_NOR','FIFA World Cup 2026','2026-06-17','Group stage','','伊拉克','挪威',1,4,datetime('now'),datetime('now')),
('2026-06-17_ARG_ALG','FIFA World Cup 2026','2026-06-17','Group stage','','阿根廷','阿尔及利亚',3,0,datetime('now'),datetime('now'));

INSERT OR REPLACE INTO historical_samples(match_id, teams_text, predicted_score, actual_score, error_types_json, reusable_lessons_json, tags_json, notes, created_at) VALUES
('2026-06-16_BEL_EGY','比利时 vs 埃及','2-1','1-1','["高估强队第二球","低估弱队持续进攻","低估1-1平局"]','["热门球队射门多但射正质量一般时，第二球概率要下调","弱队射门和控球接近热门时，1-1应进入主区间"]','["低估平局","弱队第一球能力","强队第二球不足"]','比利时方向正确但高估第二球。',datetime('now')),
('2026-06-16_IRN_NZL','伊朗 vs 新西兰','1-0','2-2','["低估弱队第二球","低估首战混乱指数","低估比赛开放度"]','["弱队有多点进攻或定位球+运动战双路径时，2-2不能只作为边缘冷门","首轮既可能谨慎，也可能因早球和失误变开放"]','["弱队第二球能力","2-2平局","首战混乱"]','低估新西兰第二球路径。',datetime('now')),
('2026-06-17_FRA_SEN','法国 vs 塞内加尔','2-1','3-1','["低估强队第三球","低估下半场调整","低估巨星超额进球"]','["强队有健康巨星和替补冲击时，3-1要进入主预测区间","下半场xG显著提升的强队传统应上调第三球"]','["强队第三球","巨星超额进球","替补冲击"]','低估法国下半场提速和姆巴佩超额能力。',datetime('now')),
('2026-06-17_IRQ_NOR','伊拉克 vs 挪威','1-3','1-4','["低估强队第四球","低估高空定位球错位","低估前锋压迫制造进球"]','["哈兰德类中锋不仅提供终结，还提供压迫门将、制造混战和乌龙的路径","强队高空优势明显时，4-1应进入候选区间"]','["高空定位球错位","前锋压迫失误","强队第四球"]','低估挪威高空和压迫制造进球。',datetime('now')),
('2026-06-17_ARG_ALG','阿根廷 vs 阿尔及利亚','2-1','3-0','["高估弱队进球","低估强队零封能力","低估巨星健康状态"]','["弱队核心攻击手不首发或出场时间受限时，不能机械给弱队一球","强队控场和反抢强时，2-1应修正为2-0或3-0"]','["强队零封能力","高估弱队进球","巨星超额进球"]','低估阿根廷零封和梅西状态。',datetime('now'));

INSERT OR IGNORE INTO historical_sample_tags(match_id, tag, note) VALUES
('2026-06-16_BEL_EGY','低估平局','1-1应进入主区间'),
('2026-06-16_BEL_EGY','强队第二球不足','射正质量不足'),
('2026-06-16_IRN_NZL','弱队第二球能力','2-2平局样本'),
('2026-06-16_IRN_NZL','首战混乱','首轮也可能开放'),
('2026-06-17_FRA_SEN','强队第三球','下半场提速'),
('2026-06-17_FRA_SEN','巨星超额进球','姆巴佩远射/个人能力'),
('2026-06-17_IRQ_NOR','高空定位球错位','哈兰德/挪威高点'),
('2026-06-17_IRQ_NOR','前锋压迫失误','压迫门将制造进球'),
('2026-06-17_ARG_ALG','强队零封能力','阿根廷控场'),
('2026-06-17_ARG_ALG','高估弱队进球','弱队核心出场/路径不足');
