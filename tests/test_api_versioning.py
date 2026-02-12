from rewrz import main as main_module
from pathlib import Path
from fastapi.testclient import TestClient
from rewrz.api import (
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


def test_category_api_has_v1_and_legacy_paths():
    new_paths = _paths(categories.router)
    old_paths = _paths(categories.legacy_router)
    assert "/api/v1/categories/" in new_paths
    assert "/api/v1/categories/{category_id}" in new_paths
    assert "/api/categories/" in old_paths
    assert "/api/categories/{category_id}" in old_paths


def test_tag_api_has_v1_and_legacy_paths():
    new_paths = _paths(tags.router)
    old_paths = _paths(tags.legacy_router)
    assert "/api/v1/tags/" in new_paths
    assert "/api/v1/tags/{tag_id}" in new_paths
    assert "/api/tags/" in old_paths
    assert "/api/tags/{tag_id}" in old_paths


def test_comment_admin_actions_have_v1_paths():
    paths = _paths(comments.router)
    assert "/api/v1/comments/{comment_id}/approve" in paths
    assert "/api/v1/comments/{comment_id}" in paths
    assert "/api/v1/comments/bulk-action" in paths
    assert "/api/v1/comments/{comment_id}/reply" in paths


def test_data_management_api_has_v1_and_legacy_paths():
    paths = _paths(data_import_export.router)
    assert "/api/v1/export/json" in paths
    assert "/api/export/json" in paths
    assert "/api/v1/export/backup" in paths
    assert "/api/export/backup" in paths
    assert "/api/v1/import/wordpress" in paths
    assert "/api/import/wordpress" in paths
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
    assert f"{admin_prefix}/api/media" in paths
    assert f"{admin_prefix}/api/v1/media/{{media_id}}" in paths
    assert f"{admin_prefix}/api/media/{{media_id}}" in paths
    assert f"{admin_prefix}/api/v1/media/bulk-delete" in paths
    assert f"{admin_prefix}/api/media/bulk-delete" in paths


def test_media_settings_api_has_v1_and_legacy_paths():
    paths = _paths(media_settings.router)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    assert f"{admin_prefix}/api/v1/media/settings" in paths
    assert f"{admin_prefix}/api/media/settings" in paths
    assert f"{admin_prefix}/api/v1/media/settings/current" in paths
    assert f"{admin_prefix}/api/media/settings/current" in paths


def test_comment_settings_api_has_v1_and_legacy_paths():
    paths = _paths(comment_settings.router)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    assert f"{admin_prefix}/api/v1/comments/settings" in paths
    assert f"{admin_prefix}/api/comments/settings" in paths
    assert f"{admin_prefix}/api/v1/comments/test-akismet" in paths
    assert f"{admin_prefix}/api/comments/test-akismet" in paths


def test_posts_api_has_v1_and_legacy_paths():
    paths = _paths(posts.router)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    assert f"{admin_prefix}/api/v1/posts/{{post_id}}" in paths
    assert f"{admin_prefix}/api/posts/{{post_id}}" in paths
    assert f"{admin_prefix}/api/v1/posts/batch-publish" in paths
    assert f"{admin_prefix}/api/posts/batch-publish" in paths
    assert f"{admin_prefix}/api/v1/posts/batch-draft" in paths
    assert f"{admin_prefix}/api/posts/batch-draft" in paths
    assert f"{admin_prefix}/api/v1/posts/batch-delete" in paths
    assert f"{admin_prefix}/api/posts/batch-delete" in paths
    assert f"{admin_prefix}/api/v1/pages/{{page_id}}" in paths
    assert f"{admin_prefix}/api/pages/{{page_id}}" in paths


def test_anniversary_and_theme_schedule_have_v1_prefix_routes():
    app_paths = _paths(main_module.app)
    assert "/api/v1/anniversary-mode/current" in app_paths
    assert "/api/anniversary-mode/current" in app_paths
    assert "/api/v1/custom-theme" in app_paths
    assert "/api/custom-theme" in app_paths
    assert "/api/v1/theme-schedule/save" in app_paths
    assert "/api/theme-schedule/save" in app_paths


def test_dynamic_admin_api_routes_have_v1_aliases():
    _ensure_admin_routes_registered()
    app_paths = _paths(main_module.app)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    assert f"{admin_prefix}/api/v1/update-admin-path" in app_paths
    assert f"{admin_prefix}/api/update-admin-path" in app_paths
    assert f"{admin_prefix}/api/v1/system-info" in app_paths
    assert f"{admin_prefix}/api/system-info" in app_paths


def test_no_conflicting_top_level_format_alias_routes():
    app_paths = _paths(main_module.app)
    # These aliases conflict with /{page_slug}. Keep only /formats/{format_slug}.
    assert "/photos" not in app_paths
    assert "/weibo" not in app_paths
    assert "/video" not in app_paths
    assert "/music" not in app_paths
    assert "/formats/{format_slug}" in app_paths


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
