"""访问请求分类器

纯函数实现，不依赖数据库与 Request 对象，便于单测和复用：
1. 互斥主分类：可疑 > 爬虫 > HTMX > API/Feed > 后台 > 有效页面浏览 > 其他
2. 有效 PV 只统计 GET + 200 + text/html 且不属于以上任何一类
3. 来源只统计有效 PV，只保留 host，不保存完整 URL 与 query
4. 可疑评分用于异常来源识别，仅观察不自动封禁
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

CATEGORY_PAGE_VIEW = "page_view"
CATEGORY_BOT = "bot"
CATEGORY_SUSPICIOUS = "suspicious"
CATEGORY_ADMIN = "admin"
CATEGORY_API = "api"
CATEGORY_HTMX = "htmx"
CATEGORY_OTHER = "other"

SOURCE_DIRECT = "direct"
SOURCE_INTERNAL = "internal"
SOURCE_SEARCH = "search"
SOURCE_SOCIAL = "social"
SOURCE_EXTERNAL = "external"

SENSITIVE_PATH_PREFIXES = (
    "/.env",
    "/.git",
    "/.svn",
    "/.aws",
    "/.ssh",
    "/.htaccess",
    "/wp-admin",
    "/wp-login.php",
    "/wp-content",
    "/wp-includes",
    "/xmlrpc.php",
    "/phpmyadmin",
    "/administrator",
    "/cgi-bin",
    "/vendor/phpunit",
    "/actuator",
    "/server-status",
    "/config.php",
    "/backup",
    "/db.php",
    "/shell.php",
    "/eval-stdin.php",
)

SCANNER_UA_TOKENS = (
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
)

# 顺序很关键：先匹配具体爬虫，最后才是泛化的 bot/spider 兜底
_BOT_SIGNATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Googlebot", ("googlebot", "google-inspectiontool")),
    ("Bingbot", ("bingbot", "msnbot")),
    ("Baidu Spider", ("baiduspider",)),
    ("YandexBot", ("yandexbot",)),
    ("DuckDuckBot", ("duckduckbot",)),
    ("Sogou Spider", ("sogou",)),
    ("360Spider", ("360spider", "haosouspider")),
    ("Applebot", ("applebot",)),
    ("GPTBot", ("gptbot",)),
    ("OAI-SearchBot", ("oai-searchbot",)),
    ("ChatGPT-User", ("chatgpt-user",)),
    ("ClaudeBot", ("claudebot", "anthropic-ai")),
    ("PerplexityBot", ("perplexitybot",)),
    ("CCBot", ("ccbot",)),
    ("Google-Extended", ("google-extended",)),
    ("Bytespider", ("bytespider",)),
    ("Amazonbot", ("amazonbot",)),
    ("AhrefsBot", ("ahrefsbot",)),
    ("SemrushBot", ("semrushbot",)),
    ("MJ12bot", ("mj12bot",)),
    ("DotBot", ("dotbot",)),
    ("PetalBot", ("petalbot",)),
    ("FacebookBot", ("facebookexternalhit", "facebookbot")),
    ("Twitterbot", ("twitterbot",)),
    ("LinkedInBot", ("linkedinbot",)),
    ("TelegramBot", ("telegrambot",)),
    ("Discordbot", ("discordbot",)),
    ("Slackbot", ("slackbot",)),
    ("curl", ("curl/",)),
    ("Wget", ("wget",)),
    ("Python 脚本", ("python-requests", "python-urllib", "aiohttp")),
    ("Go-http-client", ("go-http-client",)),
    ("无头浏览器", ("headlesschrome", "phantomjs", "puppeteer", "playwright")),
    ("Java 客户端", ("java/", "apache-httpclient")),
    ("Scrapy", ("scrapy",)),
    ("Generic Bot", ("bot", "spider", "crawler", "crawl", "slurp")),
)

_SEARCH_ENGINE_HOST_SUFFIXES = (
    "google.com",
    "google.com.hk",
    "google.co.jp",
    "google.co.uk",
    "bing.com",
    "baidu.com",
    "yandex.com",
    "yandex.ru",
    "duckduckgo.com",
    "sogou.com",
    "so.com",
    "sm.cn",
    "search.yahoo.com",
    "ecosia.org",
    "startpage.com",
)

_SOCIAL_HOST_SUFFIXES = (
    "weibo.com",
    "weibo.cn",
    "zhihu.com",
    "douban.com",
    "tieba.baidu.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "telegram.org",
    "t.me",
    "linkedin.com",
    "youtube.com",
    "bilibili.com",
    "tiktok.com",
    "mastodon.social",
)

_FEED_PATHS = {
    "/feed",
    "/feed.xml",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/robots.txt",
}

_UTM_SOURCE_CLEAN_RE = re.compile(r"[^a-z0-9._-]+")


@dataclass(frozen=True)
class TrafficClassification:
    """单次请求的分类结果。"""

    category: str
    page_view: bool
    bot_name: str
    suspicious_score: int
    suspicious_reason: str
    source_type: str
    referer_host: str
    utm_source: str
    path: str


def normalize_admin_path(admin_path: str | None) -> str:
    """把后台路径规范化为不带尾斜杠的前缀；根路径返回空串。"""
    value = "/" + str(admin_path or "").strip().strip("/")
    return "" if value == "/" else value


def normalize_path(path: str | None, max_length: int = 512) -> str:
    """只保留 path：去掉 query/fragment、统一前导斜杠、去尾部斜杠。"""
    value = str(path or "/").split("?", 1)[0].split("#", 1)[0].strip()
    if not value:
        value = "/"
    if not value.startswith("/"):
        value = "/" + value
    if len(value) > 1:
        value = value.rstrip("/") or "/"
    return value[:max_length]


def normalize_site_host(host: str | None) -> str:
    """从 Host / Referer 中提取小写主机名，去掉端口与认证信息。"""
    raw = str(host or "").strip().lower()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    return (parsed.hostname or "").lower()


def match_bot(user_agent: str | None) -> str:
    """按 UA token 匹配爬虫，返回归一化标签；未匹配返回空串。"""
    ua = str(user_agent or "").strip().lower()
    if not ua:
        return ""
    for label, tokens in _BOT_SIGNATURES:
        if any(token in ua for token in tokens):
            return label
    return ""


def _match_scanner_ua(user_agent: str) -> str | None:
    ua = str(user_agent or "").strip().lower()
    if not ua:
        return None
    for token in SCANNER_UA_TOKENS:
        if token in ua:
            return token
    return None


def _is_under_admin(path: str, admin_prefix: str) -> bool:
    if not admin_prefix:
        return False
    return path == admin_prefix or path.startswith(admin_prefix + "/")


def _is_sensitive_path(path: str, admin_prefix: str) -> bool:
    lower_path = path.lower()
    if _is_under_admin(lower_path, admin_prefix):
        # 站点自身的后台路径不按敏感路径加分，避免误伤自定义后台
        return False
    return any(lower_path.startswith(prefix) for prefix in SENSITIVE_PATH_PREFIXES)


def _is_api_path(path: str) -> bool:
    lower_path = path.lower()
    if lower_path == "/api" or lower_path.startswith("/api/"):
        return True
    if lower_path in _FEED_PATHS:
        return True
    return lower_path.startswith(("/feed/", "/rss/", "/atom/", "/sitemap"))


def _host_matches(host: str, suffixes: tuple[str, ...]) -> bool:
    return any(host == suffix or host.endswith("." + suffix) for suffix in suffixes)


def classify_source(referer: str | None, site_host: str | None) -> tuple[str, str]:
    """把 Referer 归类为来源类型，并返回只含 host 的值。"""
    raw = str(referer or "").strip()
    if not raw:
        return SOURCE_DIRECT, ""

    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        return SOURCE_EXTERNAL, ""
    host = (parsed.hostname or "").lower()
    if not host:
        return SOURCE_EXTERNAL, ""

    normalized_site = normalize_site_host(site_host)
    if normalized_site and (
        host == normalized_site
        or host == f"www.{normalized_site}"
        or normalized_site == f"www.{host}"
    ):
        return SOURCE_INTERNAL, host
    if _host_matches(host, _SEARCH_ENGINE_HOST_SUFFIXES):
        return SOURCE_SEARCH, host
    if _host_matches(host, _SOCIAL_HOST_SUFFIXES):
        return SOURCE_SOCIAL, host
    return SOURCE_EXTERNAL, host


def normalize_utm_source(query_string: str | None) -> str:
    """提取并清洗 utm_source，限制为 64 字符的 [a-z0-9._-]。"""
    raw_query = str(query_string or "").strip()
    if not raw_query:
        return ""
    try:
        values = parse_qs(raw_query, keep_blank_values=False).get("utm_source") or []
    except Exception:
        return ""
    if not values:
        return ""
    cleaned = _UTM_SOURCE_CLEAN_RE.sub("", str(values[0]).strip().lower())
    return cleaned[:64]


def classify_request(
    *,
    path: str | None,
    method: str | None,
    status_code: int,
    content_type: str | None = "",
    user_agent: str | None = "",
    referer: str | None = "",
    query_string: str | None = "",
    site_host: str | None = "",
    admin_path: str | None = "",
    is_admin: bool = False,
    is_htmx_request: bool = False,
    requests_in_minute: int = 0,
) -> TrafficClassification:
    """对单次请求做互斥分类。

    requests_in_minute 由调用方根据缓冲中的单 IP 分钟计数提供，
    超过 60 次/分钟会给可疑评分 +2。
    """
    normalized_path = normalize_path(path)
    normalized_method = str(method or "GET").strip().upper()
    admin_prefix = normalize_admin_path(admin_path).lower()
    lower_path = normalized_path.lower()

    bot_name = match_bot(user_agent)
    scanner_token = _match_scanner_ua(str(user_agent or ""))

    suspicious_score = 0
    reasons: list[str] = []

    is_sensitive = _is_sensitive_path(normalized_path, admin_prefix)
    if is_sensitive:
        suspicious_score += 3
        reasons.append("敏感路径")
    if scanner_token:
        suspicious_score += 3
        reasons.append("扫描器 UA")
    if int(requests_in_minute or 0) > 60:
        suspicious_score += 2
        reasons.append("高频访问")
    if status_code in {401, 403, 429} and not is_sensitive:
        suspicious_score += 1
        reasons.append("拒绝状态码")
    if normalized_method not in {"GET", "HEAD", "POST"}:
        suspicious_score += 1
        reasons.append("非常规方法")

    lowered_content_type = str(content_type or "").lower()

    # 主分类优先级：可疑 > 爬虫 > HTMX > API > 后台 > 有效页面 > 其他
    if suspicious_score >= 2:
        category = CATEGORY_SUSPICIOUS
    elif bot_name:
        category = CATEGORY_BOT
    elif is_htmx_request:
        category = CATEGORY_HTMX
    elif _is_api_path(normalized_path):
        category = CATEGORY_API
    elif is_admin or _is_under_admin(lower_path, admin_prefix):
        category = CATEGORY_ADMIN
    elif (
        normalized_method == "GET"
        and status_code == 200
        and lowered_content_type.startswith("text/html")
    ):
        category = CATEGORY_PAGE_VIEW
    else:
        category = CATEGORY_OTHER

    page_view = category == CATEGORY_PAGE_VIEW
    if page_view:
        source_type, referer_host = classify_source(referer, site_host)
        utm_source = normalize_utm_source(query_string)
    else:
        source_type, referer_host, utm_source = "", "", ""

    return TrafficClassification(
        category=category,
        page_view=page_view,
        bot_name=bot_name,
        suspicious_score=suspicious_score,
        suspicious_reason="、".join(reasons)[:100],
        source_type=source_type,
        referer_host=referer_host[:255],
        utm_source=utm_source,
        path=normalized_path,
    )

