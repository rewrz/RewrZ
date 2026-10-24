"""公开页面访问上报端点

公开页面内联 JS 通过 navigator.sendBeacon 上报页面浏览，用于覆盖
CDN / 反向代理命中缓存、请求未回源的访问。该端点不写数据库，只进入
访问统计的有界内存缓冲；POST 不会被 CDN 缓存，响应固定 no-store。
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..core import traffic_analytics
from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _hostname(value: str) -> str:
    """从 Host 头或 URL 中提取小写主机名，兼容 IPv6 与端口。"""
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return (urlsplit(raw if "://" in raw else f"//{raw}").hostname or "").lower()
    except ValueError:
        return ""


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def _same_host(first: str, second: str) -> bool:
    if not first or not second:
        return False
    return _strip_www(first) == _strip_www(second)


def _is_same_origin(request: Request) -> bool:
    """拒绝明显的跨站上报；缺少来源头时保持兼容放行。"""
    headers = request.headers
    fetch_site = str(headers.get("sec-fetch-site", "") or "").strip().lower()
    if fetch_site and fetch_site not in {"same-origin", "same-site", "none"}:
        return False

    origin = str(headers.get("origin", "") or "").strip()
    if not origin:
        return True
    origin_host = _hostname(origin)
    # 反向代理可能改写 Host，额外允许与站点配置域名比对
    return _same_host(origin_host, _hostname(headers.get("host", ""))) or _same_host(
        origin_host, _hostname(settings.SITE_URL)
    )


async def _read_limited_body(request: Request, limit: int) -> bytes | None:
    """按上限读取请求体，避免超大请求体占用内存；超限返回 None。"""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limit:
                return None
        except ValueError:
            return None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            return None
    return bytes(body)


@router.post(traffic_analytics.BEACON_PATH)
async def traffic_pageview_beacon(request: Request):
    """接收前端页面浏览上报；无论成功失败都返回 204，避免影响页面。"""
    response = Response(status_code=204)
    response.headers["Cache-Control"] = "no-store"
    try:
        if not traffic_analytics.is_enabled() or not _is_same_origin(request):
            return response

        raw_body = await _read_limited_body(
            request, traffic_analytics.BEACON_MAX_BODY_BYTES
        )
        if raw_body is None:
            return response
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return response
        if not isinstance(payload, dict):
            return response

        traffic_analytics.record_beacon_page_view(
            request,
            path=str(payload.get("path") or ""),
            referrer=str(payload.get("referrer") or ""),
            query_string=str(payload.get("query") or ""),
        )
    except Exception:
        logger.debug("访问统计 beacon 处理失败，已忽略", exc_info=True)
    return response
