from __future__ import annotations

import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

from rewrz import main as main_module
from rewrz.core.config import settings as app_settings
from rewrz.core.database import get_db
from rewrz.core.security import get_current_user
from rewrz.models.post import Post
from rewrz.models.setting import Setting
from rewrz.models.user import User as DbUser


def _set_installation_complete(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: value),
    )


def _ensure_admin_routes_registered() -> None:
    if not main_module.ADMIN_ROUTES_REGISTERED:
        main_module.register_admin_routes()
        main_module.ADMIN_ROUTES_REGISTERED = True


def _seed_admin_basics(db) -> DbUser:
    user = db.query(DbUser).filter(DbUser.id == 1).first()
    if user is None:
        user = DbUser(
            id=1,
            username="admin",
            hashed_password="hashed",
            email="admin@example.com",
            is_active=True,
            role="super_admin",
            use_gravatar="auto",
            display_name="管理员",
        )
        db.add(user)

    existing_keys = {item.key for item in db.query(Setting).all()}
    default_settings = {
        "site_title": {"value": "RewrZ Test"},
        "admin_email": {"value": "admin@example.com"},
        "site_url": {"value": "https://example.com"},
        "smtp_port": {"value": 587},
    }
    for key, value in default_settings.items():
        if key not in existing_keys:
            db.add(Setting(key=key, value=value, description=f"测试设置：{key}"))

    db.commit()
    db.refresh(user)
    return user


def _login_user_override() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        username="admin",
        email="admin@example.com",
        role="super_admin",
        is_active=True,
        use_gravatar="auto",
    )


def _build_admin_client(test_db, monkeypatch) -> TestClient:
    _set_installation_complete(monkeypatch, True)
    _ensure_admin_routes_registered()
    _seed_admin_basics(test_db)
    main_module.app.dependency_overrides[get_db] = lambda: test_db
    main_module.app.dependency_overrides[get_current_user] = _login_user_override
    return TestClient(main_module.app)


def _extract_csrf_token(response_text: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response_text)
    assert match is not None, "页面中未找到 CSRF 令牌"
    return match.group(1)


def test_top_level_admin_html_pages_are_not_public(monkeypatch):
    _set_installation_complete(monkeypatch, True)
    client = TestClient(main_module.app)

    for path in ("/settings", "/error-settings"):
        response = client.get(path)
        assert response.status_code == 404, path


def test_sidebar_admin_pages_exist_under_dynamic_admin_path(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        for path in (
            f"{admin_prefix}/dashboard",
            f"{admin_prefix}/settings",
            f"{admin_prefix}/users",
            f"{admin_prefix}/comment-settings",
            f"{admin_prefix}/data-management",
            f"{admin_prefix}/security-center",
            f"{admin_prefix}/error-settings",
            f"{admin_prefix}/system-info",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
    finally:
        main_module.app.dependency_overrides.clear()


def test_settings_page_requires_csrf_for_submit_when_logged_in(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        response = client.post(
            f"{admin_prefix}/settings",
            data={
                "site_title": "新站点标题",
                "tagline": "新的副标题",
                "site_url": "https://example.com",
                "admin_email": "admin@example.com",
                "copyright_info": "Copyright",
                "social_links_json": "[]",
                "anniversaries_json": "[]",
            },
        )
        assert response.status_code == 422
    finally:
        main_module.app.dependency_overrides.clear()


def test_settings_page_can_save_and_re_render_saved_value(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        page_response = client.get(f"{admin_prefix}/settings")
        assert page_response.status_code == 200
        csrf_token = _extract_csrf_token(page_response.text)

        response = client.post(
            f"{admin_prefix}/settings",
            data={
                "site_title": "新的站点标题",
                "tagline": "新的副标题",
                "site_url": "https://example.com",
                "admin_email": "admin@example.com",
                "public_contact_email": "contact@example.com",
                "smtp_host": "smtp.example.com",
                "smtp_port": "465",
                "smtp_username": "mailer@example.com",
                "smtp_password": "secret-pass",
                "smtp_from_email": "noreply@example.com",
                "smtp_use_ssl": "true",
                "copyright_info": "Copyright",
                "custom_footer_text": "<strong>页脚说明</strong>",
                "social_links_json": "[]",
                "anniversaries_json": "[]",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        assert "新的站点标题" in response.text
        assert "页脚说明" in response.text
        assert "smtp.example.com" in response.text

        response = client.get(f"{admin_prefix}/settings")
        assert response.status_code == 200
        assert "新的站点标题" in response.text
        assert "contact@example.com" in response.text
        assert "smtp.example.com" in response.text
        assert 'value="465"' in response.text
    finally:
        main_module.app.dependency_overrides.clear()


def test_settings_page_normalizes_local_asset_urls_on_save(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        page_response = client.get(f"{admin_prefix}/settings")
        assert page_response.status_code == 200
        csrf_token = _extract_csrf_token(page_response.text)

        response = client.post(
            f"{admin_prefix}/settings",
            data={
                "site_title": "新的站点标题",
                "tagline": "新的副标题",
                "site_url": "https://example.com",
                "admin_email": "admin@example.com",
                "site_logo_light": "http://127.0.0.1:8000/static/images/logo-light.png",
                "site_logo_dark": "http://localhost:9000/static/images/logo-dark.png",
                "favicon": "http://127.0.0.1:8000/static/favicon.ico",
                "site_cover_url": "http://127.0.0.1:8000/static/images/bg/1.jpg",
                "admin_login_background_image_url": "http://localhost:8123/static/images/admin-bg.jpg",
                "admin_login_background_video_url": "http://127.0.0.1:8000/media/admin-bg.mp4",
                "copyright_info": "Copyright",
                "social_links_json": "[]",
                "anniversaries_json": "[]",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        assert 'value="/static/images/logo-light.png"' in response.text
        assert 'value="/static/images/logo-dark.png"' in response.text
        assert 'value="/static/favicon.ico"' in response.text
        assert 'value="/static/images/bg/1.jpg"' in response.text
        assert 'value="/static/images/admin-bg.jpg"' in response.text
        assert 'value="/media/admin-bg.mp4"' in response.text

        saved_settings = {
            item.key: item.value.get("value")
            for item in test_db.query(Setting).filter(
                Setting.key.in_(
                    [
                        "site_logo_light",
                        "site_logo_dark",
                        "favicon",
                        "site_cover_url",
                        "admin_login_background_image_url",
                        "admin_login_background_video_url",
                    ]
                )
            ).all()
        }
        assert saved_settings["site_logo_light"] == "/static/images/logo-light.png"
        assert saved_settings["site_logo_dark"] == "/static/images/logo-dark.png"
        assert saved_settings["favicon"] == "/static/favicon.ico"
        assert saved_settings["site_cover_url"] == "/static/images/bg/1.jpg"
        assert saved_settings["admin_login_background_image_url"] == "/static/images/admin-bg.jpg"
        assert saved_settings["admin_login_background_video_url"] == "/media/admin-bg.mp4"
    finally:
        main_module.app.dependency_overrides.clear()


def test_settings_page_normalizes_multiline_homepage_background_image_urls_on_save(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        page_response = client.get(f"{admin_prefix}/settings")
        assert page_response.status_code == 200
        csrf_token = _extract_csrf_token(page_response.text)

        raw_backgrounds = "\n".join(
            [
                "http://127.0.0.1:8000/static/images/bg/1.jpg",
                "https://cdn.example.com/images/bg/remote.jpg",
                "http://localhost:8123/media/home/clip.jpg",
            ]
        )
        response = client.post(
            f"{admin_prefix}/settings",
            data={
                "site_title": "新的站点标题",
                "tagline": "新的副标题",
                "site_url": "https://example.com",
                "admin_email": "admin@example.com",
                "homepage_mode": "fullscreen_gallery",
                "homepage_background_image_url": raw_backgrounds,
                "copyright_info": "Copyright",
                "social_links_json": "[]",
                "anniversaries_json": "[]",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        assert "/static/images/bg/1.jpg" in response.text
        assert "https://cdn.example.com/images/bg/remote.jpg" in response.text
        assert "/media/home/clip.jpg" in response.text

        saved_setting = test_db.query(Setting).filter(Setting.key == "homepage_background_image_url").first()
        assert saved_setting is not None
        assert saved_setting.value.get("value") == "\n".join(
            [
                "/static/images/bg/1.jpg",
                "https://cdn.example.com/images/bg/remote.jpg",
                "/media/home/clip.jpg",
            ]
        )
    finally:
        main_module.app.dependency_overrides.clear()


def test_users_page_normalizes_local_cover_urls_on_save(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        page_response = client.get(f"{admin_prefix}/users")
        assert page_response.status_code == 200
        csrf_token = _extract_csrf_token(page_response.text)

        response = client.post(
            f"{admin_prefix}/users",
            data={
                "username": "admin",
                "email": "admin@example.com",
                "display_name": "管理员",
                "bio": "简介",
                "website": "example.com",
                "use_gravatar": "auto",
                "creator_profile_cover_url": "http://127.0.0.1:8000/static/images/covers/article.jpg",
                "creator_profile_micro_cover_url": "http://localhost:9000/static/images/covers/micro.jpg",
                "creator_profile_poem_cover_url": "http://127.0.0.1:8000/media/covers/poem.jpg",
                "creator_profile_headline": "头图说明",
                "creator_profile_article_bio": "文章简介",
                "creator_profile_micro_bio": "微博简介",
                "creator_profile_poem_bio": "诗词简介",
                "creator_profile_location": "上海",
                "creator_profile_motto": "保持收敛",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        assert "个人资料已更新。" in response.text
        assert 'value="/static/images/covers/article.jpg"' in response.text
        assert 'value="/static/images/covers/micro.jpg"' in response.text
        assert 'value="/media/covers/poem.jpg"' in response.text

        saved_settings = {
            item.key: item.value.get("value")
            for item in test_db.query(Setting).filter(
                Setting.key.in_(
                    [
                        "creator_profile_cover_url",
                        "creator_profile_micro_cover_url",
                        "creator_profile_poem_cover_url",
                    ]
                )
            ).all()
        }
        assert saved_settings["creator_profile_cover_url"] == "/static/images/covers/article.jpg"
        assert saved_settings["creator_profile_micro_cover_url"] == "/static/images/covers/micro.jpg"
        assert saved_settings["creator_profile_poem_cover_url"] == "/media/covers/poem.jpg"
    finally:
        main_module.app.dependency_overrides.clear()


def test_error_settings_page_can_save_and_re_render_saved_value(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        page_response = client.get(f"{admin_prefix}/error-settings")
        assert page_response.status_code == 200
        csrf_token = _extract_csrf_token(page_response.text)

        response = client.post(
            f"{admin_prefix}/error-settings",
            data={
                "enable_custom_error_pages": "on",
                "error_page_template": "friendly",
                "custom_error_404_title": "页面走丢了",
                "custom_error_404_message": "请返回首页继续浏览。",
                "custom_error_500_title": "服务器出错了",
                "custom_error_500_message": "请稍后再试。",
                "custom_error_403_title": "这里不开放",
                "custom_error_403_message": "你暂时没有权限访问。",
                "custom_error_400_title": "请求格式不对",
                "custom_error_400_message": "请检查输入内容。",
                "enable_error_caching": "on",
                "error_cache_duration": "600",
                "enable_error_logging": "on",
                "log_level": "WARNING",
                "enable_performance_optimization": "on",
                "related_posts_cache_strategy": "moderate",
                "reading_time_cache_duration": "1800",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        assert "错误处理设置已保存" in response.text
        assert "页面走丢了" in response.text

        response = client.get(f"{admin_prefix}/error-settings")
        assert response.status_code == 200
        assert "页面走丢了" in response.text
        assert "friendly" in response.text
    finally:
        main_module.app.dependency_overrides.clear()


def test_public_article_detail_uses_fallback_title_when_post_title_is_empty(test_db, monkeypatch):
    _set_installation_complete(monkeypatch, True)
    _seed_admin_basics(test_db)
    main_module.app.dependency_overrides[get_db] = lambda: test_db
    client = TestClient(main_module.app)

    try:
        post = Post(
            title="",
            slug="untitled-public-article",
            content_markdown="正文内容",
            content_html="<p>正文内容</p>",
            excerpt="",
            post_type="post",
            status="published",
            visibility="public",
            author_id=1,
        )
        test_db.add(post)
        test_db.commit()
        test_db.refresh(post)

        response = client.get("/article/untitled-public-article")
        assert response.status_code == 200
        heading_match = re.search(
            r'<h1 class="text-3xl md:text-4xl font-bold mb-4 leading-tight">([^<]+)</h1>',
            response.text,
        )
        assert heading_match is not None
        assert "文章" in heading_match.group(1)
        assert "<h1 class=\"text-3xl md:text-4xl font-bold mb-4 leading-tight\"></h1>" not in response.text
    finally:
        main_module.app.dependency_overrides.clear()
