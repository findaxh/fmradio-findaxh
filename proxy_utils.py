#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代理相关纯标准库工具：SSRF 防护、URL 校验、HLS 清单重写。
独立成模块，便于在不依赖 Flask 的情况下单元测试。
"""
import ipaddress
import os
import socket
import urllib.parse

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 默认开启 SSRF 防护，可通过环境变量 DISABLE_SSRF=1 关闭
SSRF_GUARD = os.environ.get("DISABLE_SSRF", "0") not in ("1", "true", "True")


def is_blocked_host(host: str) -> bool:
    """禁止访问内网/回环/链路本地等地址，降低 SSRF 风险。"""
    if not host:
        return True
    if host.lower() in ("localhost", "0.0.0.0"):
        return True
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


def safe_url(raw: str):
    """校验并清洗待代理的 URL；不合法或被 SSRF 规则拦截则返回 None。"""
    if not raw:
        return None
    try:
        decoded = urllib.parse.unquote(raw)
        if decoded.startswith("http"):
            raw = decoded
    except Exception:
        pass
    p = urllib.parse.urlparse(raw)
    if p.scheme not in ("http", "https"):
        return None
    if SSRF_GUARD and is_blocked_host(p.hostname or ""):
        return None
    return raw


def rewrite_m3u8(text: str, base_url: str) -> str:
    """将 m3u8 中的相对/绝对切片地址重写为经本服务代理的地址。"""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            out.append(line)
            continue
        if s.startswith("http://") or s.startswith("https://"):
            abs_url = s
        else:
            abs_url = urllib.parse.urljoin(base_url, s)
        out.append("/proxy?url=" + urllib.parse.quote(abs_url, safe=""))
    return "\n".join(out)
