#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FM 网络电台 Web 服务（直连模式）
- 提供前端页面
- /api/radiobrowser 查询 Radio Browser 开源电台索引：
    * 多镜像回退、按 stationuuid/url 去重
    * 自动打“区域标签”(中央台/北京/江苏/…) 与“类别标签”(新闻/交通/音乐/…)
- /api/probe 检测电台源存活（服务器侧，用于排查死链）
"""
import json
import os
import threading
import time
import urllib.parse

import requests
from flask import Flask, Response, request, send_from_directory, jsonify
from requests.adapters import HTTPAdapter

from proxy_utils import USER_AGENT, safe_url
from tagging import tag_station, norm_name

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR)

# Radio Browser API 要求的自定义 User-Agent（其使用规范）
RB_UA = "FMRadioWeb/1.0"

# ---------------------------------------------------------------------------
# 网络层：默认「纯直连」，完全不使用任何代理
#
# 背景：requests 默认 trust_env=True，会自动使用环境变量 HTTP(S)_PROXY 或
# Windows 系统代理（Clash Verge 等会把 127.0.0.1:7897/19999 写成系统代理）。
# 代理软件未启动或被关掉时，所有出站请求都会报
# ProxyError(WinError 10061 目标计算机积极拒绝)，
# 表现为「启动后加载失败，刷新几次又正常」。
#
# 本项目定位为纯直连部署，因此默认 RB_PROXY_MODE=direct：
#   - 忽略一切环境变量代理与 Windows 系统代理
#   - 不使用 Clash Verge / v2ray / 任何本地代理
#
# 仅在特殊网络（本机确实必须走代理才能出网）时才手动改：
#   RB_PROXY_MODE=system  只走系统/环境代理
#   RB_PROXY_MODE=auto    直连失败后回退系统代理
# ---------------------------------------------------------------------------
RB_PROXY_MODE = os.environ.get("RB_PROXY_MODE", "direct").strip().lower()
RB_TIMEOUT = float(os.environ.get("RB_TIMEOUT", "8"))          # 单次请求超时(秒)
RB_DEADLINE = float(os.environ.get("RB_DEADLINE", "30"))       # 每通道时限(秒)
CACHE_TTL = int(os.environ.get("RB_CACHE_TTL", "300"))         # 结果缓存秒数

_ENV_PROXY_KEYS = ("http_proxy", "https_proxy", "all_proxy", "ftp_proxy")

# 记录启动时看到的代理配置（仅用于日志/诊断）
DETECTED_PROXIES = {
    k: v for k, v in os.environ.items()
    if k.lower() in _ENV_PROXY_KEYS or k.lower() == "no_proxy"
}

if RB_PROXY_MODE == "direct":
    # 彻底切断：连代理环境变量本身也清掉，杜绝任何库间接读到系统/Clash 代理
    for _k in list(os.environ):
        if _k.lower() in _ENV_PROXY_KEYS:
            os.environ.pop(_k, None)

try:
    from urllib3.util.retry import Retry

    _RETRY = Retry(
        total=1, connect=1, read=0, status=1,
        backoff_factor=0.3, allowed_methods=frozenset(["GET"]),
    )
except Exception:  # 兼容缺少 urllib3.util.retry 的环境
    _RETRY = 0


def _make_session(trust_env: bool) -> requests.Session:
    s = requests.Session()
    s.trust_env = trust_env  # False = 忽略环境变量与系统代理
    try:
        ad = HTTPAdapter(max_retries=_RETRY, pool_maxsize=16, pool_connections=8)
        s.mount("http://", ad)
        s.mount("https://", ad)
    except Exception:
        pass
    return s


DIRECT_SESSION = _make_session(False)
SYSTEM_SESSION = _make_session(True)

MIRRORS = [
    "https://de1.api.radio-browser.info",
    "https://de2.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
    "https://all.api.radio-browser.info",
]


def _channels():
    """按 RB_PROXY_MODE 返回 [(通道名, session), ...]"""
    if RB_PROXY_MODE == "direct":
        return [("direct", DIRECT_SESSION)]
    if RB_PROXY_MODE == "system":
        return [("proxy", SYSTEM_SESSION)]
    return [("direct", DIRECT_SESSION), ("proxy", SYSTEM_SESSION)]


def _request_all(path, **kw):
    """依次尝试 通道(direct/proxy) × 镜像；返回 (resp, info) 或 (None, errors)。

    每个通道独立限时（RB_DEADLINE / 通道数），保证后面的通道一定有机会被尝试，
    不会因前一个通道卡在超时上而耗尽全部预算。
    """
    errors = []
    chans = _channels()
    per_channel = max(RB_DEADLINE / max(len(chans), 1), 5.0)
    for cname, sess in chans:
        deadline = time.time() + per_channel
        for base in MIRRORS:
            if time.time() > deadline:
                errors.append(f"[ {cname} 通道时限已到，切换下一通道 ]")
                break          # 换通道，而不是整体放弃
            try:
                r = sess.get(base + path, timeout=RB_TIMEOUT, **kw)
                if r.status_code == 200:
                    return r, {"mirror": base.split("//")[1], "channel": cname}
                errors.append(f"{base.split('//')[1]}[{cname}] HTTP {r.status_code}")
            except Exception as e:
                errors.append(f"{base.split('//')[1]}[{cname}] {type(e).__name__}")
    return None, errors


# 简单的进程内结果缓存，避免每次刷新都打远端 API
_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key):
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
        return None


def _cache_put(key, payload):
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), payload)


def _cache_stale(key):
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        return hit[1] if hit else None


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/radiobrowser")
def api_radiobrowser():
    """查询 Radio Browser 开源电台索引（需自定义 User-Agent）。
    参数：country(默认CN，2位用countrycode)、tag、name、limit、offset
    """
    country = request.args.get("country", "CN")
    limit = request.args.get("limit", "300")
    tag = request.args.get("tag", "")
    name = request.args.get("name", "")
    offset = request.args.get("offset", "0")

    params = {
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true",
        "limit": limit,
        "offset": offset,
    }
    if len(country) == 2:
        params["countrycode"] = country
    elif country:
        params["country"] = country
    if tag:
        params["tag"] = tag
    if name:
        params["name"] = name

    cache_key = (country, limit, tag, name, offset)
    cached = _cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    resp, info = _request_all(
        "/json/stations/search",
        params=params,
        headers={"User-Agent": RB_UA},
    )

    if resp is not None:
        try:
            data = resp.json()
        except Exception as e:
            data = None
            info = {"error": f"响应不是合法 JSON：{e}"}
        if isinstance(data, list):
            out = []
            seen_uuid = set()
            seen_url = set()
            seen_name = set()
            for s in data:
                uuid = s.get("stationuuid")
                url = (s.get("url_resolved") or s.get("url") or "").strip()
                if not url:
                    continue
                # 去重1：同一 stationuuid 或同一 url 只保留一个
                if uuid and uuid in seen_uuid:
                    continue
                if url in seen_url:
                    continue
                # 去重2：同一电台的不同镜像/条目（归一化名称 + 国家 相同则合并）
                nkey = (norm_name(s.get("name")), (s.get("country") or "").lower())
                if nkey in seen_name:
                    continue
                if uuid:
                    seen_uuid.add(uuid)
                seen_url.add(url)
                seen_name.add(nkey)

                region, cats = tag_station(s.get("name"), s.get("tags"), s.get("state"))
                out.append(
                    {
                        "name": (s.get("name") or "").strip(),
                        "url": url,
                        "type": "hls"
                        if url.lower().split("?")[0].endswith(".m3u8")
                        else "audio",
                        "country": s.get("country", ""),
                        "state": s.get("state", ""),
                        "tags": s.get("tags", ""),
                        "favicon": s.get("favicon", ""),
                        "codec": s.get("codec", ""),
                        "bitrate": s.get("bitrate", 0),
                        "region": region,
                        "cats": cats,
                    }
                )
            payload = {"ok": True, "count": len(out), "stations": out, "via": info}
            _cache_put(cache_key, payload)
            return jsonify(payload)

    # 全部失败：有旧缓存就降级返回旧数据，避免页面空白
    err_detail = info.get("error") if isinstance(info, dict) else None
    if isinstance(info, list):
        err_detail = "；".join(info[:4])
    stale = _cache_stale(cache_key)
    if stale:
        stale = dict(stale)
        stale["stale"] = True
        stale["warning"] = "远端获取失败，显示的是上一次缓存结果"
        return jsonify(stale)
    return (
        jsonify(
            {
                "ok": False,
                "error": err_detail or "所有 Radio Browser 镜像均不可达",
                "proxy_mode": RB_PROXY_MODE,
                "detected_proxy_env": DETECTED_PROXIES,
            }
        ),
        502,
    )


@app.route("/api/probe")
def api_probe():
    """探测服务器到电台源站的可达性，用于排查死链。"""
    raw = request.args.get("url", "")
    url = safe_url(raw)
    if not url:
        return jsonify({"ok": False, "error": "invalid or blocked url"}), 400
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": urllib.parse.urlparse(url).scheme
        + "://"
        + (urllib.parse.urlparse(url).hostname or "")
        + "/",
        "Range": "bytes=0-1023",
    }
    last_err = None
    for cname, sess in _channels():
        try:
            resp = sess.get(
                url, headers=headers, stream=True,
                timeout=(6, 12), allow_redirects=True,
            )
            status = resp.status_code
            ctype = resp.headers.get("Content-Type", "")
            final = resp.url
            try:
                next(resp.iter_content(1024))
            except Exception:
                pass
            resp.close()
            return jsonify(
                {
                    "ok": status < 400,
                    "status": status,
                    "content_type": ctype,
                    "redirected": final != url,
                    "channel": cname,
                }
            )
        except Exception as e:
            last_err = str(e)
    return jsonify({"ok": False, "error": last_err or "unknown", "channel": "none"})


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "proxy_mode": RB_PROXY_MODE})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    if RB_PROXY_MODE == "direct":
        print("[FM] 网络模式: 直连（不使用任何代理，已忽略系统/环境变量代理）")
        if DETECTED_PROXIES:
            print(f"[FM] 检测到代理配置 {DETECTED_PROXIES} —— 已强制绕过，"
                  f"Clash Verge 等不会影响本服务")
    else:
        print(f"[FM] 网络模式: {RB_PROXY_MODE}")
        if DETECTED_PROXIES:
            print(f"[FM] 检测到代理配置: {DETECTED_PROXIES}")
    print(f"[FM] 端口: {port}")
    # 0.0.0.0 便于 frp / 局域网访问；生产可加反向代理
    app.run(host="0.0.0.0", port=port, threaded=True)
