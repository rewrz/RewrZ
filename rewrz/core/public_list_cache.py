"""公共列表页缓存（首页、分类归档、标签归档）及边缘缓存响应头。

这些页面占公开访问量的大头，但内容在几十秒内几乎不变。缓存渲染后的整页
HTML 可以让命中请求直接跳过文章查询、封面预取、模板渲染与导航上下文构建。

约束：
- 只缓存匿名 GET 的完整页面，HTMX 分页追加片段不缓存；
- 列表页不含需要 CSRF 令牌的表单，匿名访问时中间件不创建 CSRF 会话，
  因此响应既没有 ``Set-Cookie`` 也没有 ``Vary: Cookie``，可被 CDN 安全缓存；
- 游客主题 Cookie 参与进程内缓存键；带主题 Cookie 的请求不标注边缘缓存头，
  避免 CDN 按 URL 缓存后把 A 的主题页面发给 B；
- 写文章后调用 ``invalidate_public_list_cache`` 递增版本号，让旧条目立即失效，
  渲染期间发生的写入也不会把旧内容重新写回缓存。
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Optional

from fastapi import Request

# 列表页允许的最大陈旧时间。20 秒足以吸收突发流量，又不会让作者发布后
# 长时间看不到自己的新文章。
DEFAULT_TTL_SECONDS = 20

# 边缘缓存响应头：浏览器不缓存 HTML，CDN / 反向代理按 s-maxage 缓存 20 秒。
PUBLIC_CACHE_CONTROL = f"public, max-age=0, s-maxage={DEFAULT_TTL_SECONDS}"

# 最多缓存多少个页面变体（分页、分类、标签、主题组合）。
MAX_ENTRIES = 64

# 缓存 HTML 的总字符预算：单页通常几百 KB，限制总量后即使条目打满，
# 额外内存也不会超过约 8MB，符合 512MB VPS 的内存预算。
MAX_TOTAL_CHARS = 8 * 1024 * 1024

# 游客主题 Cookie 名，与 themes 模块保持一致。
GUEST_THEME_COOKIE_NAME = "rewrz_theme"

# 纳入缓存的路径前缀（首页单独判断）。
_CACHEABLE_PREFIXES = ("/archives/by-category/", "/archives/by-tag/")

_lock = threading.Lock()
_cache: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
_total_chars = 0
_version = 0


def is_public_list_page_path(path: str) -> bool:
    """判断路径是否属于可缓存的公共列表页。"""
    if path == "/":
        return True
    return path.startswith(_CACHEABLE_PREFIXES)


def is_cacheable_public_list_request(request: Request) -> bool:
    """判断当前请求是否允许使用页面缓存。"""
    if request.method != "GET":
        return False
    if str(request.headers.get("HX-Request") or "").lower() == "true":
        return False
    if str(request.query_params.get("append") or "") == "1":
        return False
    if getattr(request.state, "authenticated_user", None) is not None:
        return False
    return is_public_list_page_path(request.url.path)


def should_skip_csrf_token(request: Request) -> bool:
    """匿名 GET 列表页不创建 CSRF 会话，否则响应会带 Set-Cookie 而无法被 CDN 缓存。

    列表页不含评论等受保护表单；游客的主题偏好由浏览器本地 Cookie 维护，
    不需要服务端令牌。已登录用户仍按原逻辑创建令牌，不受影响。
    """
    return (
        request.method == "GET"
        and is_public_list_page_path(request.url.path)
        and getattr(request.state, "authenticated_user", None) is None
    )


def _build_cache_key(request: Request, version: int) -> str:
    """缓存键包含完整路径、查询串与游客主题，避免不同变体互相污染。"""
    theme_preference = str(request.cookies.get(GUEST_THEME_COOKIE_NAME) or "").strip().lower()
    query = request.url.query
    return f"{request.url.path}?{query}|theme={theme_preference}|v={version}"


def get_public_list_cache_version() -> int:
    """读取当前缓存版本，渲染前记录，写入时用于判定是否已被写操作失效。"""
    with _lock:
        return _version


def get_cached_public_list_html(
    request: Request,
    *,
    version: int,
) -> Optional[str]:
    """命中缓存时返回整页 HTML，未命中返回 None。

    ``version`` 必须由路由在查询数据库之前读取并传入，这样渲染期间发生的写操作
    会让本次结果在写入阶段被丢弃，避免旧内容回灌缓存。
    """
    if not is_cacheable_public_list_request(request):
        return None

    key = _build_cache_key(request, version)
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, html = entry
        if expires_at <= now:
            _drop_entry(key)
            return None
        _cache.move_to_end(key)

    return html


def store_public_list_html(
    request: Request,
    html: str,
    *,
    version: int,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> None:
    """写入渲染结果；渲染期间发生过写操作（版本变化）则放弃本次写入。

    列表页不得包含需要 CSRF 令牌的表单：匿名访问不创建会话，缓存的是纯静态
    HTML，命中后可直接返回给任意游客。已登录用户不进入缓存。
    """
    if not is_cacheable_public_list_request(request):
        return

    size = len(html)
    if size > MAX_TOTAL_CHARS:
        return
    expires_at = time.monotonic() + max(1, int(ttl_seconds))

    global _total_chars
    with _lock:
        if version != _version:
            return
        key = _build_cache_key(request, version)
        _drop_entry(key)
        _cache[key] = (expires_at, html)
        _total_chars += size
        while _cache and (len(_cache) > MAX_ENTRIES or _total_chars > MAX_TOTAL_CHARS):
            _, (_, removed_html) = _cache.popitem(last=False)
            _total_chars -= len(removed_html)


def _drop_entry(key: str) -> None:
    """移除指定条目并同步字符计数，调用方必须持有锁。"""
    global _total_chars
    entry = _cache.pop(key, None)
    if entry is not None:
        _total_chars -= len(entry[1])


def apply_public_list_cache_headers(request: Request, response) -> None:
    """为列表页响应写入缓存策略。

    匿名 200 响应标记 ``public, max-age=0, s-maxage=20``，让 CDN 在 20 秒内
    直接复用整页 HTML，把突发流量挡在应用进程之外；浏览器每次都回源校验。

    登录态、HTMX 分页片段与错误页一律 ``private, no-store``：即使 CDN 配置了
    Cache Everything，也不会把个性化页面或分页片段缓存后发给其他访客。

    带游客主题 Cookie 的请求同样不允许边缘缓存：CDN 的缓存键只有 URL，
    无法区分主题，缓存后会把一个访客的主题页面发给另一个访客。
    """
    has_guest_theme_cookie = bool(str(request.cookies.get(GUEST_THEME_COOKIE_NAME) or "").strip())
    if response.status_code == 200 and is_cacheable_public_list_request(request) and not has_guest_theme_cookie:
        response.headers.setdefault("Cache-Control", PUBLIC_CACHE_CONTROL)
    else:
        response.headers.setdefault("Cache-Control", "private, no-store")


def invalidate_public_list_cache() -> None:
    """文章内容变化后调用：递增版本并清空已有条目。"""
    global _version, _total_chars
    with _lock:
        _version += 1
        _cache.clear()
        _total_chars = 0


def clear_public_list_cache() -> None:
    """测试用：清空缓存并让旧版本条目立即失效。"""
    invalidate_public_list_cache()
