"""
站内 URL 归一化工具

用于将误存为绝对本地地址的站内静态资源 URL 收口为相对路径，
避免切换域名、端口或反代入口后资源失效。
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}
_SITE_LOCAL_PREFIXES = ("/static/", "/media/")


def normalize_local_asset_url(url: Optional[str]) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""

    if raw.startswith(_SITE_LOCAL_PREFIXES):
        return raw

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return raw

    hostname = (parsed.hostname or "").strip().lower()
    path = (parsed.path or "").strip()
    if hostname in _LOCAL_HOSTS and path.startswith(_SITE_LOCAL_PREFIXES):
        normalized = path
        if parsed.query:
            normalized = f"{normalized}?{parsed.query}"
        if parsed.fragment:
            normalized = f"{normalized}#{parsed.fragment}"
        return normalized

    return raw


def normalize_local_asset_url_lines(raw_text: Optional[str]) -> str:
    raw = str(raw_text or "")
    if not raw.strip():
        return ""

    normalized_lines = [
        normalize_local_asset_url(line.strip())
        for line in raw.splitlines()
        if line and line.strip()
    ]
    return "\n".join(line for line in normalized_lines if line)
