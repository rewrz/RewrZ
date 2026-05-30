from rewrz import main as main_module
from pathlib import Path
from fastapi.testclient import TestClient
from rewrz.api import (
    auth,
    categories,
    comments,
    data_import_export,
    comment_settings,
    media,
    media_settings,
    posts,
    search,
    settings,
    tags,
    themes,
)
from rewrz.core.config import settings as app_settings


def _paths(router):
    return {getattr(route, "path", "") for route in router.routes}


def _ensure_admin_routes_registered():
    if not main_module.ADMIN_ROUTES_REGISTERED:
        main_module.register_admin_routes()
        main_module.ADMIN_ROUTES_REGISTERED = True


def test_search_api_has_v1_and_legacy_paths():
    paths = _paths(search.router)
    assert "/api/v1/search" in paths
    assert "/api/search" in paths
    assert "/api/v1/search/suggestions" in paths
    assert "/api/search/suggestions" in paths


def test_auth_api_has_v1_and_legacy_status_paths():
    paths = _paths(auth.router)
    assert "/api/v1/auth/status" in paths
    assert "/api/auth/status" in paths


def test_category_api_has_v1_and_legacy_paths():
    paths = _paths(categories.router)
    assert "/api/v1/categories/" in paths
    assert "/api/v1/categories/bulk-action" in paths
    assert "/api/v1/categories/{category_id}" in paths


def test_tag_api_has_v1_and_legacy_paths():
    paths = _paths(tags.router)
    assert "/api/v1/tags/" in paths
    assert "/api/v1/tags/bulk-action" in paths
    assert "/api/v1/tags/{tag_id}" in paths


def test_comment_admin_actions_have_v1_paths():
    paths = _paths(comments.router)
    assert "/api/v1/comments/{comment_id}/approve" in paths
    assert "/api/v1/comments/{comment_id}" in paths
    assert "/api/v1/comments/bulk-action" in paths
    assert "/api/v1/comments/{comment_id}/reply" in paths


def test_comment_bulk_action_route_is_not_shadowed_by_create_comment_route():
    client = TestClient(main_module.app)
    response = client.post("/api/v1/comments/bulk-action")
    # If bulk route is shadowed by /api/v1/comments/{post_id}, this becomes 422.
    assert response.status_code != 422


def test_data_management_api_has_v1_and_legacy_paths():
    paths = _paths(data_import_export.router)
    assert "/api/v1/export/json" in paths
    assert "/api/export/json" in paths
    assert "/api/v1/export/backup" in paths
    assert "/api/export/backup" in paths
    assert "/api/v1/import/wordpress" in paths
    assert "/api/import/wordpress" in paths
    assert "/api/v1/import/wordpress/options" in paths
    assert "/api/import/wordpress/options" in paths
    assert "/api/v1/import/rewrz" in paths
    assert "/api/import/rewrz" in paths
    assert "/api/v1/import/backup" in paths
    assert "/api/import/backup" in paths
    assert "/api/v1/data/stats" in paths
    assert "/api/data/stats" in paths


def test_theme_api_has_v1_and_legacy_paths():
    paths = _paths(themes.router)
    assert "/api/v1/theme/current" in paths
    assert "/api/theme/current" in paths
    assert "/api/v1/theme/variables.css" in paths
    assert "/api/theme/variables.css" in paths
    assert "/api/v1/theme/update" in paths
    assert "/api/theme/update" in paths
    assert "/api/v1/atmosphere/update" in paths
    assert "/api/atmosphere/update" in paths
    assert "/api/v1/theme/sync" in paths
    assert "/api/theme/sync" in paths
    assert "/api/v1/admin/themes/background" in paths
    assert "/api/admin/themes/background" in paths


def test_settings_api_has_v1_and_legacy_paths():
    paths = _paths(settings.router)
    assert "/api/v1/update-admin-path" in paths
    assert "/api/update-admin-path" in paths


def test_media_api_has_v1_and_legacy_paths():
    paths = _paths(media.router)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    assert f"{admin_prefix}/api/v1/media" in paths
    assert f"{admin_prefix}/api/v1/media/{{media_id}}" in paths
    assert f"{admin_prefix}/api/v1/media/bulk-delete" in paths
    assert f"{admin_prefix}/api/media" not in paths
    assert f"{admin_prefix}/api/media/{{media_id}}" not in paths
    assert f"{admin_prefix}/api/media/bulk-delete" not in paths


def test_media_settings_api_has_v1_and_legacy_paths():
    paths = _paths(media_settings.router)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    assert f"{admin_prefix}/api/v1/media/settings" in paths
    assert f"{admin_prefix}/api/v1/media/settings/current" in paths


def test_comment_settings_api_has_v1_and_legacy_paths():
    paths = _paths(comment_settings.router)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    assert f"{admin_prefix}/api/v1/comments/settings" in paths
    assert f"{admin_prefix}/api/v1/comments/test-akismet" in paths


def test_posts_api_has_v1_and_legacy_paths():
    paths = _paths(posts.router)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    assert "/api/v1/posts/quick" in paths
    assert "/api/posts/quick" in paths
    assert "/api/v1/posts/quick/media" in paths
    assert "/api/posts/quick/media" in paths
    assert f"{admin_prefix}/api/v1/posts/{{post_id}}" in paths
    assert f"{admin_prefix}/api/v1/posts/batch-publish" in paths
    assert f"{admin_prefix}/api/v1/posts/batch-draft" in paths
    assert f"{admin_prefix}/api/v1/posts/batch-delete" in paths
    assert f"{admin_prefix}/api/v1/pages/{{page_id}}" in paths
    assert f"{admin_prefix}/api/posts/{{post_id}}" not in paths
    assert f"{admin_prefix}/api/posts/batch-publish" not in paths
    assert f"{admin_prefix}/api/posts/batch-draft" not in paths
    assert f"{admin_prefix}/api/posts/batch-delete" not in paths
    assert f"{admin_prefix}/api/pages/{{page_id}}" not in paths


def test_anniversary_and_theme_schedule_have_v1_prefix_routes():
    app_paths = _paths(main_module.app)
    assert "/api/v1/anniversary-mode/current" in app_paths
    assert "/api/anniversary-mode/current" in app_paths
    assert "/api/v1/custom-theme" in app_paths
    assert "/api/custom-theme" in app_paths
    assert "/api/v1/theme-schedule/current" in app_paths
    assert "/api/theme-schedule/current" in app_paths


def test_dynamic_admin_api_routes_have_v1_aliases():
    _ensure_admin_routes_registered()
    app_paths = _paths(main_module.app)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    assert f"{admin_prefix}/api/v1/update-admin-path" in app_paths
    assert f"{admin_prefix}/api/update-admin-path" in app_paths
    assert f"{admin_prefix}/api/v1/categories/options" in app_paths
    assert f"{admin_prefix}/api/v1/anniversary-mode/save" in app_paths
    assert f"{admin_prefix}/api/v1/theme-schedule/save" in app_paths
    assert f"{admin_prefix}/api/v1/theme-schedule/clear" in app_paths
    assert f"{admin_prefix}/api/v1/admin/themes/background" in app_paths
    assert f"{admin_prefix}/api/v1/system-info" in app_paths
    assert f"{admin_prefix}/api/v1/dashboard/stats" in app_paths
    assert f"{admin_prefix}/api/v1/dashboard/site-health" in app_paths
    assert f"{admin_prefix}/api/v1/dashboard/quick-draft" in app_paths
    assert f"{admin_prefix}/api/categories/options" not in app_paths
    assert f"{admin_prefix}/api/system-info" not in app_paths
    assert f"{admin_prefix}/api/system/info" not in app_paths
    assert f"{admin_prefix}/api/dashboard/stats" not in app_paths
    assert f"{admin_prefix}/api/dashboard/site-health" not in app_paths
    assert f"{admin_prefix}/api/dashboard/quick-draft" not in app_paths


def test_external_api_and_frontend_public_api_do_not_expose_admin_path():
    _ensure_admin_routes_registered()
    app_paths = _paths(main_module.app)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    assert "/api/external/v1/posts" in app_paths
    assert f"{admin_prefix}/api/external/v1/posts" not in app_paths
    assert "/api/v1/posts/quick" in app_paths
    assert f"{admin_prefix}/api/v1/posts/quick" not in app_paths
    assert "/api/v1/theme/sync" in app_paths
    assert f"{admin_prefix}/api/v1/theme/sync" not in app_paths


def test_public_app_does_not_expose_admin_only_theme_write_routes():
    app_paths = _paths(main_module.app)
    assert "/api/v1/anniversary-mode/save" not in app_paths
    assert "/api/anniversary-mode/save" not in app_paths
    assert "/api/v1/theme-schedule/save" not in app_paths
    assert "/api/theme-schedule/save" not in app_paths
    assert "/api/v1/theme-schedule/clear" not in app_paths
    assert "/api/theme-schedule/clear" not in app_paths


def test_no_conflicting_top_level_format_alias_routes():
    app_paths = _paths(main_module.app)
    # These aliases conflict with /{page_slug}. Keep only /formats/{format_slug}.
    assert "/photos" not in app_paths
    assert "/weibo" not in app_paths
    assert "/video" not in app_paths
    assert "/music" not in app_paths
    assert "/formats/{format_slug}" in app_paths
    # Media aggregate uses archives prefix to avoid collision with /media static mount.
    assert "/archives/media/{media_slug}" in app_paths


def test_docs_endpoints_are_disabled_for_security():
    assert main_module.app.docs_url is None
    assert main_module.app.redoc_url is None
    assert main_module.app.openapi_url is None


def test_installer_routes_redirect_home_after_installation(monkeypatch):
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: True),
    )
    client = TestClient(main_module.app)

    for path in ("/installer", "/installer/check-environment", "/installer/step/1"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code in (302, 303, 307, 308)
        assert response.headers.get("location") == "/"


def test_public_templates_do_not_hardcode_admin_entrypoint():
    template_root = Path("rewrz/templates")
    excluded_dirs = {"admin", "installer"}

    for template_path in template_root.rglob("*.html"):
        if any(part in excluded_dirs for part in template_path.parts):
            continue
        content = template_path.read_text(encoding="utf-8")
        assert "/admin" not in content, f"Unexpected public admin path in {template_path}"


def test_public_missing_page_does_not_redirect_to_admin_login():
    client = TestClient(main_module.app)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    response = client.get("/this-page-should-not-exist", follow_redirects=False)
    assert response.status_code == 404
    assert response.headers.get("location") is None
    assert admin_prefix not in response.text


def test_public_navigation_uses_archives_category_routes():
    public_templates = [
        Path("rewrz/templates/base.html"),
        Path("rewrz/templates/admin/categories_list.html"),
    ]
    for template_path in public_templates:
        content = template_path.read_text(encoding="utf-8")
        assert "/category/" not in content
        assert "/archives/by-category/" in content
