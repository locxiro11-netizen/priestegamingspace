#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genre.py — 资讯分类：3A 游戏 / 独立游戏 / 综合。

新条目由大模型在精选时直接打标；模型没给、或历史条目压根没这个字段时，
用这里的规则兜底推断，保证子页签任何时候都不会是空的。

取值（写进 content.json 的是短码，展示用中文标签）：
    '3a'    3A 游戏
    'indie' 独立游戏
    'other' 综合（行业动态、平台政策、硬件、玩家圈事件等）

单独成模块的原因：ai_curate.py（新条目）、backfill_genre.py（历史回填）
都要用同一套判定，散在两处必然不一致。
"""

# 3A / 大作信号：知名 IP、系列名，以及一眼就能认出的大厂大作
AAA_KEYWORDS = [
    # Rockstar / Take-Two
    "GTA", "侠盗猎车", "荒野大镖客", "Red Dead", "R星", "Rockstar",
    # 任天堂
    "塞尔达", "Zelda", "马力欧", "Mario", "宝可梦", "Pokemon", "Pokémon",
    "喷射战士", "斯普拉遁", "任天堂", "Nintendo", "Switch 2",
    # 索尼
    "战神", "God of War", "最后生还者", "The Last of Us", "神秘海域",
    "Uncharted", "地平线", "Horizon", "蜘蛛侠", "Spider-Man", "对马岛",
    "PlayStation", "PS5", "PS6", "顽皮狗", "Naughty Dog", "圣莫妮卡",
    # 微软 / Bethesda
    "光晕", "Halo", "极限竞速", "Forza", "星空", "Starfield", "辐射",
    "Fallout", "上古卷轴", "Elder Scrolls", "Xbox", "Bethesda", "毁灭战士",
    "Doom", "使命召唤", "Call of Duty", "动视", "Activision", "暴雪",
    "Blizzard", "魔兽世界", "World of Warcraft", "守望先锋", "Overwatch",
    "暗黑破坏神", "Diablo", "炉石", "Hearthstone", "星际争霸", "StarCraft",
    # FromSoftware / 日系大作
    "艾尔登法环", "Elden Ring", "黑暗之魂", "Dark Souls", "只狼", "Sekiro",
    "血源", "Bloodborne", "装甲核心", "Armored Core", "黑神话", "Black Myth",
    "最终幻想", "Final Fantasy", "勇者斗恶龙", "Dragon Quest", "怪物猎人",
    "Monster Hunter", "生化危机", "Resident Evil", "鬼泣", "Devil May Cry",
    "合金装备", "Metal Gear", "死亡搁浅", "Death Stranding", "寂静岭",
    "Silent Hill", "如龙", "Yakuza", "卡普空", "Capcom", "科乐美", "Konami",
    "史克威尔", "Square Enix", "万代", "Bandai", "世嘉", "Sega",
    # 育碧 / EA / 欧美大厂
    "刺客信条", "Assassin's Creed", "孤岛惊魂", "Far Cry", "看门狗",
    "Watch Dogs", "彩虹六号", "Rainbow Six", "全境封锁", "Division",
    "舞力全开", "育碧", "Ubisoft", "FIFA", "EA Sports FC", "NBA 2K",
    "Madden", "极品飞车", "Need for Speed", "模拟人生", "The Sims",
    "战地", "Battlefield", "F1", "EA", "艺电",
    # 其他常见大作 / 高预算作品
    "霍格沃茨之遗", "Hogwarts", "博德之门", "Baldur's Gate", "赛博朋克",
    "Cyberpunk", "巫师", "Witcher", "CD Projekt", "CDPR", "龙腾世纪",
    "Dragon Age", "质量效应", "Mass Effect", "文明", "Civilization",
    "帝国时代", "Age of Empires", "微软飞行模拟", "Flight Simulator",
    "星际公民", "Star Citizen", "方舟", "ARK", "幻兽帕鲁", "Palworld",
    # 国内大厂重点项目
    "原神", "Genshin", "崩坏", "Honkai", "绝区零", "Zenless", "鸣潮",
    "明日方舟", "终末地", "Endfield", "三角洲行动", "Delta Force",
    "燕云十六声", "永劫无间", "黑神话：悟空", "王者荣耀", "和平精英",
    "英雄联盟", "League of Legends", "无畏契约", "Valorant", "Dota",
    "CS2", "CS:GO", "反恐精英", "Apex", "绝地求生", "PUBG",
]

# 独立游戏信号
INDIE_KEYWORDS = [
    "独立游戏", "独立游戏节", "独游", "独立开发", "独立工作室", "独立制作",
    "一人开发", "两人团队", "小团队", "个人开发", "像素风", "像素游戏",
    "indie", "Indie", "INDIE", "Indie Game", "indie game", "itch.io",
    "itchio", "众筹", "抢先体验", "Early Access", "独立游戏大奖",
    "IGF", "IndieCade", "肉鸽", "Roguelike", "Roguelite", "类幸存者",
]

# 这些来源本身就是独立游戏阵地
INDIE_SOURCES = {"indienova"}

GENRE_LABELS = {"3a": "3A游戏", "indie": "独立游戏", "other": "综合"}
VALID_GENRES = ("3a", "indie", "other")


def _haystack(item):
    """把一条资讯里能用来判断分类的文字拼在一起。"""
    parts = [
        item.get("title") or "",
        item.get("desc") or "",
        item.get("raw_desc") or "",
        item.get("game") or "",
        " ".join(item.get("tags") or []),
    ]
    return " ".join(p for p in parts if p)


def normalize_genre(value):
    """把模型输出的各种写法收敛到三个取值，认不出来返回 None。

    模型常给 '3A' / 'AAA' / '独立' / '独立游戏' / '其他' 这类中文或大小写变体，
    直接存进 content.json 会让前端过滤永远匹配不上。
    """
    if not value:
        return None
    v = str(value).strip().lower()
    mapping = {
        "3a": "3a", "aaa": "3a", "3a游戏": "3a", "aaa游戏": "3a", "大作": "3a",
        "3a大作": "3a", "商业大作": "3a", "主机大作": "3a",
        "indie": "indie", "独立": "indie", "独立游戏": "indie", "独游": "indie",
        "indiegame": "indie", "独立游戏资讯": "indie",
        "other": "other", "其他": "other", "综合": "other", "综合资讯": "other",
        "none": "other", "null": "other",
    }
    return mapping.get(v)


def infer_genre(item):
    """规则兜底推断分类。判不出来就归 'other'。

    顺序有讲究：先独立后 3A。像《幻兽帕鲁》这种既是独立团队又是现象级爆款，
    标题里只要出现「独立游戏」就按独立算，符合玩家的心智。
    """
    text = _haystack(item)
    source = (item.get("source") or "").strip()

    # 顺序有讲究：关键词比来源可靠。
    # indienova 也会报道《GTA6》这种大作，若让来源说了算，
    # 3A 动态会被错划到独立游戏里——来源只作为「什么都没命中」时的弱信号。
    for kw in INDIE_KEYWORDS:
        if kw in text:
            return "indie"
    for kw in AAA_KEYWORDS:
        if kw in text:
            return "3a"
    if source in INDIE_SOURCES:
        return "indie"
    return "other"


def resolve_genre(item, model_value=None):
    """优先用模型的判断，模型没给或给得不像样再退回规则推断。"""
    g = normalize_genre(model_value)
    if g in VALID_GENRES:
        return g
    return infer_genre(item)


if __name__ == "__main__":
    # 自检：喂几条典型标题，看看分类对不对
    samples = [
        {"title": "《GTA6》预告片引爆全网", "source": "游民星空"},
        {"title": "这款一人开发的像素游戏卖爆了", "source": "indienova"},
        {"title": "App Store 收入十年首次下滑", "source": "GameLook"},
        {"title": "《黑神话：悟空》新预告公布", "source": "3DM"},
        {"title": "本周 Steam 值得关注的游戏", "source": "indienova"},
        {"title": "索尼支付8000万美元和解金", "source": "IGN"},
    ]
    for s in samples:
        print(f"{infer_genre(s):<6} [{s['source']}] {s['title']}")
