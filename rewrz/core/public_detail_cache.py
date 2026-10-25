"""公开详情页整页缓存（文章详情、独立页面）。

详情页是匿名访问的主要落点，但内容在几十秒内几乎不变。缓存渲染后的整页
HTML，可以让命中请求在 ``add_global_context`` 阶段直接返回，跳过设置查询、
文章查询、评论装配、模板渲染与统计写入。

与列表页缓存的关键差异：详情页包含评论表单，需要 CSRF 令牌。缓存时把当前
令牌替换为占位符，命中时再换成当前访客自己的令牌，表单始终可用。

约束：
- 只缓存匿名 GET 的完整页面：HTMX 片段、带查询串、登录态、访客互动令牌、
  评论解锁 / 密码访问 Cookie 的请求一律跳过；
- 条目记录内容 ID，命中时由调用方累加浏览量（只写内存，不产生数据库写）；
- 游客主题 Cookie 参与缓存键，不同主题各自缓存；
- 响应始终 ``private, no-store``：页面含访客专属令牌，不能被 CDN 共享缓存；
- 写操作后调用 ``invalidate_public_detail_cache`` 递增版本号并清空条目。
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Optional

from fastapi import Request

# 详情页允许的最大陈旧时间：20 秒足以吸收突发流量，也不影响作者发布后预览
DEFAULT_TTL_SECONDS = 20

# 最多缓存多少个页面变体（文章 + 页面 + 主题组合）
MAX_ENTRIES = 128

# 缓存 HTML 的总字符预算：单页通常几百 KB，限制总量后额外内存不超过约 8MB
MAX_TOTAL_CHARS = 8 * 1024 * 1024

# CSRF 令牌占位符：命中缓存时替换为当前访客的令牌
CSRF_TOKEN_PLACEHOLDER = "__REWRZ_CSRF_TOKEN__"

GUEST_THEME_COOKIE_NAME = "rewrz_theme"

# 出现这些 Cookie 的请求跳过缓存：页面内容会因身份或解锁状态而不同
_SENSITIVE_COOKIE_NAMES = ("access_token", "rewrz_visitor_token")
_SENSITIVE_COOKIE_PREFIXES = ("rewrz_comment_unlock_", "rewrz_post_access_")

# 不参与详情缓存的路径前缀与入口
_SKIP_PATH_PREFIXES = ("/api/", "/static/", "/media/", "/installer")

_lock = threading.Lock()
# 条目结构：(过期时间, 带占位符的 HTML, 内容 ID)；内容 ID 用于命中时累加浏览量
_cache: "OrderedDict[str, tuple[float, str, int]]" = OrderedDict()
_total_chars = 0
_version = 0


def is_cacheable_detail_request(request: Request) -> bool:
    """判断当前请求是否允许使用详情页缓存。"""
    if request.method != "GET":
        return False
    if request.url.query:
        return False
    if str(request.headers.get("HX-Request") or "").lower() == "true":
        return False

    path = request.url.path
    if path == "/" or path.startswith(_SKIP_PATH_PREFIXES):
        return False

    from .admin_path import get_admin_path

    admin_path = str(get_admin_path() or "").strip()
    if admin_path and admin_path != "/" and (
        path == admin_path or path.startswith(admin_path + "/")
    ):
        return False

    for cookie_name in request.cookies.keys():
        if cookie_name in _SENSITIVE_COOKIE_NAMES:
            return False
        if cookie_name.startswith(_SENSITIVE_COOKIE_PREFIXES):
            return False

    # 已登录用户的页面属于个性化预览，不进入缓存
    if getattr(request.state, "authenticated_user", None) is not None:
        return False
    return True


def _build_cache_key(request: Request, version: int) -> str:
    """缓存键包含路径与游客主题，避免不同主题的页面互相污染。"""
    theme_preference = str(request.cookies.get(GUEST_THEME_COOKIE_NAME) or "").strip().lower()
    return f"{request.url.path}|theme={theme_preference}|v={version}"


def get_public_detail_cache_version() -> int:
    """读取当前缓存版本，渲染前记录，写入时用于判定是否已被写操作失效。"""
    with _lock:
        return _version


def get_cached_public_detail_entry(
    request: Request,
    *,
    version: int,
) -> Optional[tuple[str, int]]:
    """命中缓存时返回 (带占位符的整页 HTML, 内容 ID)，未命中返回 None。

    内容 ID 供调用方在命中路径上继续累加浏览量，避免整页缓存导致计数失真。
    """
    if not is_cacheable_detail_request(request):
        return None

    key = _build_cache_key(request, version)
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, html, content_id = entry
        if expires_at <= now:
            _drop_entry(key)
            return None
        _cache.move_to_end(key)
    return html, content_id


def store_public_detail_html(
    request: Request,
    html: str,
    *,
    version: int,
    csrf_token: str,
    content_id: int,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> None:
    """写入渲染结果；渲染期间发生过写操作（版本变化）则放弃本次写入。"""
    if not is_cacheable_detail_request(request):
        return
    token = str(csrf_token or "")
    if not token or token not in html:
        return

    cached_html = html.replace(token, CSRF_TOKEN_PLACEHOLDER)
    size = len(cached_html)
    if size > MAX_TOTAL_CHARS:
        return

    try:
        normalized_content_id = max(0, int(content_id))
    except (TypeError, ValueError):
        normalized_content_id = 0

    expires_at = time.monotonic() + max(1, int(ttl_seconds))
    global _total_chars
    with _lock:
        if version != _version:
            return
        key = _build_cache_key(request, version)
        _drop_entry(key)
        _cache[key] = (expires_at, cached_html, normalized_content_id)
        _total_chars += size
        while _cache and (len(_cache) > MAX_ENTRIES or _total_chars > MAX_TOTAL_CHARS):
            _, (_, removed_html, _) = _cache.popitem(last=False)
            _total_chars -= len(removed_html)


def render_cached_public_detail_html(html: str, csrf_token: str) -> str:
    """把缓存中的占位符替换为当前访客的 CSRF 令牌。"""
    token = str(csrf_token or "")
    if not token:
        return html
    return html.replace(CSRF_TOKEN_PLACEHOLDER, token)


def store_public_detail_response(request: Request, response, *, version: int, content_id: int) -> None:
    """从模板响应中提取 HTML 并写入缓存。

    Starlette 的 TemplateResponse 在构造时已完成渲染，``body`` 可直接读取。
    ``version`` 必须是路由查询数据库之前记录的版本号，渲染期间发生的写操作
    会让本次结果被丢弃，避免旧内容回灌缓存。
    """
    try:
        body = bytes(getattr(response, "body", b"") or b"")
        html = body.decode("utf-8")
    except Exception:
        return
    store_public_detail_html(
        request,
        html,
        version=version,
        csrf_token=str(getattr(request.state, "csrf_token", "") or ""),
        content_id=content_id,
    )


def apply_public_detail_cache_headers(response) -> None:
    """详情页响应一律禁止共享缓存：HTML 中含访客专属 CSRF 令牌。"""
    response.headers.setdefault("Cache-Control", "private, no-store")


def _drop_entry(key: str) -> None:
    """移除指定条目并同步字符计数，调用方必须持有锁。"""
    global _total_chars
    entry = _cache.pop(key, None)
    if entry is not None:
        _total_chars -= len(entry[1])


def invalidate_public_detail_cache() -> None:
    """文章内容变化后调用：递增版本并清空已有条目。"""
    global _version, _total_chars
    with _lock:
        _version += 1
        _cache.clear()
        _total_chars = 0


def clear_public_detail_cache() -> None:
    """测试用：清空缓存并让旧版本条目立即失效。"""
    invalidate_public_detail_cache()
