"""垃圾爬虫与扫描路径拦截中间件。

目标：在进入会话、设置、数据库等任何业务逻辑之前，直接拒绝明显无价值的
爬虫与扫描请求，降低带宽与数据库压力。

拦截策略（顺序不可调换）：
1. 白名单优先：正规搜索引擎、社交预览、可用性监控等 UA 一律放行；
2. 黑名单：商业 SEO 抓取、AI 训练抓取、扫描器等已知垃圾 UA 一律 403；
3. 通用兜底：UA 含 bot / crawler / spider / scraper 的请求一律 403；
4. 空 UA 一律 403（正常浏览器与订阅器都会携带 UA）；
5. 扫描路径：PHP/ASP/JSP 等无价值后缀与 wp-admin、.env 等探测路径，
   无论什么 UA 都直接返回 404。

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
    if any(token in ua for token in _BLOCKED_UA_TOKENS):
        return True
    return bool(_GENERIC_BOT_UA_RE.search(ua))


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

        if not getattr(settings, "BOT_BLOCK_ENABLED", True):
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "/")

        if is_scanner_path(path):
            await _send_plain(send, 404, "资源不存在".encode("utf-8"))
            return

        if is_blocked_user_agent(_read_header(scope, b"user-agent")):
            await _send_plain(send, 403, "禁止访问".encode("utf-8"))
            return

        await self.app(scope, receive, send)
