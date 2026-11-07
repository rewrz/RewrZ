"""垃圾爬虫与扫描路径拦截中间件。

目标：在进入会话、设置、数据库等任何业务逻辑之前，直接拒绝明显无价值的
爬虫与扫描请求，降低带宽与数据库压力。

拦截策略（顺序不可调换）：
1. 白名单优先：正规搜索引擎、社交预览、可用性监控等 UA 一律放行；
2. 黑名单：商业 SEO 抓取、AI 训练抓取、扫描器等已知垃圾 UA 一律 403；
3. 通用兜底：UA 含 bot / crawler / spider / scraper 的请求一律 403；
4. 空 UA 一律 403（正常浏览器与订阅器都会携带 UA）；
5. 扫描路径：PHP/ASP/JSP 等无价值后缀与 wp-admin、.env 等探测路径，
   无论什么 UA 都直接返回 404；
6. 仅 `/robots.txt` 豁免 UA 拦截：爬虫必须先读到 Disallow 规则才谈得上
   遵守；站点地图含全站 URL 清单、订阅入口属于内容输出，仍一律按黑名单拦截。

刻意放行的客户端：curl / wget / python-requests / Go-http-client 等
不匹配通用规则，避免误杀健康检查与自建订阅器；这些客户端的异常扫描
行为由第 5 条路径规则兜底。

白名单与黑名单都匹配 UA 的小写形式，按子串匹配。
"""
from __future__ import annotations

import re
from typing import Iterable

from .admin_path import get_admin_path
from .config import settings

# 正规爬虫 / 预览 / 监控白名单：先于黑名单与通用规则判断。
# 覆盖主流搜索引擎、社交平台链接预览、站点可用性监控。
_ALLOWED_UA_TOKENS: tuple[str, ...] = (
    # Google 搜索与相关官方抓取
    "googlebot",
    "google-inspectiontool",
    "googleother",
    "google-read-aloud",
    "adsbot-google",
    "mediapartners-google",
    "apis-google",
    "feedfetcher-google",
    # Bing
    "bingbot",
    "msnbot",
    "adidxbot",
    "bingpreview",
    # 百度 / 搜狗 / 360 / 神马
    "baiduspider",
    "sogou",
    "360spider",
    "haosouspider",
    "yisouspider",
    # Yandex / DuckDuckGo / Yahoo / Seznam / Qwant
    "yandexbot",
    "duckduckbot",
    "duckduckgo",
    "slurp",
    "seznambot",
    "qwantify",
    # Apple
    "applebot",
    # 社交平台链接预览
    "facebookexternalhit",
    "facebookbot",
    "twitterbot",
    "linkedinbot",
    "telegrambot",
    "whatsapp",
    "slackbot",
    "discordbot",
    "pinterest",
    "redditbot",
    "mastodon",
    # 可用性监控
    "uptimerobot",
    "pingdom",
    "statuscake",
    "site24x7",
    "freshping",
    "betteruptime",
    "better uptime",
    "hetrixtools",
    "nodeping",
    "checkly",
)

# 已知垃圾爬虫：商业 SEO 工具、AI 训练抓取、扫描器、无价值采集器。
_BLOCKED_UA_TOKENS: tuple[str, ...] = (
    # 商业 SEO / 反链工具
    "semrush",
    "ahrefs",
    "mj12bot",
    "dotbot",
    "blexbot",
    "dataforseo",
    "serpstat",
    "megaindex",
    "rogerbot",
    "screaming frog",
    "siteaudit",
    "zoominfo",
    "leiki",
    "nimbusbot",
    "barkrowler",
    "linkdexbot",
    "seokicks",
    "babbar",
    "grapeshot",
    "magpie-crawler",
    "exabot",
    "ccbot",
    "petalbot",
    "bytespider",
    "timpibot",
    "omgili",
    "youbot",
    # AI 训练 / 数据采集
    "gptbot",
    "oai-searchbot",
    "chatgpt-user",
    "claudebot",
    "claude-web",
    "claude-user",
    "anthropic-ai",
    "perplexitybot",
    "amazonbot",
    "meta-externalagent",
    "imagesiftbot",
    "cohere-ai",
    "difybot",
    "ai2bot",
    "awariobot",
    "factset_spyderbot",
    "isscyberriskcrawler",
    # 安全扫描器与无头浏览器
    "sqlmap",
    "nikto",
    "nmap",
    "masscan",
    "zgrab",
    "dirbuster",
    "gobuster",
    "nuclei",
    "wpscan",
    "acunetix",
    "nessus",
    "hydra",
    "censys",
    "scrapy",
    "headlesschrome",
    "phantomjs",
    "puppeteer",
    "playwright",
    # 整站镜像 / 离线抓取工具
    "httrack",
    "nutch",
    "libwww-perl",
    "lwp-trivial",
    "webcopier",
    "sitesucker",
    "webzip",
)

# 通用兜底：未命中白名单但自称 bot / crawler / spider / scraper 的请求。
_GENERIC_BOT_UA_RE = re.compile(r"(bot|crawler|spider|scraper)", re.IGNORECASE)

# 路由段合法字符：以字母/数字/下划线/中文开头，后续可含点与短横线。
# 只用于挡掉明显的扫描路径，不改变真实 slug 的解析规则。
# 长度上限放宽到 1024：中文标题经 slugify 转拼音后可能远超 128 个字符
# （例如 30 字标题约 146 字符），过长上限只用于挡住异常超长路径。
_SLUG_RE = re.compile(r"^[^\W.][\w.\-]{0,1023}$", re.UNICODE)

# 扫描器常用的无价值后缀；正常站点页面与订阅入口不会出现这些后缀。
_SCANNER_PATH_SUFFIXES = (
    ".php",
    ".php3",
    ".php4",
    ".php5",
    ".phtml",
    ".asp",
    ".aspx",
    ".ashx",
    ".asmx",
    ".jsp",
    ".jspx",
    ".cgi",
    ".cfm",
    ".action",
    ".do",
)

# 扫描器高频探测路径前缀。
_SCANNER_PATH_PREFIXES = (
    "/.env",
    "/.git",
    "/.svn",
    "/.hg",
    "/.aws",
    "/.ssh",
    "/.htaccess",
    "/.htpasswd",
    "/.ds_store",
    "/wp-admin",
    "/wp-login",
    "/wp-content",
    "/wp-includes",
    "/wp-json",
    "/xmlrpc.php",
    "/phpmyadmin",
    "/adminer",
    "/cgi-bin",
    "/vendor/phpunit",
    "/actuator",
    "/server-status",
    "/server-info",
    "/backup",
    "/db.php",
    "/shell.php",
    "/eval-stdin.php",
    "/config.json",
    "/composer.json",
    "/package.json",
    "/yarn.lock",
    "/.well-known/../",
)

# 合法路径白名单：先于扫描路径规则判断。
_ALLOWED_PATH_PREFIXES = (
    "/static/",
    "/media/",
    "/api/",
    "/.well-known/",
)

_ALLOWED_EXACT_PATHS = frozenset({
    "/robots.txt",
    "/ads.txt",
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/feed",
    "/feed.xml",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/favicon.ico",
})

# 只豁免 UA 拦截，不豁免扫描路径判定：站点必须能把 Disallow 规则送达被拉黑的
# 爬虫，否则拉黑只剩「不告知地拒绝」。按最小必要原则只放行 robots.txt：
# sitemap*.xml 会一次性交出全站 URL 清单，ads.txt 与 feed/rss/atom 属于声明或内容
# 输出，都不对黑名单 UA 开放；白名单中的正规搜索引擎本就不受 UA 拦截影响。
_UA_BLOCK_EXEMPT_PATHS = frozenset({"/robots.txt"})


def is_ua_block_exempt_path(path: str) -> bool:
    """判断路径是否为 UA 拦截豁免的协议入口。"""
    return str(path or "").strip().lower() in _UA_BLOCK_EXEMPT_PATHS


def _record_guard_block(reason: str) -> None:
    """把最外层拦截计入安全维度；统计模块不可用时静默跳过。"""
    try:
        from . import traffic_analytics

        traffic_analytics.record_guard_block(reason)
    except Exception:
        pass


def _read_header(scope: dict, name: bytes) -> str:
    """从 ASGI scope 中读取首个同名请求头并解码为字符串。"""
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            try:
                return value.decode("latin-1")
            except Exception:
                return ""
    return ""


def _is_exempt_path(path: str) -> bool:
    """判断路径是否属于不参与扫描判定的合法入口。"""
    lower_path = path.lower()
    if lower_path in _ALLOWED_EXACT_PATHS:
        return True
    if lower_path.startswith(_ALLOWED_PATH_PREFIXES):
        return True
    # 后台入口由 ADMIN_PATH 配置决定，自身路径不应被扫描规则拦截
    admin_path = str(get_admin_path() or "").strip().lower()
    if admin_path and admin_path != "/" and (
        lower_path == admin_path or lower_path.startswith(admin_path + "/")
    ):
        return True
    return False


def is_scanner_path(path: str) -> bool:
    """判断路径是否为典型的扫描器探测路径。"""
    lower_path = str(path or "/").lower()
    # 路径穿越不区分入口，一律拦截
    if ".." in lower_path:
        return True
    if _is_exempt_path(lower_path):
        return False
    if lower_path.endswith(_SCANNER_PATH_SUFFIXES):
        return True
    return lower_path.startswith(_SCANNER_PATH_PREFIXES)


def is_reasonable_slug(value: str) -> bool:
    """廉价判断路由段是否可能是真实 slug，避免扫描路径进入数据库查询。"""
    return bool(_SLUG_RE.fullmatch(str(value or "")))


def is_blocked_user_agent(user_agent: str) -> bool:
    """判断 UA 是否属于应拦截的垃圾爬虫。

    正则兜底对正常浏览器 UA 不会命中；白名单先命中则直接放行。
    """
    ua = str(user_agent or "").strip().lower()
    if not ua:
        return True
    if any(token in ua for token in _ALLOWED_UA_TOKENS):
        return False
    # 站点侧 UA 例外（例如 CUBOT 等手机品牌裸 UA），在拦截规则之前放行
    if any(token in ua for token in (getattr(settings, "BOT_BLOCK_UA_ALLOWLIST", None) or ())):
        return False
    if any(token in ua for token in _BLOCKED_UA_TOKENS):
        return True
    return bool(_GENERIC_BOT_UA_RE.search(ua))


_GLOBAL_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)

# 后台页面禁止被第三方页面嵌套，避免点击劫持；前台保持可嵌入。
_ADMIN_FRAME_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"content-security-policy", b"frame-ancestors 'self'"),
)


def _is_https_request(scope: dict) -> bool:
    forwarded_proto = _read_header(scope, b"x-forwarded-proto").strip().lower()
    if forwarded_proto:
        return forwarded_proto.split(",")[0].strip() == "https"
    return str(scope.get("scheme") or "").lower() == "https"


def _is_admin_scope_path(path: str) -> bool:
    admin_path = str(get_admin_path() or "").strip().lower()
    lower_path = str(path or "").lower()
    if not admin_path or admin_path == "/":
        return False
    return lower_path == admin_path or lower_path.startswith(admin_path + "/")


def _apply_security_headers(message: dict, scope: dict) -> dict:
    """给响应追加基础安全头；已有同名头时以业务响应为准。"""
    if message.get("type") != "http.response.start":
        return message

    headers = list(message.get("headers") or [])
    existing = {key.lower() for key, _ in headers}
    extra: list[tuple[bytes, bytes]] = []

    for key, value in _GLOBAL_SECURITY_HEADERS:
        if key not in existing:
            extra.append((key, value))

    if _is_admin_scope_path(scope.get("path") or "/"):
        for key, value in _ADMIN_FRAME_HEADERS:
            if key not in existing:
                extra.append((key, value))

    if _is_https_request(scope) and b"strict-transport-security" not in existing:
        extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))

    if extra:
        message = {**message, "headers": headers + extra}
    return message


async def _send_plain(send, status_code: int, body: bytes, headers: Iterable[tuple[bytes, bytes]] = ()) -> None:
    """发送最小化纯文本响应，不经过任何业务中间件。"""
    await send({
        "type": "http.response.start",
        "status": status_code,
        "headers": [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"cache-control", b"no-store"),
            *headers,
        ],
    })
    await send({"type": "http.response.body", "body": body})


class BotBlockMiddleware:
    """最外层垃圾请求拦截：不建会话、不查数据库、不写统计。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 统一给所有 HTTP 响应补充安全头（含静态资源与拦截响应）
        async def send_with_headers(message):
            await send(_apply_security_headers(message, scope))

        if not getattr(settings, "BOT_BLOCK_ENABLED", True):
            await self.app(scope, receive, send_with_headers)
            return

        path = str(scope.get("path") or "/")

        if is_scanner_path(path):
            _record_guard_block("扫描路径 404")
            await _send_plain(send_with_headers, 404, "资源不存在".encode("utf-8"))
            return

        if not is_ua_block_exempt_path(path) and is_blocked_user_agent(
            _read_header(scope, b"user-agent")
        ):
            _record_guard_block("UA 拦截 403")
            await _send_plain(send_with_headers, 403, "禁止访问".encode("utf-8"))
            return

        await self.app(scope, receive, send_with_headers)
