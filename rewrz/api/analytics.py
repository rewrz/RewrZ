"""后台访问统计 API

提供独立统计页面、JSON 摘要、实时片段、仪表盘摘要与设置/清空入口。
所有 GET 响应都返回 private, no-store，避免统计页被 CDN 缓存。
"""
from __future__ import annotations

import threading
import time
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..core import traffic_analytics
from ..core.admin_path import get_admin_path, get_request_admin_path
from ..core.database import get_db
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..core.time_utils import site_now
from ..crud import traffic as crud_traffic
from ..schemas import User

router = APIRouter()
templates = get_templates()
ADMIN_PATH = get_admin_path()

SUMMARY_CACHE_TTL_SECONDS = 30
DASHBOARD_CACHE_TTL_SECONDS = 30
_CACHE_LOCK = threading.Lock()
_CACHE: dict[tuple, tuple[float, dict]] = {}
_CACHE_MAX_ENTRIES = 64


def clear_caches() -> None:
    """清空摘要缓存（清空统计、修改设置、测试隔离时调用）。"""
    with _CACHE_LOCK:
        _CACHE.clear()


def _cache_get(key: tuple) -> dict | None:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if expires_at <= time.monotonic():
            _CACHE.pop(key, None)
            return None
        return payload


def _cache_set(key: tuple, payload: dict, ttl: int) -> None:
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX_ENTRIES:
            for stale_key in sorted(_CACHE, key=lambda item: _CACHE[item][0])[
                : len(_CACHE) - _CACHE_MAX_ENTRIES + 1
            ]:
                _CACHE.pop(stale_key, None)
        _CACHE[key] = (time.monotonic() + ttl, payload)


def _summary_payload(
    db: Session,
    range_key: str | None,
    start: str | None,
    end: str | None,
    *,
    refresh: bool = False,
) -> dict:
    cache_key = ("summary", range_key or "today", start or "", end or "")
    if not refresh:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    payload = crud_traffic.get_analytics_summary(db, range_key, start, end)
    _cache_set(cache_key, payload, SUMMARY_CACHE_TTL_SECONDS)
    return payload


def _dashboard_payload(db: Session, *, refresh: bool = False) -> dict:
    cache_key = ("dashboard",)
    if not refresh:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    payload = crud_traffic.get_dashboard_summary(db)
    _cache_set(cache_key, payload, DASHBOARD_CACHE_TTL_SECONDS)
    return payload


def _no_store(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _checkbox_to_bool(raw_value: Optional[str]) -> bool:
    return str(raw_value or "").strip().lower() in {"1", "true", "on", "yes", "checked"}


def _redirect_analytics(request: Request, *, range_key: str, start: str, end: str, flag: str) -> RedirectResponse:
    params = {"range": range_key or "today", flag: "1"}
    if range_key == "custom":
        if start:
            params["start"] = start
        if end:
            params["end"] = end
    target = f"{get_request_admin_path(request)}/analytics?{urlencode(params)}"
    return RedirectResponse(url=target, status_code=303)


@router.get(f"{ADMIN_PATH}/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    range_key: str = Query("today", alias="range"),
    start: str = Query(""),
    end: str = Query(""),
    saved: int = Query(0),
    cleared: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        summary = _summary_payload(db, range_key, start, end)
    except crud_traffic.TrafficRangeError as exc:
        return PlainTextResponse(f"统计范围参数不合法：{exc}", status_code=400)

    analytics_settings = traffic_analytics.get_analytics_settings(db)
    response = templates.TemplateResponse(
        request,
        "admin/analytics.html",
        {
            "request": request,
            "user": current_user,
            "admin_path": get_request_admin_path(request),
            "summary": summary,
            "analytics_settings": analytics_settings,
            "today_label": site_now().strftime("%Y-%m-%d"),
            "saved": bool(saved),
            "cleared": bool(cleared),
        },
    )
    return _no_store(response)


@router.get(f"{ADMIN_PATH}/api/v1/analytics/summary")
async def analytics_summary(
    request: Request,
    range_key: str = Query("today", alias="range"),
    start: str = Query(""),
    end: str = Query(""),
    refresh: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        payload = _summary_payload(db, range_key, start, end, refresh=bool(refresh))
    except crud_traffic.TrafficRangeError as exc:
        return _no_store(JSONResponse({"detail": str(exc)}, status_code=400))
    return _no_store(JSONResponse(payload))


@router.get(f"{ADMIN_PATH}/api/v1/analytics/live", response_class=HTMLResponse)
async def analytics_live(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    live = crud_traffic.get_live_fragment(db)
    response = templates.TemplateResponse(
        request,
        "admin/components/analytics_live.html",
        {"request": request, "live": live},
    )
    return _no_store(response)


@router.get(f"{ADMIN_PATH}/api/v1/dashboard/traffic-summary", response_class=HTMLResponse)
async def dashboard_traffic_summary(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    summary = _dashboard_payload(db)
    response = templates.TemplateResponse(
        request,
        "admin/components/dashboard_traffic_summary.html",
        {
            "request": request,
            "traffic": summary,
            "analytics_url": f"{get_request_admin_path(request)}/analytics",
        },
    )
    return _no_store(response)


@router.post(f"{ADMIN_PATH}/analytics/settings")
async def update_analytics_settings(
    request: Request,
    enabled: Optional[str] = Form(None),
    retention_days: int = Form(365),
    range_key: str = Form("today", alias="range"),
    start: str = Form(""),
    end: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_csrf_token(request, csrf_token)
    if retention_days < traffic_analytics.MIN_RETENTION_DAYS or (
        retention_days > traffic_analytics.MAX_RETENTION_DAYS
    ):
        return PlainTextResponse("保留天数必须在 30 到 730 天之间", status_code=400)

    traffic_analytics.save_analytics_settings(
        db,
        enabled=_checkbox_to_bool(enabled),
        retention_days=retention_days,
    )
    clear_caches()
    return _redirect_analytics(
        request, range_key=range_key, start=start, end=end, flag="saved"
    )


@router.post(f"{ADMIN_PATH}/analytics/clear")
async def clear_analytics(
    request: Request,
    range_key: str = Form("today", alias="range"),
    start: str = Form(""),
    end: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_csrf_token(request, csrf_token)
    traffic_analytics.clear_analytics_data(db)
    clear_caches()
    return _redirect_analytics(
        request, range_key=range_key, start=start, end=end, flag="cleared"
    )
