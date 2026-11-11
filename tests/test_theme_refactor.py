import json
import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

from rewrz import main as main_module
from rewrz.api import themes as themes_api
from rewrz.core import effects_engine
from rewrz.core.database import get_db
from rewrz.core.security import create_access_token
from rewrz.crud import setting as crud_setting
from rewrz.crud import user as crud_user
from rewrz.schemas import SettingCreate, UserCreate
from rewrz.schemas.setting import SettingUpdate
from rewrz.models.setting import Setting


def _upsert_setting(test_db, *, key: str, value: dict, description: str, category: str):
    existing = crud_setting.get_setting(test_db, key)
    if existing is None:
        crud_setting.create_setting(
            test_db,
            SettingCreate(
                key=key,
                value=value,
                description=description,
                category=category,
            ),
        )
        return
    crud_setting.update_setting(
        test_db,
        key,
        SettingUpdate(
            value=value,
            description=description,
            category=category,
        ),
    )


def test_resolve_active_theme_prefers_logged_in_user_preference(test_db):
    user = crud_user.create_user(
        test_db,
        UserCreate(username="theme-user", email="theme-user@example.com", password="testpassword"),
    )
    crud_user.set_user_theme_preference(test_db, user.id, theme_preference="galaxy")
    _upsert_setting(
        test_db,
        key="current_theme",
        value={"value": "light"},
        description="当前使用的主题",
        category="theme",
    )

    request = SimpleNamespace(state=SimpleNamespace(authenticated_user=crud_user.get_user(test_db, user.id)))
    resolved = themes_api.resolve_active_theme(test_db, request=request)

    assert resolved["theme_id"] == "galaxy"
    assert resolved["theme_source"] == "user_preference"


def test_theme_sync_returns_new_resolved_effects_shape(test_db):
    user = crud_user.create_user(
        test_db,
        UserCreate(username="sync-user", email="sync-user@example.com", password="testpassword"),
    )
    crud_user.set_user_theme_preference(test_db, user.id, theme_preference="dark")
    _upsert_setting(
        test_db,
        key="current_theme",
        value={"value": "light"},
        description="当前使用的主题",
        category="theme",
    )
    _upsert_setting(
        test_db,
        key=effects_engine.SETTING_MANUAL_OVERRIDE,
        value={"value": {"scene": "memorial", "effects": ["grayscale", "candles"], "enabled": True, "priority": 3000}},
        description="当前手动特效场景",
        category="effects",
    )

    def override_get_db():
        yield test_db

    main_module.app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(main_module.app)
        token = create_access_token({"sub": str(user.id), "username": user.username, "token_version": 1})
        client.cookies.set("access_token", token)
        response = client.get("/api/v1/theme/sync")
        assert response.status_code == 200
        payload = response.json()
        assert payload["theme"] == "dark"
        assert payload["theme_source"] == "user_preference"
        assert "resolved_effects" in payload
        assert payload["resolved_effects"]["scene"] == "memorial"
        assert payload["resolved_effects"]["source"] == "manual"
        assert "grayscale" in payload["resolved_effects"]["effects"]
        assert "candles" in payload["resolved_effects"]["effects"]
        assert payload["background"]["type"] == "none"
    finally:
        main_module.app.dependency_overrides.clear()


def test_check_scheduled_effect_scene_only_reads_new_effects_switch(test_db):
    crud_setting.create_setting(
        test_db,
        SettingCreate(
            key="auto_theme_enabled",
            value={"value": True},
            description="旧键",
            category="theme",
        ),
    )
    crud_setting.create_setting(
        test_db,
        SettingCreate(
            key=effects_engine.SETTING_SCHEDULE_RULES,
            value={"value": {"items": [{"start_date": "2026-06-01", "end_date": "2026-06-30", "atmosphere": "festive", "scene": "festive"}]}},
            description="节日特效调度配置",
            category="effects",
        ),
    )

    resolved = themes_api.check_scheduled_effect_scene(test_db)
    assert resolved is None


def test_public_holiday_catalog_stays_within_target_solar_year():
    catalog = effects_engine.build_public_holiday_catalog(2026)

    assert catalog["year"] == 2026
    assert len(catalog["items"]) == 27
    assert all(str(item["start_at"]).startswith("2026-") for item in catalog["items"])

    items_by_code = {item["code"]: item for item in catalog["items"]}
    assert items_by_code["winter_solstice"]["start_at"] == "2026-12-22"
    assert items_by_code["laba_festival"]["start_at"] == "2026-01-26"
    assert items_by_code["little_new_year"]["start_at"] == "2026-02-10"
    assert items_by_code["new_year_eve"]["start_at"] == "2026-02-16"
    assert "rice_grains" in items_by_code["laba_festival"]["effects"]
    assert "embers" in items_by_code["little_new_year"]["effects"]
    assert "moonlight" in items_by_code["mid_autumn_festival"]["effects"]
    assert "balloons" in items_by_code["childrens_day"]["effects"]
    assert "red_packets" in items_by_code["spring_festival"]["effects"]
    assert "dragon_boats" in items_by_code["dragon_boat_festival"]["effects"]
    assert "paper_charms" in items_by_code["zhongyuan_festival"]["effects"]
    assert "dumplings" in items_by_code["winter_solstice"]["effects"]
    assert "tree_lights" in items_by_code["christmas_day"]["effects"]
    assert "rain" in items_by_code["dragon_heads_raising_day"]["effects"]


def _build_theme_admin_client(test_db, monkeypatch):
    from rewrz.core.security import get_current_user
    from rewrz.models.user import User as DbUser

    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: True),
    )
    if not main_module.ADMIN_ROUTES_REGISTERED:
        main_module.register_admin_routes()
        main_module.ADMIN_ROUTES_REGISTERED = True

    if test_db.query(DbUser).filter(DbUser.id == 1).first() is None:
        test_db.add(
            DbUser(
                id=1,
                username="admin",
                hashed_password="hashed",
                email="admin@example.com",
                is_active=True,
                role="super_admin",
                use_gravatar="auto",
            )
        )
    for key in ("site_title", "site_url"):
        if test_db.query(Setting).filter(Setting.key == key).first() is None:
            test_db.add(Setting(key=key, value={"value": "RewrZ Test"}, description="测试设置"))
    test_db.commit()

    main_module.app.dependency_overrides[get_db] = lambda: test_db
    main_module.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        username="admin",
        email="admin@example.com",
        role="super_admin",
        is_active=True,
        use_gravatar="auto",
    )
    return TestClient(main_module.app)


def test_normalize_background_effects_filters_and_orders():
    assert themes_api.normalize_background_effects(["orbs", "glow", "glow", "不存在的特效", "DIM"]) == ["glow", "dim", "orbs"]
    assert themes_api.normalize_background_effects("blur") == ["blur"]
    assert themes_api.normalize_background_effects(None) == []


def test_background_effects_saved_and_rendered(test_db, monkeypatch):
    from rewrz.core.config import settings as app_settings

    monkeypatch.setattr(themes_api, "verify_csrf_token", lambda request, token: None)
    client = _build_theme_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        response = client.post(
            f"{admin_prefix}/api/v1/admin/themes/background",
            data={
                "background_type": "custom",
                "custom_background_url": "/static/images/covers/home-default.jpg",
                "background_effects": ["glow", "dim", "invalid"],
                "csrf_token": "test-token",
            },
        )
        assert response.status_code == 200
        stored = crud_setting.get_setting(test_db, key="background_image_settings").value["value"]
        assert stored["type"] == "custom"
        assert stored["effects"] == ["glow", "dim"]

        page = client.get(f"{admin_prefix}/themes")
        assert page.status_code == 200
        assert "背景特效滤镜" in page.text
        assert "site-bg-preview" in page.text
        assert "粒子光球" in page.text
        assert 'value="invalid"' not in page.text
        assert "theme-admin-bg-fx" not in page.text

        # 站点背景必须作用于后台所有页面，而不只是主题系统页
        for admin_page_path in ("/themes", "/settings"):
            admin_page = client.get(f"{admin_prefix}{admin_page_path}")
            assert admin_page.status_code == 200
            assert 'data-background-type="custom"' in admin_page.text
            assert 'data-background-url="/static/images/covers/home-default.jpg"' in admin_page.text
            assert "js/theme-background.js" in admin_page.text
            assert 'id="admin-bg-fx"' in admin_page.text
            effects_match = re.search(r"data-background-effects='([^']*)'", admin_page.text)
            assert effects_match is not None
            assert json.loads(effects_match.group(1)) == ["glow", "dim"]

        home = client.get("/")
        assert home.status_code == 200
        assert 'class="site-bg-fx fx-glow fx-dim"' in home.text
    finally:
        main_module.app.dependency_overrides.clear()
