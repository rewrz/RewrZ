"""
动态主题系统和氛围引擎 API 模块

提供以下功能：
1. 主题配置管理（浅色/深色/自定义主题）
2. 氛围引擎（节日主题、纪念日主题、特殊活动主题）
3. 主题预设和自定义CSS变量
4. 主题调度和自动切换
"""
import json
import os
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Tuple
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import ensure_admin_user, get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..crud import setting as crud_setting
from ..crud import user as crud_user
from ..schemas import Setting, SettingCreate, SettingUpdate, User

router = APIRouter()

# 预定义主题配置（8种预设主题，含二次元风格）
DEFAULT_THEMES = {
    "light": {
        "name": "云朵白",
        "variables": {
            "--color-primary": "#6366f1",
            "--color-primary-hover": "#4f46e5",
            "--color-secondary": "#475569",
            "--color-background": "#ffffff",
            "--color-background-alt": "#f8fafc",
            "--color-text": "#0f172a",
            "--color-text-light": "#475569",
            "--color-text-muted": "#64748b",
            "--color-border": "#cbd5e1",
            "--color-border-light": "#e2e8f0",
            "--color-card-bg": "#ffffff",
            "--color-card-shadow": "rgba(99, 102, 241, 0.1)",
            "--color-nav-bg": "rgba(255, 255, 255, 0.85)",
            "--color-footer-bg": "#f8fafc",
            "--font-family-base": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-heading": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-decorative": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--backdrop-blur": "blur(12px)"
        }
    },
    "dark": {
        "name": "夜幕蓝",
        "variables": {
            "--color-primary": "#818cf8",
            "--color-primary-hover": "#6366f1",
            "--color-secondary": "#cbd5e1",
            "--color-background": "#0f172a",
            "--color-background-alt": "#1e293b",
            "--color-text": "#f1f5f9",
            "--color-text-light": "#dbe4f0",
            "--color-text-muted": "#94a3b8",
            "--color-border": "#334155",
            "--color-border-light": "#475569",
            "--color-card-bg": "#1e293b",
            "--color-card-shadow": "rgba(129, 140, 248, 0.15)",
            "--color-nav-bg": "rgba(15, 23, 42, 0.85)",
            "--color-footer-bg": "#1e293b",
            "--font-family-base": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-heading": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-decorative": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--backdrop-blur": "blur(12px)"
        }
    },
    "nature": {
        "name": "森林绿",
        "variables": {
            "--color-primary": "#10b981",
            "--color-primary-hover": "#059669",
            "--color-secondary": "#166534",
            "--color-background": "#f0fdf4",
            "--color-background-alt": "#dcfce7",
            "--color-text": "#14532d",
            "--color-text-light": "#166534",
            "--color-text-muted": "#15803d",
            "--color-border": "#86efac",
            "--color-border-light": "#dcfce7",
            "--color-card-bg": "#ffffff",
            "--color-card-shadow": "rgba(16, 185, 129, 0.1)",
            "--color-nav-bg": "rgba(240, 253, 244, 0.9)",
            "--color-footer-bg": "#dcfce7",
            "--font-family-base": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-heading": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-decorative": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--backdrop-blur": "blur(12px)"
        }
    },
    "ocean": {
        "name": "海盐蓝",
        "variables": {
            "--color-primary": "#0ea5e9",
            "--color-primary-hover": "#0284c7",
            "--color-secondary": "#0f766e",
            "--color-background": "#f0f9ff",
            "--color-background-alt": "#e0f2fe",
            "--color-text": "#0c4a6e",
            "--color-text-light": "#075985",
            "--color-text-muted": "#0369a1",
            "--color-border": "#7dd3fc",
            "--color-border-light": "#e0f2fe",
            "--color-card-bg": "#ffffff",
            "--color-card-shadow": "rgba(14, 165, 233, 0.1)",
            "--color-nav-bg": "rgba(240, 249, 255, 0.9)",
            "--color-footer-bg": "#e0f2fe",
            "--font-family-base": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-heading": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-decorative": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--backdrop-blur": "blur(12px)"
        }
    },
    "sunset": {
        "name": "夕阳橙",
        "variables": {
            "--color-primary": "#ea8a12",
            "--color-primary-hover": "#c96a08",
            "--color-secondary": "#9a3412",
            "--color-background": "#fff7e6",
            "--color-background-alt": "#fde7bd",
            "--color-text": "#6f2f0f",
            "--color-text-light": "#92400e",
            "--color-text-muted": "#b45309",
            "--color-border": "#f2b26b",
            "--color-border-light": "#f7d7a4",
            "--color-card-bg": "#fffdf9",
            "--color-card-shadow": "rgba(234, 138, 18, 0.14)",
            "--color-nav-bg": "rgba(255, 247, 230, 0.92)",
            "--color-footer-bg": "#fde7bd",
            "--font-family-base": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-heading": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-decorative": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--backdrop-blur": "blur(12px)"
        }
    },
    "sakura": {
        "name": "樱花粉",
        "variables": {
            "--color-primary": "#e34f96",
            "--color-primary-hover": "#c92d77",
            "--color-secondary": "#9d174d",
            "--color-background": "#fff4f8",
            "--color-background-alt": "#f9dde9",
            "--color-text": "#6d173b",
            "--color-text-light": "#84214c",
            "--color-text-muted": "#a63a68",
            "--color-border": "#ee9fc3",
            "--color-border-light": "#f6d6e5",
            "--color-card-bg": "#fffdfd",
            "--color-card-shadow": "rgba(227, 79, 150, 0.14)",
            "--color-nav-bg": "rgba(255, 244, 248, 0.93)",
            "--color-footer-bg": "#f9dde9",
            "--font-family-base": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-heading": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-decorative": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--backdrop-blur": "blur(12px)"
        }
    },
    "galaxy": {
        "name": "星空紫",
        "variables": {
            "--color-primary": "#b26bff",
            "--color-primary-hover": "#9747f0",
            "--color-secondary": "#ddd6fe",
            "--color-background": "#0a0a18",
            "--color-background-alt": "#17162d",
            "--color-text": "#f6efff",
            "--color-text-light": "#ddd3fb",
            "--color-text-muted": "#bba9f7",
            "--color-border": "#6d55c6",
            "--color-border-light": "#2d2553",
            "--color-card-bg": "#18172c",
            "--color-card-shadow": "rgba(178, 107, 255, 0.2)",
            "--color-nav-bg": "rgba(10, 10, 24, 0.94)",
            "--color-footer-bg": "#17162d",
            "--font-family-base": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-heading": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-decorative": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--backdrop-blur": "blur(14px)"
        }
    },
    "mint": {
        "name": "薄荷绿",
        "variables": {
            "--color-primary": "#12a594",
            "--color-primary-hover": "#0f8477",
            "--color-secondary": "#0f766e",
            "--color-background": "#effcf8",
            "--color-background-alt": "#d8f5ed",
            "--color-text": "#0f4f48",
            "--color-text-light": "#11635a",
            "--color-text-muted": "#14766d",
            "--color-border": "#67d9c9",
            "--color-border-light": "#c7efe6",
            "--color-card-bg": "#fbfffd",
            "--color-card-shadow": "rgba(18, 165, 148, 0.13)",
            "--color-nav-bg": "rgba(239, 252, 248, 0.93)",
            "--color-footer-bg": "#d8f5ed",
            "--font-family-base": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-heading": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--font-family-decorative": "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
            "--backdrop-blur": "blur(12px)"
        }
    }
}

# 节日/纪念日场景别名：将扩展类型映射到基础特效场景
EFFECT_SCENE_ALIASES = {
    "mourn": "memorial",
    "spring_festival": "spring_festival",
    "new_year": "new_year",
    "cherry_blossom": "cherry_blossom",
    "winter": "winter",
    "autumn": "autumn",
    "valentine": "valentine",
    "christmas": "christmas",
    "national_day": "national_day",
    "rainy_day": "rainy_day",
    "stormy": "stormy",
    "sunny": "sunny",
    "cloudy": "cloudy",
    "spring": "spring",
    "summer": "summer",
    "thunderstorm": "thunderstorm",
    "festive": "festive",
    "celebration": "celebration",
    "memorial": "memorial",
}

# 特效场景默认特效映射（与前端 effect-manager 保持一致）
EFFECT_SCENE_PRESETS = {
    "festive": ["fireworks", "confetti", "lanterns"],
    "mourn": ["grayscale", "candles"],
    "spring_festival": ["lanterns", "firecrackers"],
    "new_year": ["fireworks", "confetti"],
    "cherry_blossom": ["sakura", "petals"],
    "winter": ["snow", "clouds"],
    "autumn": ["leaves"],
    "celebration": ["fireworks", "confetti"],
    "memorial": ["grayscale", "candles"],
    "valentine": ["sakura", "petals"],
    "christmas": ["snow", "fireworks"],
    "national_day": ["fireworks", "lanterns"],
    "rainy_day": ["rain", "clouds"],
    "stormy": ["rain", "thunder", "clouds"],
    "sunny": ["sunshine"],
    "cloudy": ["clouds"],
    "spring": ["sakura", "petals", "sunshine"],
    "summer": ["sunshine"],
    "thunderstorm": ["thunder", "rain"]
}

GLASS_INTENSITY_LEVELS = {"weak", "medium", "strong"}
DEFAULT_GLASS_INTENSITY = "medium"


def _extract_setting_value(setting: Optional[Setting], default: Any = None) -> Any:
    if not setting or setting.value is None:
        return default
    if isinstance(setting.value, dict):
        return setting.value.get("value", default)
    return setting.value


def parse_atmosphere_setting(setting: Optional[Setting]) -> Tuple[Optional[str], List[str]]:
    if not setting or setting.value is None:
        return None, []

    raw_value = setting.value
    atmosphere = None
    effects: List[str] = []

    if isinstance(raw_value, dict):
        atmosphere = raw_value.get("value")
        if isinstance(atmosphere, dict):
            atmosphere = atmosphere.get("value")
        raw_effects = raw_value.get("effects", [])
        if isinstance(raw_effects, list):
            effects = raw_effects
    elif isinstance(raw_value, str):
        atmosphere = raw_value

    if atmosphere is not None:
        atmosphere = str(atmosphere).strip().lower() or None

    return atmosphere, effects


def normalize_theme_name(theme_name: Optional[str]) -> str:
    if not theme_name:
        return "light"

    normalized = str(theme_name).strip().lower()
    return normalized if normalized in DEFAULT_THEMES else "light"


def resolve_theme_name(theme_name: Optional[str], custom_themes: Optional[Dict[str, Any]] = None) -> str:
    raw_theme = str(theme_name).strip() if theme_name else ""
    if not raw_theme:
        return "light"

    normalized_default = raw_theme.lower()
    if normalized_default in DEFAULT_THEMES:
        return normalized_default

    if custom_themes:
        if raw_theme in custom_themes:
            return raw_theme
        if raw_theme.lower() in custom_themes:
            return raw_theme.lower()

    return "light"


def normalize_effect_scene_name(scene: Optional[str]) -> Optional[str]:
    if not scene:
        return None

    normalized = str(scene).strip().lower()
    return EFFECT_SCENE_ALIASES.get(normalized, normalized)


def normalize_glass_intensity(intensity: Optional[str]) -> str:
    if not intensity:
        return DEFAULT_GLASS_INTENSITY
    normalized = str(intensity).strip().lower()
    if normalized in GLASS_INTENSITY_LEVELS:
        return normalized
    return DEFAULT_GLASS_INTENSITY


def get_scene_effects(scene: Optional[str], explicit_effects: Optional[List[str]] = None) -> List[str]:
    if explicit_effects:
        return explicit_effects

    if not scene:
        return []

    scene_key = str(scene).strip().lower()
    if scene_key in EFFECT_SCENE_PRESETS:
        return EFFECT_SCENE_PRESETS[scene_key]

    normalized = normalize_effect_scene_name(scene_key)
    if normalized in EFFECT_SCENE_PRESETS:
        return EFFECT_SCENE_PRESETS[normalized]

    return []


def load_custom_themes(db: Session) -> Dict[str, Any]:
    custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
    if not custom_themes_setting or not isinstance(custom_themes_setting.value, dict):
        return {}
    value = custom_themes_setting.value.get("value")
    return value if isinstance(value, dict) else {}


def resolve_theme_variables(theme_name: str, custom_themes: Dict[str, Any]) -> Dict[str, Any]:
    if theme_name in DEFAULT_THEMES:
        return dict(DEFAULT_THEMES[theme_name]["variables"])
    if theme_name in custom_themes and isinstance(custom_themes[theme_name], dict):
        variables = custom_themes[theme_name].get("variables")
        if isinstance(variables, dict):
            return dict(variables)
    return dict(DEFAULT_THEMES["light"]["variables"])


def get_site_default_theme(db: Session, custom_themes: Dict[str, Any]) -> str:
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    return resolve_theme_name(_extract_setting_value(theme_setting, "light"), custom_themes)


def resolve_active_theme(
    db: Session,
    request: Optional[Request] = None,
    explicit_theme: Optional[str] = None,
) -> Dict[str, Any]:
    custom_themes = load_custom_themes(db)
    theme_source = "system_default"
    resolved_theme = "light"

    if explicit_theme:
        resolved_theme = resolve_theme_name(explicit_theme, custom_themes)
        theme_source = "request_override"
    else:
        request_user = getattr(request.state, "authenticated_user", None) if request is not None else None
        user_theme = resolve_theme_name(getattr(request_user, "theme_preference", None), custom_themes) if request_user else "light"
        if request_user and getattr(request_user, "theme_preference", None) and user_theme != "light":
            resolved_theme = user_theme
            theme_source = "user_preference"
        else:
            site_theme = get_site_default_theme(db, custom_themes)
            if site_theme:
                resolved_theme = site_theme
                theme_source = "site_default"

    glass_intensity_setting = crud_setting.get_setting(db, key="glass_intensity")
    glass_intensity = normalize_glass_intensity(_extract_setting_value(glass_intensity_setting, DEFAULT_GLASS_INTENSITY))
    background_setting = crud_setting.get_setting(db, key="background_image_settings")
    background = background_setting.value.get("value") if background_setting and isinstance(background_setting.value, dict) else {"type": "none", "custom_url": None}

    return {
        "theme_id": resolved_theme,
        "theme_source": theme_source,
        "variables": resolve_theme_variables(resolved_theme, custom_themes),
        "glass_intensity": glass_intensity,
        "background": background or {"type": "none", "custom_url": None},
    }


def _load_anniversaries(db: Session) -> List[Dict[str, Any]]:
    anniversaries_setting = crud_setting.get_setting(db, key="anniversaries_json")
    if not anniversaries_setting or anniversaries_setting.value is None:
        return []

    raw_value = anniversaries_setting.value
    if isinstance(raw_value, dict):
        raw_value = raw_value.get("value", raw_value)

    try:
        if isinstance(raw_value, str):
            data = json.loads(raw_value)
        elif isinstance(raw_value, list):
            data = raw_value
        else:
            data = []
    except (TypeError, ValueError, json.JSONDecodeError):
        data = []

    return data if isinstance(data, list) else []


def resolve_current_anniversary_scene(db: Session) -> Optional[Dict[str, Any]]:
    anniversaries = _load_anniversaries(db)
    today = date.today()
    for anniversary in anniversaries:
        if not isinstance(anniversary, dict):
            continue
        try:
            month = int(anniversary.get("month"))
            day = int(anniversary.get("day"))
        except (TypeError, ValueError):
            continue
        if month == today.month and day == today.day:
            raw_scene = anniversary.get("type")
            normalized_scene = normalize_effect_scene_name(raw_scene)
            return {
                "scene": normalized_scene,
                "raw_scene": str(raw_scene or "").strip() or None,
                "effects": get_scene_effects(normalized_scene, anniversary.get("effects") if isinstance(anniversary.get("effects"), list) else []),
                "name": str(anniversary.get("name") or "").strip() or "纪念日",
                "source": "anniversary",
            }
    return None


def check_scheduled_effect_scene(db: Session) -> Optional[Dict[str, Any]]:
    enabled_setting = crud_setting.get_setting(db, key="effects_schedule_enabled")
    enabled = _extract_setting_value(enabled_setting, False)
    if not bool(enabled):
        return None

    schedule_setting = crud_setting.get_setting(db, key="theme_schedule")
    if not schedule_setting:
        return None

    schedule = schedule_setting.value.get("value", []) if isinstance(schedule_setting.value, dict) else []
    today = date.today()

    for item in schedule:
        if not isinstance(item, dict):
            continue

        try:
            start_date = datetime.strptime(item["start_date"], "%Y-%m-%d").date()
            end_date = datetime.strptime(item["end_date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue

        if start_date <= today <= end_date:
            raw_scene = item.get("atmosphere") or item.get("scene")
            normalized_scene = normalize_effect_scene_name(raw_scene)
            if normalized_scene:
                return {
                    "scene": normalized_scene,
                    "raw_scene": str(raw_scene).strip().lower(),
                    "effects": get_scene_effects(normalized_scene),
                    "source": "schedule",
                    "start_date": item.get("start_date"),
                    "end_date": item.get("end_date"),
                }

    return None


def resolve_active_effects(db: Session) -> Dict[str, Any]:
    anniversary_scene = resolve_current_anniversary_scene(db)
    if anniversary_scene:
        return {
            "scene": anniversary_scene["scene"],
            "source": "anniversary",
            "effects": anniversary_scene["effects"],
            "body_classes": [f"atmosphere-{anniversary_scene['scene']}"] if anniversary_scene["scene"] else [],
            "label": anniversary_scene.get("name", "纪念日"),
        }

    manual_setting = crud_setting.get_setting(db, key="current_atmosphere")
    manual_scene, manual_effects = parse_atmosphere_setting(manual_setting)
    normalized_manual_scene = normalize_effect_scene_name(manual_scene)
    if normalized_manual_scene:
        return {
            "scene": normalized_manual_scene,
            "source": "manual",
            "effects": get_scene_effects(normalized_manual_scene, manual_effects),
            "body_classes": [f"atmosphere-{normalized_manual_scene}"],
            "label": normalized_manual_scene,
        }

    scheduled_scene = check_scheduled_effect_scene(db)
    if scheduled_scene:
        return {
            "scene": scheduled_scene["scene"],
            "source": "schedule",
            "effects": scheduled_scene["effects"],
            "body_classes": [f"atmosphere-{scheduled_scene['scene']}"] if scheduled_scene["scene"] else [],
            "label": scheduled_scene["scene"],
        }

    return {
        "scene": None,
        "source": "none",
        "effects": [],
        "body_classes": [],
        "label": "",
    }

def _load_anniversaries_setting(db: Session) -> list[dict[str, Any]]:
    anniversaries_setting = crud_setting.get_setting(db, key="anniversaries_json")
    if not anniversaries_setting or not anniversaries_setting.value:
        return []

    try:
        anniversaries_json = anniversaries_setting.value.get("value") if isinstance(anniversaries_setting.value, dict) else anniversaries_setting.value
        anniversaries = json.loads(anniversaries_json) if isinstance(anniversaries_json, str) else anniversaries_json
    except Exception:
        return []

    return anniversaries if isinstance(anniversaries, list) else []


def _build_settings_holder(*, anniversaries: list[dict[str, Any]], background_settings: dict[str, Any]):
    return type("Settings", (), {
        "anniversaries": anniversaries,
        "background_image_settings": background_settings,
    })()


def _get_theme_page_context(request: Request, current_user: User, db: Session) -> Dict[str, Any]:
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    custom_themes = load_custom_themes(db)
    glass_intensity_setting = crud_setting.get_setting(db, key="glass_intensity")
    background_setting = crud_setting.get_setting(db, key="background_image_settings")

    current_theme = resolve_theme_name(_extract_setting_value(theme_setting, "light"), custom_themes)
    glass_intensity = normalize_glass_intensity(_extract_setting_value(glass_intensity_setting, DEFAULT_GLASS_INTENSITY))
    background_settings = background_setting.value.get("value") if background_setting else {"type": "none", "custom_url": None}

    return {
        "request": request,
        "user": current_user,
        "current_theme": current_theme,
        "default_themes": DEFAULT_THEMES,
        "custom_themes": custom_themes,
        "glass_intensity": glass_intensity,
        "background_settings": background_settings,
        "settings": _build_settings_holder(anniversaries=[], background_settings=background_settings),
    }


def _get_effects_page_context(request: Request, current_user: User, db: Session) -> Dict[str, Any]:
    atmosphere_setting = crud_setting.get_setting(db, key="current_atmosphere")
    effects_schedule_setting = crud_setting.get_setting(db, key="effects_schedule_enabled")
    theme_schedule_setting = crud_setting.get_setting(db, key="theme_schedule")
    background_setting = crud_setting.get_setting(db, key="background_image_settings")

    current_effect_scene, _ = parse_atmosphere_setting(atmosphere_setting)
    effects_schedule_enabled = bool(_extract_setting_value(effects_schedule_setting, False))
    theme_schedule = theme_schedule_setting.value.get("value") if theme_schedule_setting else []
    background_settings = background_setting.value.get("value") if background_setting else {"type": "none", "custom_url": None}
    anniversaries = _load_anniversaries_setting(db)

    return {
        "request": request,
        "user": current_user,
        "effect_scene_presets": EFFECT_SCENE_PRESETS,
        "current_effect_scene": normalize_effect_scene_name(current_effect_scene),
        "effects_schedule_enabled": effects_schedule_enabled,
        "theme_schedule": theme_schedule,
        "background_settings": background_settings,
        "settings": _build_settings_holder(anniversaries=anniversaries, background_settings=background_settings),
    }


# 主题管理页面已移至 main.py 中的动态路由注册系统
# 这样可以根据 ADMIN_PATH 配置动态生成路由，提高安全性
async def admin_theme_system_page(request: Request, db: Session, current_user: User):
    """主题系统页面 - 供 main.py 动态路由调用"""
    templates = get_templates()
    return templates.TemplateResponse("admin/themes.html", _get_theme_page_context(request, current_user, db))


async def admin_effects_page(request: Request, db: Session, current_user: User):
    """节日特效引擎页面 - 供 main.py 动态路由调用"""
    templates = get_templates()
    return templates.TemplateResponse("admin/effects.html", _get_effects_page_context(request, current_user, db))

# 主题更新路由已移至 main.py 中的动态路由注册系统
async def update_theme_settings(
    request: Request,
    db: Session,
    current_user: User,
    current_theme: str,
    glass_intensity: str,
    csrf_token: str
):
    """更新主题设置"""
    verify_csrf_token(request, csrf_token)
    
    custom_themes = load_custom_themes(db)
    normalized_current_theme = resolve_theme_name(current_theme, custom_themes)
    normalized_glass_intensity = normalize_glass_intensity(glass_intensity)

    # 更新当前主题
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    if theme_setting:
        crud_setting.update_setting(db, key="current_theme", setting_update=SettingUpdate(value={"value": normalized_current_theme}))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(
            key="current_theme", 
            value={"value": normalized_current_theme}, 
            description="当前使用的主题",
            category="theme"
        ))
    
    # 更新毛玻璃强度档位
    glass_intensity_setting = crud_setting.get_setting(db, key="glass_intensity")
    if glass_intensity_setting:
        crud_setting.update_setting(
            db,
            key="glass_intensity",
            setting_update=SettingUpdate(value={"value": normalized_glass_intensity}),
        )
    else:
        crud_setting.create_setting(
            db,
            setting=SettingCreate(
                key="glass_intensity",
                value={"value": normalized_glass_intensity},
                description="毛玻璃强度档位",
                category="theme",
            ),
        )
    
    # 对于HTMX请求，返回空响应或者重新渲染部分页面
    if request.headers.get("HX-Request"):
        # 返回成功提示的HTML片段
        return HTMLResponse("""
        <div class="fixed top-4 right-4 bg-green-500 text-white px-4 py-2 rounded-lg shadow-lg z-50" 
             style="animation: slideIn 0.3s ease-out;">
            <i class="fas fa-check-circle mr-2"></i>主题设置已更新
        </div>
        <script>
            setTimeout(() => {
                document.querySelector('.fixed.top-4.right-4').remove();
            }, 3000);
        </script>
        """)
    else:
        return JSONResponse({"success": True, "message": "主题设置已更新"})


async def update_effects_settings(
    request: Request,
    db: Session,
    current_user: User,
    effects_schedule_enabled: bool,
    csrf_token: str,
):
    """更新节日特效引擎设置"""
    verify_csrf_token(request, csrf_token)
    ensure_admin_user(current_user)

    effects_schedule_setting = crud_setting.get_setting(db, key="effects_schedule_enabled")
    if effects_schedule_setting:
        crud_setting.update_setting(
            db,
            key="effects_schedule_enabled",
            setting_update=SettingUpdate(value={"value": effects_schedule_enabled}),
        )
    else:
        crud_setting.create_setting(
            db,
            setting=SettingCreate(
                key="effects_schedule_enabled",
                value={"value": effects_schedule_enabled},
                description="是否启用节日特效调度",
                category="effects",
            ),
        )

    if request.headers.get("HX-Request"):
        return HTMLResponse(
            """
        <div class="fixed top-4 right-4 bg-green-500 text-white px-4 py-2 rounded-lg shadow-lg z-50"
             style="animation: slideIn 0.3s ease-out;">
            <i class="fas fa-check-circle mr-2"></i>节日特效引擎设置已更新
        </div>
        <script>
            setTimeout(() => {
                document.querySelector('.fixed.top-4.right-4')?.remove();
            }, 3000);
        </script>
        """
        )

    return JSONResponse({"success": True, "message": "节日特效引擎设置已更新"})





# 自定义主题创建路由已移至 main.py 中的动态路由注册系统
async def create_custom_theme(
    request: Request,
    db: Session,
    current_user: User,
    theme_name: str,
    theme_data: str,
    csrf_token: str
):
    """创建自定义主题"""
    verify_csrf_token(request, csrf_token)
    ensure_admin_user(current_user)
    
    try:
        theme_config = json.loads(theme_data)
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "message": "主题配置格式错误"})
    
    # 获取现有自定义主题
    custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
    custom_themes = custom_themes_setting.value.get("value") if custom_themes_setting else {}
    
    # 添加新主题
    custom_themes[theme_name] = {
        "name": theme_config.get("name", theme_name),
        "variables": theme_config.get("variables", {}),
        "created_at": datetime.now().isoformat()
    }
    
    # 保存到数据库
    if custom_themes_setting:
        crud_setting.update_setting(db, key="custom_themes", setting_update=SettingUpdate(value={"value": custom_themes}))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(
            key="custom_themes",
            value={"value": custom_themes},
            description="自定义主题配置",
            category="theme"
        ))
    
    return JSONResponse({"success": True, "message": "自定义主题已创建"})

# 自定义主题删除路由已移至 main.py 中的动态路由注册系统
async def delete_custom_theme(
    theme_name: str,
    request: Request,
    db: Session,
    current_user: User,
    csrf_token: str,
):
    """删除自定义主题"""
    verify_csrf_token(request, csrf_token)
    ensure_admin_user(current_user)

    custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
    if not custom_themes_setting:
        raise HTTPException(status_code=404, detail="未找到自定义主题")
    
    custom_themes = custom_themes_setting.value.get("value", {})
    if theme_name not in custom_themes:
        raise HTTPException(status_code=404, detail="主题不存在")
    
    del custom_themes[theme_name]
    crud_setting.update_setting(db, key="custom_themes", setting_update=SettingUpdate(value={"value": custom_themes}))
    
    return JSONResponse({"success": True, "message": "主题已删除"})

# 主题调度路由已移至 main.py 中的动态路由注册系统
async def schedule_themes(
    request: Request,
    db: Session,
    current_user: User,
    schedule_data: str,
    csrf_token: str
):
    """更新节日特效调度设置"""
    verify_csrf_token(request, csrf_token)
    
    try:
        schedule = json.loads(schedule_data)
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "message": "调度配置格式错误"})
    
    schedule_setting = crud_setting.get_setting(db, key="theme_schedule")
    if schedule_setting:
        crud_setting.update_setting(db, key="theme_schedule", setting_update=SettingUpdate(value={"value": schedule}))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(
            key="theme_schedule",
            value={"value": schedule},
            description="节日特效调度配置",
            category="effects"
        ))
    
    return JSONResponse({"success": True, "message": "主题调度已更新"})

# 背景图片更新路由已移至 main.py 中的动态路由注册系统
async def update_background_image(
    request: Request,
    db: Session,
    current_user: User,
    background_type: str,
    custom_background_url: Optional[str],
    csrf_token: str
):
    """更新背景图片设置"""
    verify_csrf_token(request, csrf_token)
    ensure_admin_user(current_user)
    
    # 构建背景设置数据
    background_settings = {
        "type": background_type,
        "custom_url": custom_background_url
    }
    
    # 保存到数据库
    background_setting = crud_setting.get_setting(db, key="background_image_settings")
    if background_setting:
        crud_setting.update_setting(db, key="background_image_settings", setting_update=SettingUpdate(value={"value": background_settings}))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(
            key="background_image_settings",
            value={"value": background_settings},
            description="背景图片设置",
            category="theme"
        ))
    
    return JSONResponse({"success": True, "message": "背景图片设置已保存"})

@router.post("/api/v1/admin/themes/background")
@router.post("/api/admin/themes/background")
async def update_background_image_api(
    request: Request,
    background_type: str = Form(...),
    custom_background_url: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await update_background_image(
        request=request,
        db=db,
        current_user=current_user,
        background_type=background_type,
        custom_background_url=custom_background_url,
        csrf_token=csrf_token,
    )


@router.get("/api/v1/theme/current")
@router.get("/api/theme/current")
async def get_current_theme(request: Request, db: Session = Depends(get_db)):
    """获取当前主题配置（前端 API）"""
    requested_theme = str(request.query_params.get("theme") or "").strip()
    resolved_theme = resolve_active_theme(db, request=request, explicit_theme=requested_theme or None)
    resolved_effects = resolve_active_effects(db)
    return JSONResponse({
        "theme": resolved_theme["theme_id"],
        "theme_source": resolved_theme["theme_source"],
        "background": resolved_theme["background"],
        "glass_intensity": resolved_theme["glass_intensity"],
        "variables": resolved_theme["variables"],
        "resolved_effects": resolved_effects,
    })

@router.get("/api/v1/theme/variables.css")
@router.get("/api/theme/variables.css")
async def theme_variables_css(request: Request, db: Session = Depends(get_db)):
    """动态生成 CSS 变量文件，仅处理主题变量。"""
    from fastapi.responses import Response
    
    theme_response = await get_current_theme(request, db)
    theme_data = json.loads(theme_response.body)
    
    # 构建CSS内容
    css_content = ":root {\n"
    for var_name, var_value in theme_data["variables"].items():
        css_content += f"    {var_name}: {var_value};\n"
    css_content += "}\n"
    
    return Response(
        content=css_content,
        media_type="text/css",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )

@router.post("/api/v1/theme/update")
@router.post("/api/theme/update")
async def update_theme_realtime(
    request: Request,
    theme: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """实时更新已登录用户的主题偏好。"""
    verify_csrf_token(request, csrf_token)
    
    custom_themes = load_custom_themes(db)
    theme_to_save = resolve_theme_name(theme, custom_themes)
    if str(theme_to_save).strip() == "light" and str(theme).strip().lower() not in DEFAULT_THEMES and str(theme).strip() not in custom_themes:
        raise HTTPException(status_code=400, detail="主题不存在")

    updated_user = crud_user.set_user_theme_preference(
        db,
        int(current_user.id),
        theme_preference=theme_to_save,
    )
    request.state.authenticated_user = updated_user
    return JSONResponse({"success": True, "theme": theme_to_save, "theme_source": "user_preference"})

@router.post("/api/v1/atmosphere/update")
@router.post("/api/atmosphere/update")
async def update_atmosphere_realtime(
    request: Request,
    atmosphere: Optional[str] = Form(None),
    effects: List[str] = Form([]),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """实时更新手动特效场景设置"""
    verify_csrf_token(request, csrf_token)
    ensure_admin_user(current_user)
    
    normalized_scene = normalize_effect_scene_name(atmosphere)
    if atmosphere and not normalized_scene:
        raise HTTPException(status_code=400, detail="特效场景不存在")
    
    atmosphere_setting = crud_setting.get_setting(db, key="current_atmosphere")
    atmosphere_data = {
        "value": normalized_scene,
        "effects": effects,
        "updated_at": datetime.now().isoformat()
    }
    
    if atmosphere_setting:
        crud_setting.update_setting(db, key="current_atmosphere", setting_update=SettingUpdate(value=atmosphere_data))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(key="current_atmosphere", value=atmosphere_data))
    
    return JSONResponse({"success": True, "scene": normalized_scene, "effects": effects})

@router.get("/api/v1/theme/sync")
@router.get("/api/theme/sync")
async def sync_theme_settings(request: Request, db: Session = Depends(get_db)):
    """同步主题与特效设置。"""
    resolved_theme = resolve_active_theme(db, request=request)
    resolved_effects = resolve_active_effects(db)
    homepage_setting = crud_setting.get_setting(db, key="homepage_mode")
    homepage_mode = homepage_setting.value.get("value") if homepage_setting else "default"

    return JSONResponse({
        "theme": resolved_theme["theme_id"],
        "theme_source": resolved_theme["theme_source"],
        "resolved_effects": resolved_effects,
        "homepage_mode": homepage_mode,
        "background": resolved_theme["background"],
        "glass_intensity": resolved_theme["glass_intensity"],
        "timestamp": datetime.now().isoformat()
    }, headers={"Cache-Control": "no-cache, must-revalidate"})
