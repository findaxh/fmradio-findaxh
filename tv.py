#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电视频道 + 视频节目聚合（纯标准库 + requests）。

数据源：
- TV 频道：多个公开 m3u 列表（vbskycn 6 小时自动拨测 / peterhchina 每日更新等），
  同一频道聚合多个备用源，播放失败自动切换
- 视频节目：央视《新闻联播》(tv.cctv.com/lm/xwlb) 与 BTV《北京新闻》(btime.com)

与 app.py 的网络策略保持一致：默认纯直连，不使用任何系统/环境代理。
"""
import json
import os
import re
import threading
import time

import requests

UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 默认 TV 源（按优先级排列，可用环境变量 TV_SOURCES 覆盖，逗号分隔）
#   1. zilong7728/Collect-IPTV：每 4 小时自动更新，自带可用性检测 + 低延迟优选
#      （best_sorted.m3u，447 个频道全带台标；raw 不通时自动走 gh-proxy / jsDelivr 镜像）
#   2. vbskycn/iptv：后台每 6 小时自动测速拨测，剔除死链，带台标 + EPG
#   3. peterhchina/iptv：每日更新，央视 + 卫视 + 地方
#   4. peterhchina 央视频道专表
#   5. iptv-org 全球公开列表（补充海外台）
_CI = "https://raw.githubusercontent.com/zilong7728/Collect-IPTV/refs/heads/main/best_sorted.m3u"
TV_SOURCES = [
    u.strip()
    for u in os.environ.get(
        "TV_SOURCES",
        ",".join(
            [
                _CI,
                "https://gh-proxy.com/https://raw.githubusercontent.com/zilong7728/Collect-IPTV/refs/heads/main/best_sorted.m3u",
                "https://live.zbds.top/tv/iptv4.m3u",
                "https://peterhchina.github.io/iptv/CNTV-V4.m3u",
                "https://peterhchina.github.io/iptv/CCTV-V4.m3u",
                "https://iptv-org.github.io/iptv/countries/cn.m3u",
            ]
        ),
    ).split(",")
    if u.strip()
]

MAX_URLS_PER_CHANNEL = int(os.environ.get("TV_MAX_URLS", "6"))
TV_TIMEOUT = float(os.environ.get("TV_TIMEOUT", "15"))
TV_CACHE_TTL = float(os.environ.get("TV_CACHE_TTL", "1800"))

XWLB_URL = "https://tv.cctv.com/lm/xwlb/index.shtml"
XWLB_DAY_URL = "https://tv.cctv.com/lm/xwlb/day/{}.shtml"
XWLB_VIDEO_API = "https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do"
BJXW_URL = "https://www.btime.com/btv/btvxw_bjxm"
BJXW_INFOFLOW = "https://pc.api.btime.com/btimeweb/infoFlow"
BJXW_TRANS = "https://app.api.btime.com/trans"
BJXW_PLAY = "https://app.api.btime.com/video/play"
XWLB_DAYS = int(os.environ.get("XWLB_DAYS", "30"))   # 侧栏展示的往期天数

# ---- 缓存 ----
_CACHE = {}
_LOCK = threading.Lock()

# 源存活探测缓存：url -> (ts, ok, latency_ms)
_PROBE_CACHE = {}
# 串行化真正的探测：避免多人同时打开页面时线程数按用户数翻倍
_PROBE_RUNNING = threading.Lock()
_PROBE_TTL = float(os.environ.get("TV_PROBE_TTL", "600"))
_PROBE_WORKERS = int(os.environ.get("TV_PROBE_WORKERS", "48"))
_PROBE_TIMEOUT = float(os.environ.get("TV_PROBE_TIMEOUT", "4"))
# 拉取全部 TV 源的总时限（秒）：全部源都不可达时不让 SSE 无限挂住
TV_SOURCES_DEADLINE = float(os.environ.get("TV_SOURCES_DEADLINE", "45"))


def _cache_get(key, ttl):
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        return None


def _cache_put(key, val):
    with _LOCK:
        _CACHE[key] = (time.time(), val)


def probe_url(url, timeout=None):
    """探测一个流地址是否存活，返回 (ok, latency_ms)。"""
    timeout = timeout or _PROBE_TIMEOUT
    sess = _session()
    t0 = time.time()
    try:
        r = sess.get(
            url,
            headers={"User-Agent": UA_BROWSER, "Accept": "*/*"},
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        )
        try:
            next(r.iter_content(512))
        except Exception:
            pass
        r.close()
        ok = r.status_code < 400
    except Exception:
        ok = False
    return ok, int((time.time() - t0) * 1000)


def probe_channels(channels, refresh=False):
    """并发探测频道各备用源，返回 {url: {"ok":..,"ms":..}}。"""
    gen = probe_channels_iter(channels, refresh=refresh)
    live = None
    try:
        while True:
            next(gen)
    except StopIteration as e:
        live = e.value
    return live or {}


def probe_channels_iter(channels, refresh=False):
    """生成器版探测：yield (done, total) 汇报进度，return 存活映射。

    只探测每个频道的全部备用地址（上限 MAX_URLS_PER_CHANNEL），结果按 _PROBE_TTL 缓存。
    用 _PROBE_RUNNING 串行化真正的探测：多人同时打开页面时，后来者会等前一轮跑完，
    然后直接命中缓存秒出，不会把线程数放大成「用户数 × 48」。
    """
    urls = []
    for c in channels:
        for u in (c.get("urls") or [])[:MAX_URLS_PER_CHANNEL]:
            urls.append(u)
    urls = list(dict.fromkeys(urls))
    total = len(urls)
    urlset = set(urls)

    def _fresh():
        now = time.time()
        with _LOCK:
            return {
                u: {"ok": v[1], "ms": v[2]}
                for u, v in _PROBE_CACHE.items()
                if u in urlset and now - v[0] <= _PROBE_TTL
            }

    cached = _fresh()
    todo = [u for u in urls if refresh or u not in cached]

    if not todo:
        yield (total, total)
        return cached

    done = 0
    step = max(1, len(todo) // 40)          # 约汇报 40 次进度
    with _PROBE_RUNNING:
        # 拿到锁后可能已有别的请求跑完一轮，重新读缓存，避免重复探测
        if not refresh:
            cached = _fresh()
            todo = [u for u in urls if u not in cached]
            if not todo:
                yield (total, total)
                return cached
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=_PROBE_WORKERS) as ex:
                futs = {ex.submit(probe_url, u): u for u in todo}
                for f in as_completed(futs):
                    u = futs[f]
                    try:
                        ok, ms = f.result()
                    except Exception:
                        ok, ms = False, 0
                    cached[u] = {"ok": ok, "ms": ms}
                    with _LOCK:
                        _PROBE_CACHE[u] = (time.time(), ok, ms)
                    done += 1
                    if done % step == 0 or done == len(todo):
                        yield (done, len(todo))
        except Exception:
            for u in todo:
                ok, ms = probe_url(u)
                cached[u] = {"ok": ok, "ms": ms}
                with _LOCK:
                    _PROBE_CACHE[u] = (time.time(), ok, ms)
                done += 1
                if done % step == 0 or done == len(todo):
                    yield (done, len(todo))
    return cached


# ---- 网络（默认纯直连，忽略系统/环境代理） ----
# 复用一个 Session：requests.Session 内部的 urllib3 连接池是线程安全的，
# 复用后能避免「探测 2000+ 个地址就新建 2000+ 个连接」的性能灾难。
_SHARED_SESSION = None
_SHARED_LOCK = threading.Lock()


def _session():
    global _SHARED_SESSION
    s = _SHARED_SESSION
    if s is None:
        with _SHARED_LOCK:
            if _SHARED_SESSION is None:
                s = requests.Session()
                s.trust_env = False          # 忽略环境变量与 Windows 系统代理
                _SHARED_SESSION = s
            else:
                s = _SHARED_SESSION
    return s


def _detect_encoding(resp):
    """优先用响应头 charset，其次 HTML meta，最后 utf-8。

    requests 对没有 charset 头的 text/* 会默认按 ISO-8859-1 解码，
    央视/部分站点正是这种情况，直接 r.text 会得到乱码。
    """
    ctype = resp.headers.get("Content-Type") or ""
    m = re.search(r"charset=([\w\-]+)", ctype, re.I)
    if m:
        return m.group(1)
    try:
        head = resp.content[:4096].decode("ascii", "ignore")
    except Exception:
        head = ""
    m = re.search(r'charset=["\']?([\w\-]+)', head, re.I)
    if m:
        return m.group(1)
    return "utf-8"


def http_get(url, timeout=None, referer=None, as_json=False, retries=2):
    """GET 一个 URL；返回 (resp, None) 或 (None, 错误串)。直连，不走任何代理。

    retries：公开直播列表偶发断连/限流，默认重试 1 次。
    """
    headers = {"User-Agent": UA_BROWSER, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    r = None
    last = None
    for attempt in range(max(1, retries)):
        try:
            r = _session().get(url, headers=headers, timeout=timeout or TV_TIMEOUT)
            break
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            r = None
            if attempt + 1 < retries:
                time.sleep(0.8)
    if r is None:
        return None, last or "request failed"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    # 强制按真实编码解码，避免无 charset 的页面出现乱码
    try:
        r.encoding = _detect_encoding(r)
    except Exception:
        r.encoding = "utf-8"
    if as_json:
        try:
            return r.json(), None
        except Exception as e:
            return None, f"bad json: {e}"
    return r, None


# ---------------------------------------------------------------------------
# m3u 解析
# ---------------------------------------------------------------------------
_EXTINF_RE = re.compile(r"#EXTINF:(.*)")
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _split_extinf(line):
    """拆分 `#EXTINF:<时长> <属性>,<显示名>` → (属性串, 显示名)。

    不能用简单的 `[^,]*` 切分：属性值里可能含逗号（如
    tvg-logo="http://x/a,b.png"）。这里按「引号外的第一个逗号」切，
    时长字段（可能为空/带空格/小数/负数）直接跳过。
    """
    body = line[len("#EXTINF:"):]
    i = 0
    while i < len(body) and (body[i].isdigit() or body[i] in "-.+ "):
        i += 1
    rest = body[i:]
    inq = False
    for j, ch in enumerate(rest):
        if ch == '"':
            inq = not inq
        elif ch == "," and not inq:
            return rest[:j], rest[j + 1:].strip()
    return rest, ""


def parse_m3u(text):
    """解析 M3U/M3U8 播放列表 → [{name,url,logo,group}]

    兼容 #EXTINF:-1 / #EXTINF:0 / #EXTINF:-1.5 / #EXTINF: 以及带空格的各种写法。
    """
    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            attrs = {}
            name = ""
            m = _EXTINF_RE.search(line)
            if m:
                attr_str, name = _split_extinf(line)
                attrs = dict(_ATTR_RE.findall(attr_str))
            url = ""
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt and not nxt.startswith("#"):
                    url = nxt
                    break
                j += 1
            if url.startswith("http"):
                out.append(
                    {
                        "name": name,
                        "url": url,
                        "logo": attrs.get("tvg-logo", ""),
                        "group": (attrs.get("group-title", "") or "").strip(),
                    }
                )
            i = j
        i += 1
    return out


# 常见央视频道中文名
_CCTV_NAMES = {
    "cctv-1": "CCTV-1 综合",
    "cctv-2": "CCTV-2 财经",
    "cctv-3": "CCTV-3 综艺",
    "cctv-4": "CCTV-4 中文国际",
    "cctv-5": "CCTV-5 体育",
    "cctv-5+": "CCTV-5+ 体育赛事",
    "cctv-6": "CCTV-6 电影",
    "cctv-7": "CCTV-7 国防军事",
    "cctv-8": "CCTV-8 电视剧",
    "cctv-9": "CCTV-9 纪录",
    "cctv-10": "CCTV-10 科教",
    "cctv-11": "CCTV-11 戏曲",
    "cctv-12": "CCTV-12 社会与法",
    "cctv-13": "CCTV-13 新闻",
    "cctv-14": "CCTV-14 少儿",
    "cctv-15": "CCTV-15 音乐",
    "cctv-16": "CCTV-16 奥林匹克",
    "cctv-17": "CCTV-17 农业农村",
    "cctv-4k": "CCTV-4K 超高清",
    "cctv-8k": "CCTV-8K 超高清",
}

_GROUP_CN = {
    "news": "新闻",
    "general": "综合",
    "movies": "电影",
    "series": "电视剧",
    "sports": "体育",
    "music": "音乐",
    "kids": "少儿",
    "animation": "动画",
    "documentary": "纪录片",
    "education": "科教",
    "science": "科学",
    "culture": "文化",
    "entertainment": "综艺",
    "lifestyle": "生活",
    "travel": "旅游",
    "business": "财经",
    "family": "家庭",
    "outdoor": "户外",
    "weather": "天气",
    "legislative": "政务",
    "religious": "宗教",
    "shop": "购物",
    "health": "健康",
    "comedy": "喜剧",
    "classic": "经典",
    "undefined": "其他",
}

# 国内源常用的中文分组，直接采用
_CN_GROUPS = {
    "央视频道", "卫视频道", "地方频道", "体育频道", "电影频道", "纪录频道",
    "音乐频道", "儿童频道", "数字频道", "春晚频道", "解说频道", "直播中国",
    "付费频道", "综艺频道", "新闻频道", "影视频道", "科教频道", "财经频道",
    "生活频道", "旅游频道", "戏曲频道", "购物频道", "4K频道", "8K频道",
}
_GROUP_SKIP = {"更新时间", "undefined", "general;travel"}

_NAME_KW = [
    (r"cctv|cgtn", "央视"),
    (r"卫视", "卫视"),
    (r"news|新闻", "新闻"),
    (r"sport|体育|football|basketball|足球|篮球", "体育"),
    (r"movie|film|cinema|theater|theatre|影视", "影视"),
    (r"kids|children|少儿|动画", "少儿"),
    (r"music|音乐", "音乐"),
    (r"documentary|纪录|人文", "纪录片"),
    (r"edu|科教|science|科学", "科教"),
]


def _slug(name):
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def tv_categories(name, group):
    """由频道名与 m3u 分组推导中文分类标签。"""
    cats = []
    g = (group or "").strip()
    if g in _GROUP_SKIP:
        g = ""
    if g:
        if g in _CN_GROUPS:
            cats.append(g)
        else:
            for part in re.split(r"[;,]", g):
                cn = _GROUP_CN.get(part.strip().lower())
                if cn and cn not in cats:
                    cats.append(cn)
    s = _slug(name)
    for pat, cn in _NAME_KW:
        if re.search(pat, s) and cn not in cats:
            cats.append(cn)
    if not cats:
        cats = ["综合"]
    return cats


def _norm_tv_name(name):
    """把不同来源的同一频道名归一化，用于跨源合并。

    CCTV1 / CCTV-1 / CCTV-1 综合 / CCTV-1 HD (1080p) -> CCTV-1
    湖南卫视 / 湖南卫视HD / 东方卫视4K -> 湖南卫视 / 东方卫视
    """
    n = (name or "").strip().upper()
    n = re.sub(r"[\[（(][^\]）)]*[\]）)]", "", n)      # (1080p) [Geo-blocked]
    n = re.sub(r"[\s\-_\.·]+", "", n)                 # CCTV - 1 -> CCTV1
    m = re.match(r"^CCTV\+?(\d+[K\+]?)?", n)          # 央视：只取频道号
    if m:
        num = m.group(1) or ""
        return "CCTV-" + num if num else "CCTV"
    m = re.match(r"^(CGTN[A-Z]*)", n)                    # CGTN 国际台
    if m:
        return m.group(1)
    n = re.sub(r"(?i)(HD|FHD|UHD|SD|4K|8K|1080P|720P|540P|576I)", "", n)
    n = re.sub(r"(高清|超清|标清|蓝光|频道|直播|版)", "", n)
    return n



def _channel_key(name):
    """先做中英文名归一，再做名称归一。"""
    return _norm_tv_name(tv_display_name(name))


def tv_display_name(name):
    """把 CCTV-x 之类的英文名映射为中文名，未命中则原样返回。"""
    s = _slug(name)
    # CCTV1 / CCTV-1 / CCTV+ 1 / CCTV-4K / CCTV-5+ 都归一成 CCTV-x
    m = re.match(r"cctv[\s\-]*\+?\s*(\d+\s*[k\+]?)?", s)
    if m:
        num = re.sub(r"\s+", "", m.group(1) or "")
        if num:
            key = "cctv-" + num.lower()
            if key in _CCTV_NAMES:
                return _CCTV_NAMES[key]
            return "CCTV-" + num
    if s.startswith("cetv"):
        return name
    if "beijing satellite tv" in s:
        return "北京卫视"
    if "anhui tv" in s:
        return "安徽卫视"
    if "dongfang tv" in s or "dragon tv" in s:
        return "东方卫视"
    if "zhejiang tv" in s:
        return "浙江卫视"
    if "hunan tv" in s:
        return "湖南卫视"
    if "jiangsu tv" in s:
        return "江苏卫视"
    if "shandong tv" in s:
        return "山东卫视"
    if "guangdong tv" in s:
        return "广东卫视"
    if "shenzhen tv" in s:
        return "深圳卫视"
    if "tianjin tv" in s:
        return "天津卫视"
    if "chongqing tv" in s:
        return "重庆卫视"
    if "liaoning tv" in s:
        return "辽宁卫视"
    if "heilongjiang tv" in s:
        return "黑龙江卫视"
    if "hubei tv" in s:
        return "湖北卫视"
    if "sichuan tv" in s:
        return "四川卫视"
    if "hebei tv" in s:
        return "河北卫视"
    if "henan tv" in s:
        return "河南卫视"
    if "fujian tv" in s:
        return "东南卫视"
    if "guangxi tv" in s:
        return "广西卫视"
    if "yunnan tv" in s:
        return "云南卫视"
    if "guizhou tv" in s:
        return "贵州卫视"
    if "shanxi tv" in s:
        return "山西卫视"
    if "shaanxi tv" in s:
        return "陕西卫视"
    if "gansu tv" in s:
        return "甘肃卫视"
    if "ningxia tv" in s:
        return "宁夏卫视"
    if "qinghai tv" in s:
        return "青海卫视"
    if "xinjiang tv" in s:
        return "新疆卫视"
    if "xizang tv" in s or "tibet" in s:
        return "西藏卫视"
    if "inner mongolia tv" in s:
        return "内蒙古卫视"
    if "jilin tv" in s:
        return "吉林卫视"
    if "jiangxi tv" in s:
        return "江西卫视"
    if "hainan tv" in s:
        return "海南卫视"
    return name


def _clean_channel(name):
    """去掉 (1080p) / [Geo-blocked] 之类的后缀噪音。"""
    n = re.sub(r"\s*[\(\[][^)\]]*[\)\]]\s*$", "", name or "").strip()
    return n or (name or "").strip()


def _natkey(s):
    """自然排序键：CCTV-2 排在 CCTV-10 前面。"""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s or "")]


def _snapshot(payload):
    """把缓存里的 payload 复制一份再返回。

    get_channels 的调用方（探测逻辑）会往 channel 字典里写 live/best_url/latency_ms，
    如果直接返回缓存对象，这些字段会永久污染缓存，之后不带 probe 的请求
    （/api/tv/channels）就会拿到上一次探测的过期结果。
    """
    return {
        **payload,
        "channels": [dict(c) for c in payload["channels"]],
    }


def get_channels(force=False, probe=False, refresh=False):
    """聚合所有 TV 源 → {ok, count, channels, sources, errors}

    同一频道在不同源里会聚合到一起，urls 按源优先级排列（备用源），
    播放端按顺序自动切换，避免单源失效就看不了。
    probe=True 时附带每个源的存活探测结果；结果按频道名称自然排序。
    """
    key = "tv:channels"
    payload = None if force else _cache_get(key, TV_CACHE_TTL)

    if payload is None:
        merged = {}     # key -> channel dict
        order = []      # 保持首次出现顺序
        errors = []
        deadline = time.time() + TV_SOURCES_DEADLINE
        for si, src in enumerate(TV_SOURCES):
            # 总时限保护：至少试第一个源，之后的源超预算就跳过
            if si > 0 and time.time() > deadline:
                errors.append(f"{src} → 已超过总时限 {TV_SOURCES_DEADLINE}s，跳过")
                continue
            resp, err = http_get(src)
            if err:
                errors.append(f"{src} → {err}")
                continue
            for ch in parse_m3u(resp.text):
                name = _clean_channel(ch["name"])
                if not name or not ch["url"]:
                    continue
                disp = tv_display_name(name)
                k = _channel_key(name)
                if not k:
                    continue
                if k not in merged:
                    merged[k] = {
                        "name": disp,
                        "raw_name": name,
                        "logo": ch["logo"],
                        "cats": tv_categories(name, ch["group"]),
                        "urls": [],
                    }
                    order.append(k)
                c = merged[k]
                if ch["url"] not in c["urls"]:
                    c["urls"].append(ch["url"])
                if not c["logo"] and ch["logo"]:
                    c["logo"] = ch["logo"]

        channels = []
        for k in order:
            c = merged[k]
            urls = c["urls"][:MAX_URLS_PER_CHANNEL]
            channels.append(
                {
                    "name": c["name"],
                    "raw_name": c["raw_name"],
                    "logo": c["logo"],
                    "cats": c["cats"],
                    "url": urls[0],                       # 主源
                    "urls": urls,                         # 全部备用源（含主源）
                    "backups": len(urls) - 1,
                    "type": "hls"
                    if urls[0].lower().split("?")[0].endswith(".m3u8")
                    else "video",
                }
            )

        # 按频道名自然排序（CCTV-2 在 CCTV-10 前）
        channels.sort(key=lambda c: _natkey(c["name"]))
        payload = {
            "ok": bool(channels),
            "count": len(channels),
            "channels": channels,
            "sources": TV_SOURCES,
            "errors": errors,
        }
        _cache_put(key, payload)

    # 返回快照，避免调用方写字段污染缓存
    result = _snapshot(payload)

    if probe:
        live = probe_channels(result["channels"], refresh=refresh)
        for c in result["channels"]:
            best = None
            for u in (c.get("urls") or [])[:MAX_URLS_PER_CHANNEL]:
                st = live.get(u)
                if not st:
                    continue
                if st["ok"] and (best is None or st["ms"] < best[1]):
                    best = (u, st["ms"])
            c["live"] = bool(best)
            c["best_url"] = best[0] if best else c["url"]
            c["latency_ms"] = best[1] if best else None
        result["probed"] = True
    return result



# ---------------------------------------------------------------------------
# 《新闻联播》 tv.cctv.com/lm/xwlb
# ---------------------------------------------------------------------------
def _parse_xwlb(html, date_hint=""):
    """解析《新闻联播》某一天的节目列表（首页当日 + day/YYYYMMDD 往期通用）。"""
    items = []
    m = re.search(r'rilititle"><p>([\d\-]+)</p>', html)
    page_date = m.group(1) if m else date_hint
    block = html
    b = re.search(r'id="content"[^>]*>(.*?)</ul>', html, re.S)
    if b:
        block = b.group(1)
    for li in re.findall(r"<li>(.*?)</li>", block, re.S):
        um = re.search(r'href="(https://tv\.cctv\.com/[^"]+)"', li)
        im = re.search(r'<img src="(//[^"]+)"', li)
        tm = re.search(r'<i class="sql\d+">([^<]*)</i>([^<]+)</a>', li)
        dm = re.search(r"<span>(\d{1,2}:\d{2}:\d{2})</span>", li)
        if not um:
            continue
        title = (tm.group(2).strip() if tm else "") or um.group(1)
        cover = ("https:" + im.group(1)) if im else ""
        date = page_date
        d2 = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", um.group(1))
        if d2:
            date = f"{d2.group(1)}-{d2.group(2)}-{d2.group(3)}"
        items.append(
            {
                "title": title,
                "cover": cover,
                "url": um.group(1),
                "tag": (tm.group(1).strip() if tm else ""),
                "date": date,
                "duration": dm.group(1) if dm else "",
                "source": "新闻联播",
                "playable": True,
            }
        )
    return items


def _recent_dates(n):
    """最近 n 天（含今天）的日期串，倒序。"""
    import datetime as _dt

    today = _dt.date.today()
    return [(today - _dt.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def get_xwlb(force=False, date=None):
    """《新闻联播》：date=YYYY-MM-DD 取往期，默认最新一期。"""
    if date:
        return _get_xwlb_for(date, force)
    key = "tv:prog:xwlb:latest"
    if not force:
        hit = _cache_get(key, TV_CACHE_TTL)
        if hit is not None:
            return hit
    resp, err = http_get(XWLB_URL, referer=XWLB_URL)
    if err:
        return {"ok": False, "error": f"新闻联播页面获取失败：{err}"}
    items = _parse_xwlb(resp.text)
    if not items:
        return {"ok": False, "error": "未解析到新闻联播节目（页面结构可能变化）"}
    # 首页不返回时长，若缺失则用当日往期页补齐
    if not items[0].get("duration"):
        day = items[0].get("date")
        if day:
            dresp, derr = http_get(XWLB_DAY_URL.format(day.replace("-", "")), referer=XWLB_URL)
            if not derr:
                dur = {it["url"]: it.get("duration", "") for it in _parse_xwlb(dresp.text)}
                for it in items:
                    if dur.get(it["url"]):
                        it["duration"] = dur[it["url"]]
    payload = {
        "ok": True,
        "source": "新闻联播",
        "page": XWLB_URL,
        "date": items[0].get("date"),
        "count": len(items),
        "items": items,
        "dates": _recent_dates(XWLB_DAYS),
    }
    _cache_put(key, payload)
    return payload


def _get_xwlb_for(date, force=False):
    key = "tv:prog:xwlb:" + date
    if not force:
        hit = _cache_get(key, TV_CACHE_TTL)
        if hit is not None:
            return hit
    url = XWLB_DAY_URL.format(date.replace("-", ""))
    resp, err = http_get(url, referer=XWLB_URL)
    if err:
        return {"ok": False, "error": f"{date} 页面获取失败：{err}", "date": date}
    items = _parse_xwlb(resp.text, date_hint=date)
    if not items:
        return {
            "ok": False,
            "error": f"{date} 未解析到节目（可能当日无节目或页面结构变化）",
            "date": date,
        }
    payload = {
        "ok": True,
        "source": "新闻联播",
        "page": XWLB_URL,
        "date": items[0].get("date") or date,
        "count": len(items),
        "items": items,
        "dates": _recent_dates(XWLB_DAYS),
    }
    _cache_put(key, payload)
    return payload


def get_xwlb_dates():
    """侧栏用的往期日期列表。"""
    return {"ok": True, "dates": _recent_dates(XWLB_DAYS)}


# ---------------------------------------------------------------------------
# 《北京新闻》 btime.com
# ---------------------------------------------------------------------------
_LISTID_RE = re.compile(r'"listId":"(btv_[0-9a-f]+_s0_(\d{4})_(\d{2}))"')


def _parse_bjxw_listid(html):
    best = None
    for m in _LISTID_RE.finditer(html):
        lid, y, mo = m.group(1), int(m.group(2)), int(m.group(3))
        if best is None or (y, mo) > best[0]:
            best = ((y, mo), lid)
    return best[1] if best else None


def _parse_bjxw(data):
    items = []
    for it in (data or {}).get("data", {}).get("list", []):
        d = it.get("data") or {}
        title = (d.get("title") or "").strip()
        url = it.get("url") or it.get("open_url") or ""
        gid = it.get("gid") or ""
        if not title or not url:
            continue
        covers = d.get("covers") or []
        items.append(
            {
                "title": title,
                "cover": covers[0] if covers else "",
                "url": url,
                "gid": gid,
                "tag": "完整版",
                "date": d.get("pdate_ymd", ""),
                "duration": d.get("duration", ""),
                "source": "北京新闻",
                "playable": True,
            }
        )
    return items


def get_bjxw(force=False):
    key = "tv:prog:bjxw"
    if not force:
        hit = _cache_get(key, TV_CACHE_TTL)
        if hit is not None:
            return hit
    resp, err = http_get(BJXW_URL, referer="https://www.btime.com/")
    if err:
        return {"ok": False, "error": f"北京新闻页面获取失败：{err}"}
    list_id = _parse_bjxw_listid(resp.text)
    if not list_id:
        return {"ok": False, "error": "未找到北京新闻节目列表 ID（页面结构可能变化）"}
    data, err = http_get(
        f"{BJXW_INFOFLOW}?list_id={list_id}&refresh=1&count=20&expands=pageinfo",
        referer=BJXW_URL,
        as_json=True,
    )
    if err:
        return {"ok": False, "error": f"北京新闻列表获取失败：{err}"}
    items = _parse_bjxw(data)
    if not items:
        return {"ok": False, "error": "未解析到北京新闻节目"}
    dates = sorted({it["date"] for it in items if it["date"]}, reverse=True)
    payload = {
        "ok": True,
        "source": "北京新闻",
        "page": BJXW_URL,
        "count": len(items),
        "dates": dates,
        "items": items,
    }
    _cache_put(key, payload)
    return payload


PROGRAMS = {
    "xwlb": {
        "name": "新闻联播",
        "desc": "CCTV《新闻联播》每日更新完整视频与当日分条",
        "getter": get_xwlb,
        "page": XWLB_URL,
    },
    "bjxw": {
        "name": "北京新闻",
        "desc": "BRTV《北京新闻》每日更新完整视频",
        "getter": get_bjxw,
        "page": BJXW_URL,
    },
}


# ---------------------------------------------------------------------------
# 播放地址解析
# ---------------------------------------------------------------------------
def _cctv_video(page_url):
    """从央视视频页取 guid，再取 mp4 地址。"""
    resp, err = http_get(page_url, referer=page_url)
    if err:
        return {"ok": False, "error": f"页面获取失败：{err}"}
    m = re.search(r'guid\s*=\s*"([0-9a-fA-F]{32})"', resp.text)
    if not m:
        return {"ok": False, "error": "未找到视频 ID"}
    pid = m.group(1)
    info, err = http_get(f"{XWLB_VIDEO_API}?pid={pid}", referer=page_url, as_json=True)
    if err:
        return {"ok": False, "error": f"视频信息获取失败：{err}"}
    if not isinstance(info, dict) or info.get("ack") != "yes":
        return {"ok": False, "error": "视频信息接口返回异常"}
    chapters = ((info.get("video") or {}).get("chapters")) or []
    urls = [c.get("url") for c in chapters if c.get("url")]
    if not urls:
        return {"ok": False, "error": "未找到可播放地址"}
    # 时长最长的分片通常是正片
    best = None
    for c in chapters:
        u = c.get("url")
        if not u:
            continue
        try:
            dur = float(c.get("duration") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        if best is None or dur > best[0]:
            best = (dur, u)
    return {
        "ok": True,
        "url": (best or (0, urls[0]))[1],
        "type": "mp4",
        "title": info.get("title", ""),
        "duration": (info.get("video") or {}).get("totalLength", ""),
    }


def _btime_video(page_url, gid=""):
    """北京新闻：app.api.btime.com/video/play 直接返回签名 mp4 地址。"""
    if not gid:
        m = re.search(r"item\.btime\.com/([0-9a-z]+)", page_url or "")
        if not m:
            return {"ok": False, "error": "无法识别的链接", "page": page_url}
        gid = m.group(1)
    data, err = http_get(
        f"{BJXW_PLAY}?from=pc&id={gid}&type_id=3",
        referer=page_url or "https://www.btime.com/",
        as_json=True,
    )
    if err or not isinstance(data, dict) or data.get("errno") != 0:
        return {
            "ok": False,
            "error": "解析失败：" + (err or (data or {}).get("errmsg") or "未知"),
            "page": page_url,
        }
    streams = ((data.get("data") or {}).get("video_stream")) or []
    if not streams:
        return {"ok": False, "error": "未找到可播放地址", "page": page_url}
    # 取码率最高的一路
    best = None
    for s in streams:
        try:
            rate = float(s.get("stream_rate") or 0)
        except (TypeError, ValueError):
            rate = 0.0
        if best is None or rate > best[0]:
            best = (rate, s)
    s = best[1]
    return {
        "ok": True,
        "url": s.get("stream_url", ""),
        "type": "mp4",
        "title": s.get("stream_vbt", ""),
        "duration": (data.get("data") or {}).get("duration", ""),
        "rate": s.get("stream_rate", ""),
    }


def resolve_video(page_url, gid=""):
    if "tv.cctv.com" in page_url:
        return _cctv_video(page_url)
    if "btime.com" in page_url:
        return _btime_video(page_url, gid=gid)
    return {"ok": False, "error": "不支持的来源", "page": page_url}
