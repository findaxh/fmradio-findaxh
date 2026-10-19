#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电台区域/类别标签推导 + 名称归一化（纯标准库，便于测试）。
- tag_station: 根据名称/标签/州省推导 (区域, 类别列表)
- norm_name:   归一化电台名，用于去重（去掉 CNR-x/CRI/CCTV-x 前缀、空白、大小写）
"""
import re

PROVINCES = [
    "北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
    "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆", "香港", "澳门",
]

# 名称含这些关键字 -> 中央台（只保留强信号，避免“XX音乐之声”等地方台误判）
CENTRAL_NAME_KW = [
    "CNR", "CRI", "CCTV", "中央人民广播", "中国国际广播", "中央",
    "中国交通广播", "环球资讯", "轻松调频", "南海之声", "海峡飞虹",
    "大湾区之声", "经典音乐广播", "Hit FM", "HitFM",
    "Easy FM", "EasyFM", "NEWS Plus", "中国之声", "经济之声",
]

STATE_MAP = {
    "kwangtung": "广东", "guangdong": "广东", "canton": "广东",
    "peking": "北京", "beijing": "北京",
    "shanghai": "上海",
    "tianjin": "天津", "tiensin": "天津",
    "chongqing": "重庆", "chungking": "重庆",
    "hebei": "河北", "hopeh": "河北", "hopei": "河北",
    "shanxi": "山西", "shansi": "山西",
    "shaanxi": "陕西", "shensi": "陕西",
    "liaoning": "辽宁", "fengtien": "辽宁",
    "jilin": "吉林", "kirin": "吉林",
    "heilongjiang": "黑龙江", "heilungkiang": "黑龙江",
    "jiangsu": "江苏", "kiangsu": "江苏",
    "zhejiang": "浙江", "chekiang": "浙江",
    "anhui": "安徽", "anhwei": "安徽",
    "fujian": "福建", "fukien": "福建", "amoy": "福建",
    "jiangxi": "江西", "kiangsi": "江西",
    "shandong": "山东", "shantung": "山东",
    "henan": "河南", "honan": "河南",
    "hubei": "湖北", "hupeh": "湖北",
    "hunan": "湖南",
    "hainan": "海南",
    "sichuan": "四川", "szechwan": "四川", "szechuan": "四川",
    "guizhou": "贵州", "kweichow": "贵州",
    "yunnan": "云南",
    "gansu": "甘肃", "kansu": "甘肃",
    "qinghai": "青海", "tsinghai": "青海",
    "taiwan": "台湾", "formosa": "台湾",
    "inner mongolia": "内蒙古", "nei mongol": "内蒙古", "inner mongol": "内蒙古",
    "guangxi": "广西", "kwangsi": "广西",
    "tibet": "西藏", "xizang": "西藏",
    "ningxia": "宁夏", "ningsia": "宁夏",
    "xinjiang": "新疆", "sinkiang": "新疆",
    "hong kong": "香港", "hongkong": "香港",
    "macau": "澳门", "macao": "澳门",
}

NAME_CATS = [
    ("新闻", "新闻"), ("资讯", "新闻"), ("交通", "交通"), ("汽车", "交通"),
    ("音乐", "音乐"), ("经济", "财经"), ("财经", "财经"), ("房产", "财经"),
    ("体育", "体育"), ("文艺", "文艺"), ("戏曲", "戏曲"), ("都市", "都市"),
    ("乡村", "乡村"), ("生活", "生活"), ("健康", "健康"), ("教育", "教育"),
    ("少儿", "少儿"), ("亲子", "少儿"), ("旅游", "旅游"), ("故事", "故事"),
    ("评书", "评书"), ("综艺", "综艺"), ("国际", "国际"), ("外语", "外语"),
    ("英语", "外语"), ("老年", "老年"), ("青年", "青年"), ("美食", "生活"),
    ("天气", "生活"), ("应急", "应急"),
]

TAG_MAP = {
    "news": "新闻", "news talk": "新闻", "music": "音乐", "traffic": "交通",
    "talk": "综合", "sports": "体育", "culture": "文艺", "finance": "财经",
    "business": "财经", "economy": "财经", "education": "教育",
    "children": "少儿", "religious": "宗教", "public": "公共",
    "top 40": "流行", "pop": "流行", "rock": "摇滚", "jazz": "爵士",
    "classical": "古典", "oldies": "怀旧", "country": "乡村",
    "weather": "生活", "comedy": "喜剧", "documentary": "纪实",
    "variety": "综艺", "information": "综合", "general": "综合",
}


def tag_station(name, tags, state):
    """根据名称/标签/州省推导 (region, cats)。"""
    name = name or ""
    tags = (tags or "").lower()
    state = (state or "").strip().lower()

    region = None
    up = name.upper()
    for kw in CENTRAL_NAME_KW:
        if kw.upper() in up:
            region = "中央台"
            break
    if not region:
        for p in PROVINCES:
            if p in name:
                region = p
                break
    if not region and state:
        region = STATE_MAP.get(state)
    if not region:
        region = "其他"

    cats = []
    seen = set()
    for kw, cat in NAME_CATS:
        if kw in name and cat not in seen:
            cats.append(cat)
            seen.add(cat)
    for t in tags.split(","):
        c = TAG_MAP.get(t.strip())
        if c and c not in seen:
            cats.append(c)
            seen.add(c)
    if not cats:
        cats = ["综合"]

    return region, cats


# 名称前缀（CNR-x / CRI / CCTV-x 等），去重时剥离
_NAME_PREFIX_RE = re.compile(r"^(CNR|CRI|CCTV)[\s\-_]*\d*[\s\-_]*", re.I)


def norm_name(name):
    """归一化电台名用于去重：剥离 CNR-x/CRI/CCTV-x 前缀、去空白、转小写。
    使 'CNR-1 中国之声' 与 '中国之声' 归为同一台。"""
    n = (name or "").strip()
    n = _NAME_PREFIX_RE.sub("", n)
    n = re.sub(r"\s+", "", n)
    return n.lower()
