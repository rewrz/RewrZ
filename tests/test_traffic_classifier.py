"""访问分类器单元测试。"""
from __future__ import annotations

from rewrz.core import traffic_classifier as classifier


def test_normalize_path_strips_query_and_trailing_slash():
    assert classifier.normalize_path("/posts/hello/?utm_source=x#top") == "/posts/hello"
    assert classifier.normalize_path("") == "/"
    assert classifier.normalize_path("/") == "/"


def test_normalize_admin_path_variants():
    assert classifier.normalize_admin_path("/admin/") == "/admin"
    assert classifier.normalize_admin_path("panel") == "/panel"
    assert classifier.normalize_admin_path("/") == ""


def test_normal_page_view_counts_source_and_utm():
    result = classifier.classify_request(
        path="/posts/hello/?utm_source=Newsletter",
        method="GET",
        status_code=200,
        content_type="text/html; charset=utf-8",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        referer="https://www.google.com/search?q=rewrz",
        query_string="utm_source=Newsletter",
        site_host="example.com",
        admin_path="/admin",
    )
    assert result.category == classifier.CATEGORY_PAGE_VIEW
    assert result.page_view is True
    assert result.path == "/posts/hello"
    assert result.source_type == classifier.SOURCE_SEARCH
    assert result.referer_host == "www.google.com"
    assert result.utm_source == "newsletter"


def test_internal_referer_is_classified_as_internal():
    result = classifier.classify_request(
        path="/posts/hello",
        method="GET",
        status_code=200,
        content_type="text/html",
        referer="https://www.example.com/posts",
        site_host="example.com",
    )
    assert result.category == classifier.CATEGORY_PAGE_VIEW
    assert result.source_type == classifier.SOURCE_INTERNAL


def test_social_and_external_referers():
    social = classifier.classify_source("https://weibo.com/123", "example.com")
    assert social == (classifier.SOURCE_SOCIAL, "weibo.com")
    external = classifier.classify_source("https://blog.example.net/post", "example.com")
    assert external == (classifier.SOURCE_EXTERNAL, "blog.example.net")
    assert classifier.classify_source("javascript:alert(1)", "example.com") == (
        classifier.SOURCE_EXTERNAL,
        "",
    )


def test_bot_user_agent_is_classified_as_bot():
    result = classifier.classify_request(
        path="/",
        method="GET",
        status_code=200,
        content_type="text/html",
        user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    )
    assert result.category == classifier.CATEGORY_BOT
    assert result.bot_name == "Googlebot"
    assert result.page_view is False
    assert result.source_type == ""


def test_sensitive_path_and_scanner_ua_are_suspicious():
    by_path = classifier.classify_request(
        path="/.env",
        method="GET",
        status_code=404,
        content_type="text/plain",
        user_agent="Mozilla/5.0",
    )
    assert by_path.category == classifier.CATEGORY_SUSPICIOUS
    assert by_path.suspicious_score >= 2
    assert "敏感路径" in by_path.suspicious_reason

    by_ua = classifier.classify_request(
        path="/",
        method="GET",
        status_code=200,
        content_type="text/html",
        user_agent="sqlmap/1.7",
    )
    assert by_ua.category == classifier.CATEGORY_SUSPICIOUS
    assert "扫描器 UA" in by_ua.suspicious_reason


def test_high_frequency_and_rejected_status_add_suspicion():
    high_frequency = classifier.classify_request(
        path="/",
        method="GET",
        status_code=200,
        content_type="text/html",
        user_agent="Mozilla/5.0",
        requests_in_minute=61,
    )
    assert high_frequency.category == classifier.CATEGORY_SUSPICIOUS
    assert "高频访问" in high_frequency.suspicious_reason

    rejected = classifier.classify_request(
        path="/private",
        method="GET",
        status_code=403,
        content_type="text/html",
        user_agent="Mozilla/5.0",
    )
    assert rejected.suspicious_score == 1
    assert rejected.category == classifier.CATEGORY_OTHER

    unusual_method = classifier.classify_request(
        path="/private",
        method="DELETE",
        status_code=403,
        content_type="text/html",
        user_agent="Mozilla/5.0",
    )
    assert unusual_method.suspicious_score == 2
    assert unusual_method.category == classifier.CATEGORY_SUSPICIOUS


def test_htmx_api_feed_and_admin_paths_are_mutually_exclusive():
    htmx = classifier.classify_request(
        path="/posts",
        method="GET",
        status_code=200,
        content_type="text/html",
        is_htmx_request=True,
        is_admin=True,
    )
    assert htmx.category == classifier.CATEGORY_HTMX

    api = classifier.classify_request(
        path="/api/v1/posts",
        method="GET",
        status_code=200,
        content_type="application/json",
    )
    assert api.category == classifier.CATEGORY_API

    feed = classifier.classify_request(
        path="/feed.xml",
        method="GET",
        status_code=200,
        content_type="application/rss+xml",
    )
    assert feed.category == classifier.CATEGORY_API

    admin = classifier.classify_request(
        path="/admin/dashboard",
        method="GET",
        status_code=200,
        content_type="text/html",
        admin_path="/admin",
        is_admin=True,
    )
    assert admin.category == classifier.CATEGORY_ADMIN
    assert admin.page_view is False


def test_custom_admin_path_not_treated_as_sensitive_scan():
    result = classifier.classify_request(
        path="/secret-panel/login",
        method="GET",
        status_code=200,
        content_type="text/html",
        admin_path="/secret-panel",
    )
    assert result.category == classifier.CATEGORY_ADMIN
    assert result.suspicious_score == 0


def test_page_view_requires_get_html_200():
    post = classifier.classify_request(
        path="/submit",
        method="POST",
        status_code=200,
        content_type="text/html",
    )
    assert post.category == classifier.CATEGORY_OTHER
    assert post.page_view is False

    not_html = classifier.classify_request(
        path="/download",
        method="GET",
        status_code=200,
        content_type="application/octet-stream",
    )
    assert not_html.category == classifier.CATEGORY_OTHER

    not_ok = classifier.classify_request(
        path="/missing",
        method="GET",
        status_code=404,
        content_type="text/html",
    )
    assert not_ok.category == classifier.CATEGORY_OTHER


def test_normalize_utm_source_limits_characters_and_length():
    assert classifier.normalize_utm_source("utm_source=AB%20C%21") == "abc"
    assert classifier.normalize_utm_source("foo=bar") == ""
    assert len(classifier.normalize_utm_source("utm_source=" + "a" * 100)) == 64
