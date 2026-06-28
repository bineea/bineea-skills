#!/usr/bin/env python3
"""从 ESPN 比赛中心生成赛后数据导入文件。"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = SKILL_ROOT / "data" / "imports"
SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/"
    "fifa.world/summary?event={event_id}"
)

MATCHES = [
    {
        "event_id": "760415",
        "match_id": "2026-06-12_MEX_RSA",
        "match_date": "2026-06-12",
        "team_a_en": "Mexico",
        "team_b_en": "South Africa",
        "team_a": "墨西哥",
        "team_b": "南非",
        "score_a": 2,
        "score_b": 0,
    },
    {
        "event_id": "760414",
        "match_id": "2026-06-12_KOR_CZE",
        "match_date": "2026-06-12",
        "team_a_en": "South Korea",
        "team_b_en": "Czechia",
        "team_a": "韩国",
        "team_b": "捷克",
        "score_a": 2,
        "score_b": 1,
    },
    {
        "event_id": "760416",
        "match_id": "2026-06-13_CAN_BIH",
        "match_date": "2026-06-13",
        "team_a_en": "Canada",
        "team_b_en": "Bosnia-Herzegovina",
        "team_a": "加拿大",
        "team_b": "波黑",
        "score_a": 1,
        "score_b": 1,
    },
    {
        "event_id": "760417",
        "match_id": "2026-06-13_USA_PAR",
        "match_date": "2026-06-13",
        "team_a_en": "United States",
        "team_b_en": "Paraguay",
        "team_a": "美国",
        "team_b": "巴拉圭",
        "score_a": 4,
        "score_b": 1,
    },
    {
        "event_id": "760420",
        "match_id": "2026-06-14_QAT_SUI",
        "match_date": "2026-06-14",
        "team_a_en": "Qatar",
        "team_b_en": "Switzerland",
        "team_a": "卡塔尔",
        "team_b": "瑞士",
        "score_a": 1,
        "score_b": 1,
    },
    {
        "event_id": "760419",
        "match_id": "2026-06-14_BRA_MAR",
        "match_date": "2026-06-14",
        "team_a_en": "Brazil",
        "team_b_en": "Morocco",
        "team_a": "巴西",
        "team_b": "摩洛哥",
        "score_a": 1,
        "score_b": 1,
    },
    {
        "event_id": "760418",
        "match_id": "2026-06-14_HAI_SCO",
        "match_date": "2026-06-14",
        "team_a_en": "Haiti",
        "team_b_en": "Scotland",
        "team_a": "海地",
        "team_b": "苏格兰",
        "score_a": 0,
        "score_b": 1,
    },
    {
        "event_id": "760421",
        "match_id": "2026-06-14_AUS_TUR",
        "match_date": "2026-06-14",
        "team_a_en": "Australia",
        "team_b_en": "Türkiye",
        "team_a": "澳大利亚",
        "team_b": "土耳其",
        "score_a": 2,
        "score_b": 0,
    },
    {
        "event_id": "760422",
        "match_id": "2026-06-15_GER_CUW",
        "match_date": "2026-06-15",
        "team_a_en": "Germany",
        "team_b_en": "Curaçao",
        "team_a": "德国",
        "team_b": "库拉索",
        "score_a": 7,
        "score_b": 1,
    },
    {
        "event_id": "760425",
        "match_id": "2026-06-15_NED_JPN",
        "match_date": "2026-06-15",
        "team_a_en": "Netherlands",
        "team_b_en": "Japan",
        "team_a": "荷兰",
        "team_b": "日本",
        "score_a": 2,
        "score_b": 2,
    },
    {
        "event_id": "760423",
        "match_id": "2026-06-15_CIV_ECU",
        "match_date": "2026-06-15",
        "team_a_en": "Ivory Coast",
        "team_b_en": "Ecuador",
        "team_a": "科特迪瓦",
        "team_b": "厄瓜多尔",
        "score_a": 1,
        "score_b": 0,
    },
    {
        "event_id": "760424",
        "match_id": "2026-06-15_SWE_TUN",
        "match_date": "2026-06-15",
        "team_a_en": "Sweden",
        "team_b_en": "Tunisia",
        "team_a": "瑞典",
        "team_b": "突尼斯",
        "score_a": 5,
        "score_b": 1,
    },
    {
        "event_id": "760428",
        "match_id": "2026-06-16_ESP_CPV",
        "match_date": "2026-06-16",
        "team_a_en": "Spain",
        "team_b_en": "Cape Verde",
        "team_a": "西班牙",
        "team_b": "佛得角",
        "score_a": 0,
        "score_b": 0,
    },
    {
        "event_id": "760426",
        "match_id": "2026-06-16_BEL_EGY",
        "match_date": "2026-06-16",
        "team_a_en": "Belgium",
        "team_b_en": "Egypt",
        "team_a": "比利时",
        "team_b": "埃及",
        "score_a": 1,
        "score_b": 1,
    },
    {
        "event_id": "760429",
        "match_id": "2026-06-16_KSA_URU",
        "match_date": "2026-06-16",
        "team_a_en": "Saudi Arabia",
        "team_b_en": "Uruguay",
        "team_a": "沙特阿拉伯",
        "team_b": "乌拉圭",
        "score_a": 1,
        "score_b": 1,
    },
    {
        "event_id": "760427",
        "match_id": "2026-06-16_IRN_NZL",
        "match_date": "2026-06-16",
        "team_a_en": "Iran",
        "team_b_en": "New Zealand",
        "team_a": "伊朗",
        "team_b": "新西兰",
        "score_a": 2,
        "score_b": 2,
    },
    {
        "event_id": "760432",
        "match_id": "2026-06-17_FRA_SEN",
        "match_date": "2026-06-17",
        "team_a_en": "France",
        "team_b_en": "Senegal",
        "team_a": "法国",
        "team_b": "塞内加尔",
        "score_a": 3,
        "score_b": 1,
    },
    {
        "event_id": "760430",
        "match_id": "2026-06-17_IRQ_NOR",
        "match_date": "2026-06-17",
        "team_a_en": "Iraq",
        "team_b_en": "Norway",
        "team_a": "伊拉克",
        "team_b": "挪威",
        "score_a": 1,
        "score_b": 4,
    },
    {
        "event_id": "760433",
        "match_id": "2026-06-17_ARG_ALG",
        "match_date": "2026-06-17",
        "team_a_en": "Argentina",
        "team_b_en": "Algeria",
        "team_a": "阿根廷",
        "team_b": "阿尔及利亚",
        "score_a": 3,
        "score_b": 0,
    },
    {
        "event_id": "760431",
        "match_id": "2026-06-17_AUT_JOR",
        "match_date": "2026-06-17",
        "team_a_en": "Austria",
        "team_b_en": "Jordan",
        "team_a": "奥地利",
        "team_b": "约旦",
        "score_a": 3,
        "score_b": 1,
    },
    {
        "event_id": "760435",
        "match_id": "2026-06-18_POR_COD",
        "match_date": "2026-06-18",
        "team_a_en": "Portugal",
        "team_b_en": "Congo DR",
        "team_a": "葡萄牙",
        "team_b": "刚果（金）",
        "score_a": 1,
        "score_b": 1,
    },
    {
        "event_id": "760437",
        "match_id": "2026-06-18_ENG_CRO",
        "match_date": "2026-06-18",
        "team_a_en": "England",
        "team_b_en": "Croatia",
        "team_a": "英格兰",
        "team_b": "克罗地亚",
        "score_a": 4,
        "score_b": 2,
    },
    {
        "event_id": "760434",
        "match_id": "2026-06-18_GHA_PAN",
        "match_date": "2026-06-18",
        "team_a_en": "Ghana",
        "team_b_en": "Panama",
        "team_a": "加纳",
        "team_b": "巴拿马",
        "score_a": 1,
        "score_b": 0,
    },
    {
        "event_id": "760436",
        "match_id": "2026-06-18_UZB_COL",
        "match_date": "2026-06-18",
        "team_a_en": "Uzbekistan",
        "team_b_en": "Colombia",
        "team_a": "乌兹别克斯坦",
        "team_b": "哥伦比亚",
        "score_a": 1,
        "score_b": 3,
    },
    {
        "event_id": "760443",
        "match_id": "2026-06-20_TUR_PAR",
        "match_date": "2026-06-20",
        "team_a_en": "Türkiye",
        "team_b_en": "Paraguay",
        "team_a": "土耳其",
        "team_b": "巴拉圭",
        "score_a": 0,
        "score_b": 1,
    },
    {
        "event_id": "760447",
        "match_id": "2026-06-21_NED_SWE",
        "match_date": "2026-06-21",
        "team_a_en": "Netherlands",
        "team_b_en": "Sweden",
        "team_a": "荷兰",
        "team_b": "瑞典",
        "score_a": 5,
        "score_b": 1,
    },
    {
        "event_id": "760448",
        "match_id": "2026-06-21_GER_CIV",
        "match_date": "2026-06-21",
        "team_a_en": "Germany",
        "team_b_en": "Ivory Coast",
        "team_a": "德国",
        "team_b": "科特迪瓦",
        "score_a": 2,
        "score_b": 1,
    },
    {
        "event_id": "760446",
        "match_id": "2026-06-21_ECU_CUW",
        "match_date": "2026-06-21",
        "team_a_en": "Ecuador",
        "team_b_en": "Curaçao",
        "team_a": "厄瓜多尔",
        "team_b": "库拉索",
        "score_a": 0,
        "score_b": 0,
    },
    {
        "event_id": "760449",
        "match_id": "2026-06-21_TUN_JPN",
        "match_date": "2026-06-21",
        "team_a_en": "Tunisia",
        "team_b_en": "Japan",
        "team_a": "突尼斯",
        "team_b": "日本",
        "score_a": 0,
        "score_b": 4,
    },
    {
        "event_id": "760453",
        "match_id": "2026-06-22_ESP_KSA",
        "match_date": "2026-06-22",
        "team_a_en": "Spain",
        "team_b_en": "Saudi Arabia",
        "team_a": "西班牙",
        "team_b": "沙特阿拉伯",
        "score_a": 4,
        "score_b": 0,
    },
    {
        "event_id": "760451",
        "match_id": "2026-06-22_BEL_IRN",
        "match_date": "2026-06-22",
        "team_a_en": "Belgium",
        "team_b_en": "Iran",
        "team_a": "比利时",
        "team_b": "伊朗",
        "score_a": 0,
        "score_b": 0,
    },
    {
        "event_id": "760450",
        "match_id": "2026-06-22_URU_CPV",
        "match_date": "2026-06-22",
        "team_a_en": "Uruguay",
        "team_b_en": "Cape Verde",
        "team_a": "乌拉圭",
        "team_b": "佛得角",
        "score_a": 2,
        "score_b": 2,
    },
    {
        "event_id": "760452",
        "match_id": "2026-06-22_NZL_EGY",
        "match_date": "2026-06-22",
        "team_a_en": "New Zealand",
        "team_b_en": "Egypt",
        "team_a": "新西兰",
        "team_b": "埃及",
        "score_a": 1,
        "score_b": 3,
    },
    {
        "event_id": "760456",
        "match_id": "2026-06-23_ARG_AUT",
        "match_date": "2026-06-23",
        "team_a_en": "Argentina",
        "team_b_en": "Austria",
        "team_a": "阿根廷",
        "team_b": "奥地利",
        "score_a": 2,
        "score_b": 0,
    },
    {
        "event_id": "760457",
        "match_id": "2026-06-23_FRA_IRQ",
        "match_date": "2026-06-23",
        "team_a_en": "France",
        "team_b_en": "Iraq",
        "team_a": "法国",
        "team_b": "伊拉克",
        "score_a": 3,
        "score_b": 0,
    },
    {
        "event_id": "760454",
        "match_id": "2026-06-23_NOR_SEN",
        "match_date": "2026-06-23",
        "team_a_en": "Norway",
        "team_b_en": "Senegal",
        "team_a": "挪威",
        "team_b": "塞内加尔",
        "score_a": 3,
        "score_b": 2,
    },
    {
        "event_id": "760455",
        "match_id": "2026-06-23_JOR_ALG",
        "match_date": "2026-06-23",
        "team_a_en": "Jordan",
        "team_b_en": "Algeria",
        "team_a": "约旦",
        "team_b": "阿尔及利亚",
        "score_a": 1,
        "score_b": 2,
    },
    {
        "event_id": "760461",
        "match_id": "2026-06-24_POR_UZB",
        "match_date": "2026-06-24",
        "team_a_en": "Portugal",
        "team_b_en": "Uzbekistan",
        "team_a": "葡萄牙",
        "team_b": "乌兹别克斯坦",
        "score_a": 5,
        "score_b": 0,
    },
    {
        "event_id": "760458",
        "match_id": "2026-06-24_ENG_GHA",
        "match_date": "2026-06-24",
        "team_a_en": "England",
        "team_b_en": "Ghana",
        "team_a": "英格兰",
        "team_b": "加纳",
        "score_a": 0,
        "score_b": 0,
    },
    {
        "event_id": "760460",
        "match_id": "2026-06-24_PAN_CRO",
        "match_date": "2026-06-24",
        "team_a_en": "Panama",
        "team_b_en": "Croatia",
        "team_a": "巴拿马",
        "team_b": "克罗地亚",
        "score_a": 0,
        "score_b": 1,
    },
    {
        "event_id": "760459",
        "match_id": "2026-06-24_COL_COD",
        "match_date": "2026-06-24",
        "team_a_en": "Colombia",
        "team_b_en": "Congo DR",
        "team_a": "哥伦比亚",
        "team_b": "刚果（金）",
        "score_a": 1,
        "score_b": 0,
    },
    {
        "event_id": "760462",
        "match_id": "2026-06-25_BIH_QAT",
        "match_date": "2026-06-25",
        "team_a_en": "Bosnia-Herzegovina",
        "team_b_en": "Qatar",
        "team_a": "波黑",
        "team_b": "卡塔尔",
        "score_a": 3,
        "score_b": 1,
    },
    {
        "event_id": "760463",
        "match_id": "2026-06-25_SUI_CAN",
        "match_date": "2026-06-25",
        "team_a_en": "Switzerland",
        "team_b_en": "Canada",
        "team_a": "瑞士",
        "team_b": "加拿大",
        "score_a": 2,
        "score_b": 1,
    },
    {
        "event_id": "760464",
        "match_id": "2026-06-25_MAR_HAI",
        "match_date": "2026-06-25",
        "team_a_en": "Morocco",
        "team_b_en": "Haiti",
        "team_a": "摩洛哥",
        "team_b": "海地",
        "score_a": 4,
        "score_b": 2,
    },
    {
        "event_id": "760465",
        "match_id": "2026-06-25_SCO_BRA",
        "match_date": "2026-06-25",
        "team_a_en": "Scotland",
        "team_b_en": "Brazil",
        "team_a": "苏格兰",
        "team_b": "巴西",
        "score_a": 0,
        "score_b": 3,
    },
    {
        "event_id": "760467",
        "match_id": "2026-06-25_CZE_MEX",
        "match_date": "2026-06-25",
        "team_a_en": "Czechia",
        "team_b_en": "Mexico",
        "team_a": "捷克",
        "team_b": "墨西哥",
        "score_a": 0,
        "score_b": 3,
    },
    {
        "event_id": "760466",
        "match_id": "2026-06-25_RSA_KOR",
        "match_date": "2026-06-25",
        "team_a_en": "South Africa",
        "team_b_en": "South Korea",
        "team_a": "南非",
        "team_b": "韩国",
        "score_a": 1,
        "score_b": 0,
    },
    {
        "event_id": "760473",
        "match_id": "2026-06-26_CUW_CIV",
        "match_date": "2026-06-26",
        "team_a_en": "Curaçao",
        "team_b_en": "Ivory Coast",
        "team_a": "库拉索",
        "team_b": "科特迪瓦",
        "score_a": 0,
        "score_b": 2,
    },
    {
        "event_id": "760468",
        "match_id": "2026-06-26_ECU_GER",
        "match_date": "2026-06-26",
        "team_a_en": "Ecuador",
        "team_b_en": "Germany",
        "team_a": "厄瓜多尔",
        "team_b": "德国",
        "score_a": 2,
        "score_b": 1,
    },
    {
        "event_id": "760471",
        "match_id": "2026-06-26_JPN_SWE",
        "match_date": "2026-06-26",
        "team_a_en": "Japan",
        "team_b_en": "Sweden",
        "team_a": "日本",
        "team_b": "瑞典",
        "score_a": 1,
        "score_b": 1,
    },
    {
        "event_id": "760472",
        "match_id": "2026-06-26_TUN_NED",
        "match_date": "2026-06-26",
        "team_a_en": "Tunisia",
        "team_b_en": "Netherlands",
        "team_a": "突尼斯",
        "team_b": "荷兰",
        "score_a": 1,
        "score_b": 3,
    },
    {
        "event_id": "760469",
        "match_id": "2026-06-26_PAR_AUS",
        "match_date": "2026-06-26",
        "team_a_en": "Paraguay",
        "team_b_en": "Australia",
        "team_a": "巴拉圭",
        "team_b": "澳大利亚",
        "score_a": 0,
        "score_b": 0,
    },
    {
        "event_id": "760470",
        "match_id": "2026-06-26_TUR_USA",
        "match_date": "2026-06-26",
        "team_a_en": "Türkiye",
        "team_b_en": "United States",
        "team_a": "土耳其",
        "team_b": "美国",
        "score_a": 3,
        "score_b": 2,
    },
    {
        "event_id": "760475",
        "match_id": "2026-06-27_NOR_FRA",
        "match_date": "2026-06-27",
        "team_a_en": "Norway",
        "team_b_en": "France",
        "team_a": "挪威",
        "team_b": "法国",
        "score_a": 1,
        "score_b": 4,
    },
    {
        "event_id": "760474",
        "match_id": "2026-06-27_SEN_IRQ",
        "match_date": "2026-06-27",
        "team_a_en": "Senegal",
        "team_b_en": "Iraq",
        "team_a": "塞内加尔",
        "team_b": "伊拉克",
        "score_a": 5,
        "score_b": 0,
    },
    {
        "event_id": "760478",
        "match_id": "2026-06-27_CPV_KSA",
        "match_date": "2026-06-27",
        "team_a_en": "Cape Verde",
        "team_b_en": "Saudi Arabia",
        "team_a": "佛得角",
        "team_b": "沙特阿拉伯",
        "score_a": 0,
        "score_b": 0,
    },
    {
        "event_id": "760479",
        "match_id": "2026-06-27_URU_ESP",
        "match_date": "2026-06-27",
        "team_a_en": "Uruguay",
        "team_b_en": "Spain",
        "team_a": "乌拉圭",
        "team_b": "西班牙",
        "score_a": 0,
        "score_b": 1,
    },
    {
        "event_id": "760476",
        "match_id": "2026-06-27_EGY_IRN",
        "match_date": "2026-06-27",
        "team_a_en": "Egypt",
        "team_b_en": "Iran",
        "team_a": "埃及",
        "team_b": "伊朗",
        "score_a": 1,
        "score_b": 1,
    },
    {
        "event_id": "760477",
        "match_id": "2026-06-27_NZL_BEL",
        "match_date": "2026-06-27",
        "team_a_en": "New Zealand",
        "team_b_en": "Belgium",
        "team_a": "新西兰",
        "team_b": "比利时",
        "score_a": 1,
        "score_b": 5,
    },
    {
        "event_id": "760480",
        "match_id": "2026-06-28_CRO_GHA",
        "match_date": "2026-06-28",
        "team_a_en": "Croatia",
        "team_b_en": "Ghana",
        "team_a": "克罗地亚",
        "team_b": "加纳",
        "score_a": 2,
        "score_b": 1,
    },
    {
        "event_id": "760485",
        "match_id": "2026-06-28_PAN_ENG",
        "match_date": "2026-06-28",
        "team_a_en": "Panama",
        "team_b_en": "England",
        "team_a": "巴拿马",
        "team_b": "英格兰",
        "score_a": 0,
        "score_b": 2,
    },
]

PLAYER_FIELD_MAP = {
    "totalGoals": "goals",
    "goalAssists": "assists",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "foulsCommitted": "fouls_committed",
    "foulsSuffered": "fouls_drawn",
    "offsides": "offsides",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "ownGoals": "own_goals",
}

NULL_PLAYER_FIELDS = [
    "xg",
    "xa",
    "key_passes",
    "big_chances_created",
    "touches",
    "touches_in_opposition_box",
    "passes_attempted",
    "passes_completed",
    "dribbles_attempted",
    "dribbles_completed",
    "tackles",
    "interceptions",
    "clearances",
    "blocks",
    "recoveries",
    "duels_total",
    "duels_won",
    "aerial_duels_total",
    "aerial_duels_won",
    "penalties_saved",
    "rating",
]


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def stat_map(stats: list[dict[str, Any]] | None) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for stat in stats or []:
        name = stat.get("name")
        value = stat.get("value")
        if value is None:
            display_value = stat.get("displayValue")
            if isinstance(display_value, str):
                try:
                    value = float(display_value)
                except ValueError:
                    value = None
        if isinstance(name, str) and isinstance(value, (int, float)):
            result[name] = value
    return result


def parse_clock(display_value: str | None) -> tuple[int, int]:
    if not display_value:
        return 0, 0
    match = re.search(r"(\d+)'(?:\+(\d+)')?", display_value)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2) or 0)


def substitution_minute(item: dict[str, Any]) -> tuple[int | None, int]:
    for play in item.get("plays") or []:
        if play.get("substitution"):
            minute, stoppage = parse_clock((play.get("clock") or {}).get("displayValue"))
            return minute, stoppage
    return None, 0


def red_card_minute(item: dict[str, Any]) -> int | None:
    for play in item.get("plays") or []:
        if play.get("redCard"):
            minute, _ = parse_clock((play.get("clock") or {}).get("displayValue"))
            return minute
    return None


def minutes_played(item: dict[str, Any], stats: dict[str, int | float]) -> int:
    appeared = int(stats.get("appearances", 0)) > 0
    if not appeared:
        return 0
    minute, _ = substitution_minute(item)
    if item.get("starter"):
        if item.get("subbedOut") and minute is not None:
            return min(90, max(1, minute))
        red_minute = red_card_minute(item)
        return min(90, max(1, red_minute)) if red_minute else 90
    if item.get("subbedIn"):
        if minute is None:
            return 1
        return max(1, 90 - min(90, minute))
    return 1


def make_player(
    item: dict[str, Any],
    team_name: str,
    source_ref: str,
) -> dict[str, Any]:
    stats = stat_map(item.get("stats"))
    appeared = int(stats.get("appearances", 0)) > 0
    starter = bool(item.get("starter"))
    sub_minute, _ = substitution_minute(item)
    position = item.get("position") or {}
    position_name = position.get("displayName") or position.get("name") or ""
    position_abbreviation = position.get("abbreviation") or ""

    if starter:
        lineup_status = "starter"
    elif appeared:
        lineup_status = "substitute"
    else:
        lineup_status = "unused"

    player: dict[str, Any] = {
        "team_name": team_name,
        "player_name": (item.get("athlete") or {}).get("displayName", ""),
        "shirt_number": int(item["jersey"]) if str(item.get("jersey", "")).isdigit() else None,
        "position": position_name,
        "player_type": position_abbreviation,
        "lineup_status": lineup_status,
        "started": starter,
        "captain": False,
        "minutes_played": minutes_played(item, stats),
        "substituted_on_minute": (
            sub_minute if appeared and not starter and item.get("subbedIn") else None
        ),
        "substituted_off_minute": (
            sub_minute if starter and item.get("subbedOut") else None
        ),
        "saves": None,
        "goals_conceded": None,
        "source_ids": [source_ref],
        "notes": "ESPN 接口未显式提供队长标记；高级统计缺失项保留为 null。",
    }
    for field in NULL_PLAYER_FIELDS:
        player[field] = None
    for source_name, target_name in PLAYER_FIELD_MAP.items():
        value = stats.get(source_name)
        player[target_name] = int(value) if value is not None else None

    if position_abbreviation == "G" or "Goalkeeper" in position_name:
        saves = stats.get("saves")
        conceded = stats.get("goalsConceded")
        player["saves"] = int(saves) if saves is not None else None
        player["goals_conceded"] = int(conceded) if conceded is not None else None
    return player


def find_player_team(
    rosters: list[dict[str, Any]],
    player_name: str,
    team_names: dict[str, str],
) -> str | None:
    for roster in rosters:
        english_team = (roster.get("team") or {}).get("displayName")
        for item in roster.get("roster") or []:
            if (item.get("athlete") or {}).get("displayName") == player_name:
                return team_names.get(english_team)
    return None


def add_event(
    events: list[dict[str, Any]],
    *,
    team_name: str,
    player_name: str,
    related_player_name: str = "",
    event_type: str,
    minute: int,
    stoppage_minute: int = 0,
    outcome: str,
    source_ref: str,
    notes: str = "",
) -> None:
    events.append(
        {
            "event_ref": f"event_{len(events) + 1:03d}",
            "team_name": team_name,
            "player_name": player_name,
            "related_player_name": related_player_name,
            "event_type": event_type,
            "minute": minute,
            "stoppage_minute": stoppage_minute,
            "outcome": outcome,
            "xg": None,
            "source_ids": [source_ref],
            "notes": notes,
        }
    )


def generate_events(
    summary: dict[str, Any],
    team_names: dict[str, str],
    source_ref: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    rosters = summary.get("rosters") or []
    competition = (summary["header"]["competitions"] or [])[0]

    for detail in competition.get("details") or []:
        participants = detail.get("participants") or []
        if not participants:
            continue
        scorer = (participants[0].get("athlete") or {}).get("displayName", "")
        assist = (
            (participants[1].get("athlete") or {}).get("displayName", "")
            if len(participants) > 1
            else ""
        )
        minute, stoppage = parse_clock((detail.get("clock") or {}).get("displayValue"))
        if detail.get("ownGoal"):
            scorer_team = find_player_team(rosters, scorer, team_names)
            if scorer_team:
                add_event(
                    events,
                    team_name=scorer_team,
                    player_name=scorer,
                    event_type="own_goal",
                    minute=minute,
                    stoppage_minute=stoppage,
                    outcome="乌龙球",
                    source_ref=source_ref,
                    notes=f"进球记入 {team_names.get((detail.get('team') or {}).get('displayName'), '')}",
                )
            continue

        scoring_team = team_names[(detail.get("team") or {}).get("displayName")]
        add_event(
            events,
            team_name=scoring_team,
            player_name=scorer,
            related_player_name=assist,
            event_type="goal",
            minute=minute,
            stoppage_minute=stoppage,
            outcome="进球",
            source_ref=source_ref,
            notes="点球" if detail.get("penaltyKick") else "",
        )
        if assist:
            add_event(
                events,
                team_name=scoring_team,
                player_name=assist,
                related_player_name=scorer,
                event_type="assist",
                minute=minute,
                stoppage_minute=stoppage,
                outcome="助攻",
                source_ref=source_ref,
            )

    for roster in rosters:
        english_team = (roster.get("team") or {}).get("displayName")
        team_name = team_names[english_team]
        for item in roster.get("roster") or []:
            player_name = (item.get("athlete") or {}).get("displayName", "")
            for play in item.get("plays") or []:
                minute, stoppage = parse_clock((play.get("clock") or {}).get("displayValue"))
                if play.get("yellowCard"):
                    add_event(
                        events,
                        team_name=team_name,
                        player_name=player_name,
                        event_type="yellow_card",
                        minute=minute,
                        stoppage_minute=stoppage,
                        outcome="黄牌",
                        source_ref=source_ref,
                    )
                if play.get("redCard"):
                    add_event(
                        events,
                        team_name=team_name,
                        player_name=player_name,
                        event_type="red_card",
                        minute=minute,
                        stoppage_minute=stoppage,
                        outcome="红牌",
                        source_ref=source_ref,
                    )
            if item.get("starter") and item.get("subbedOut"):
                minute, stoppage = substitution_minute(item)
                replacement = item.get("subbedOutFor") or {}
                replacement_name = (replacement.get("athlete") or {}).get("displayName", "")
                if minute is not None and replacement_name:
                    add_event(
                        events,
                        team_name=team_name,
                        player_name=player_name,
                        related_player_name=replacement_name,
                        event_type="substitution_off",
                        minute=minute,
                        stoppage_minute=stoppage,
                        outcome="被换下",
                        source_ref=source_ref,
                    )
                    add_event(
                        events,
                        team_name=team_name,
                        player_name=replacement_name,
                        related_player_name=player_name,
                        event_type="substitution_on",
                        minute=minute,
                        stoppage_minute=stoppage,
                        outcome="替补登场",
                        source_ref=source_ref,
                    )
    return events


def team_statistics(summary: dict[str, Any], english_team: str) -> dict[str, Any]:
    for team in (summary.get("boxscore") or {}).get("teams") or []:
        if (team.get("team") or {}).get("displayName") == english_team:
            return stat_map(team.get("statistics"))
    return {}


def build_import(config: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    competition = (summary["header"]["competitions"] or [])[0]
    if not ((competition.get("status") or {}).get("type") or {}).get("completed"):
        raise ValueError(f"{config['match_id']} 尚未结束")

    competitors = {
        (item.get("team") or {}).get("displayName"): int(item.get("score", 0))
        for item in competition.get("competitors") or []
    }
    expected = {
        config["team_a_en"]: config["score_a"],
        config["team_b_en"]: config["score_b"],
    }
    if competitors != expected:
        raise ValueError(
            f"{config['match_id']} 比分不一致：数据源 {competitors}，数据库 {expected}"
        )

    source_ref = "espn_summary"
    team_names = {
        config["team_a_en"]: config["team_a"],
        config["team_b_en"]: config["team_b"],
    }
    players: list[dict[str, Any]] = []
    for roster in summary.get("rosters") or []:
        english_team = (roster.get("team") or {}).get("displayName")
        for item in roster.get("roster") or []:
            players.append(make_player(item, team_names[english_team], source_ref))

    stats_a = team_statistics(summary, config["team_a_en"])
    stats_b = team_statistics(summary, config["team_b_en"])
    details = competition.get("details") or []
    venue = ((summary.get("gameInfo") or {}).get("venue") or {}).get("fullName", "")
    events = generate_events(summary, team_names, source_ref)

    return {
        "schema_version": "1.0.0",
        "data_completeness": "full",
        "match": {
            "match_id": config["match_id"],
            "competition": "FIFA World Cup 2026",
            "match_date": config["match_date"],
            "stage": "Group stage",
            "venue": venue,
            "team_a": config["team_a"],
            "team_b": config["team_b"],
            "actual_score_a": config["score_a"],
            "actual_score_b": config["score_b"],
        },
        "sources": [
            {
                "source_ref": "fifa_scores",
                "source_title": "FIFA World Cup 2026 官方赛果与赛程",
                "source_url": (
                    "https://www.fifa.com/en/tournaments/mens/worldcup/"
                    "canadamexicousa2026/scores-fixtures"
                ),
                "source_type": "official_match_report",
                "summary": "用于核验正式赛程、完赛状态和最终比分。",
                "reliability": "high",
            },
            {
                "source_ref": source_ref,
                "source_title": "ESPN FIFA World Cup 比赛中心",
                "source_url": SUMMARY_URL.format(event_id=config["event_id"]),
                "source_type": "statistics_provider",
                "summary": "正式赛果、完整名单、首发替补、换人、进球助攻、纪律与基础统计。",
                "reliability": "high",
            }
        ],
        "team_stats": {
            "shots_a": int(stats_a["totalShots"]) if "totalShots" in stats_a else None,
            "shots_b": int(stats_b["totalShots"]) if "totalShots" in stats_b else None,
            "shots_on_target_a": (
                int(stats_a["shotsOnTarget"]) if "shotsOnTarget" in stats_a else None
            ),
            "shots_on_target_b": (
                int(stats_b["shotsOnTarget"]) if "shotsOnTarget" in stats_b else None
            ),
            "xg_a": None,
            "xg_b": None,
            "possession_a": stats_a.get("possessionPct"),
            "possession_b": stats_b.get("possessionPct"),
            "corners_a": int(stats_a["wonCorners"]) if "wonCorners" in stats_a else None,
            "corners_b": int(stats_b["wonCorners"]) if "wonCorners" in stats_b else None,
            "set_piece_goals": None,
            "penalty_goals": sum(1 for detail in details if detail.get("penaltyKick")),
            "own_goals": sum(1 for detail in details if detail.get("ownGoal")),
            "red_cards": sum(
                int(stats.get("redCards", 0)) for stats in (stats_a, stats_b)
            ),
            "goalkeeper_errors": None,
            "stoppage_time_goals": sum(
                1
                for detail in details
                if ((detail.get("addedClock") or {}).get("value") or 0) > 0
            ),
            "notes": (
                "ESPN 未稳定提供 xG、定位球进球与门将重大失误字段，"
                "相关未知值保留为 null。"
            ),
        },
        "players": players,
        "events": events,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for config in MATCHES:
        url = SUMMARY_URL.format(event_id=config["event_id"])
        summary = fetch_json(url)
        data = build_import(config, summary)
        output = OUTPUT_DIR / f"{config['match_id']}.json"
        output.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        active = sum(1 for player in data["players"] if player["minutes_played"] > 0)
        print(
            f"已生成 {output.name}: 球员{len(data['players'])}，"
            f"实际出场{active}，事件{len(data['events'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
