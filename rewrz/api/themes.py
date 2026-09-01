"""
动态主题系统和节日特效引擎 API 模块。

提供以下功能：
1. 主题配置管理（浅色/深色/自定义主题）
2. 节日特效引擎（节日、纪念日、特殊活动特效）
3. 主题预设和自定义 CSS 变量
4. 特效调度与自动切换
"""
import json
import os
import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..core.database import get_db, db_manager
from ..core import effects_engine
from ..core.security import ensure_admin_user, get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..crud import setting as crud_setting
from ..crud import user as crud_user
from ..schemas import Setting, SettingCreate, SettingUpdate, User

router = APIRouter()
logger = logging.getLogger(__name__)

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
    "festive": ["fireworks", "confetti", "lanterns", "golden_dust", "stars"],
    "mourn": ["grayscale", "candles", "floating_lights"],
    "spring_festival": ["lanterns", "firecrackers", "golden_dust", "embers"],
    "new_year": ["fireworks", "confetti", "golden_dust", "stars"],
    "cherry_blossom": ["sakura", "petals"],
    "winter": ["snow", "clouds", "moonlight"],
    "autumn": ["leaves"],
    "celebration": ["fireworks", "confetti", "golden_dust", "balloons"],
    "memorial": ["grayscale", "candles", "floating_lights"],
    "valentine": ["hearts", "petals", "sakura", "stars"],
    "christmas": ["snow", "fireworks", "floating_lights", "stars"],
    "national_day": ["fireworks", "lanterns", "golden_dust", "stars"],
    "rainy_day": ["rain", "clouds"],
    "stormy": ["rain", "thunder", "clouds"],
    "sunny": ["sunshine"],
    "cloudy": ["clouds"],
    "spring": ["sakura", "petals", "sunshine"],
    "summer": ["sunshine", "bubbles", "balloons"],
    "thunderstorm": ["thunder", "rain"]
}

AVAILABLE_EFFECT_OPTIONS = [
    {"value": "fireworks", "label": "烟花绽放", "icon": "🎆"},
    {"value": "countdown_banner", "label": "跨年倒计时", "icon": "⏳"},
    {"value": "lanterns", "label": "红灯笼", "icon": "🏮"},
    {"value": "firecrackers", "label": "爆竹声声", "icon": "🧨"},
    {"value": "confetti", "label": "彩带飞舞", "icon": "🎊"},
    {"value": "golden_dust", "label": "金色流光", "icon": "✨"},
    {"value": "floating_lights", "label": "漂浮光点", "icon": "🏮"},
    {"value": "hearts", "label": "爱心漂浮", "icon": "💖"},
    {"value": "balloons", "label": "气球上升", "icon": "🎈"},
    {"value": "bubbles", "label": "梦幻气泡", "icon": "🫧"},
    {"value": "moonlight", "label": "月光皎洁", "icon": "🌕"},
    {"value": "stars", "label": "星光闪烁", "icon": "✨"},
    {"value": "embers", "label": "暖焰余烬", "icon": "🔥"},
    {"value": "rice_grains", "label": "米粒飘落", "icon": "🌾"},
    {"value": "red_packets", "label": "红包飘落", "icon": "🧧"},
    {"value": "ingots", "label": "元宝飘落", "icon": "💰"},
    {"value": "tangyuan", "label": "汤圆漂浮", "icon": "🍡"},
    {"value": "dragon_shape", "label": "龙形轮廓", "icon": "🐉"},
    {"value": "willow_catkins", "label": "柳絮飘落", "icon": "🌿"},
    {"value": "gear_icons", "label": "齿轮漂浮", "icon": "⚙️"},
    {"value": "tie_icons", "label": "领带漂浮", "icon": "👔"},
    {"value": "dragon_boats", "label": "龙舟横渡", "icon": "🚣"},
    {"value": "zongzi", "label": "粽子飘落", "icon": "🍙"},
    {"value": "star_bridge", "label": "星桥流光", "icon": "🌌"},
    {"value": "feathers", "label": "羽毛飘落", "icon": "🪶"},
    {"value": "paper_charms", "label": "纸符飘落", "icon": "🪔"},
    {"value": "lotus_lights", "label": "河灯漂浮", "icon": "🪷"},
    {"value": "chalk_writing", "label": "粉笔字横幅", "icon": "✍️"},
    {"value": "osmanthus", "label": "桂花飘落", "icon": "🌼"},
    {"value": "dumplings", "label": "饺子飘落", "icon": "🥟"},
    {"value": "tree_lights", "label": "圣诞灯串", "icon": "🎄"},
    {"value": "grayscale", "label": "全站灰白", "icon": "⚫"},
    {"value": "candles", "label": "蜡烛摇曳", "icon": "🕯️"},
    {"value": "petals", "label": "花瓣飘落", "icon": "🌸"},
    {"value": "sakura", "label": "樱花飞舞", "icon": "🌺"},
    {"value": "snow", "label": "雪花飘飘", "icon": "❄️"},
    {"value": "leaves", "label": "落叶纷飞", "icon": "🍂"},
    {"value": "rain", "label": "下雨天", "icon": "🌧️"},
    {"value": "thunder", "label": "雷电交加", "icon": "⚡"},
    {"value": "clouds", "label": "云雾缭绕", "icon": "☁️"},
    {"value": "sunshine", "label": "阳光明媚", "icon": "☀️"},
]

EFFECT_SCENE_DISPLAY_NAMES = {
    "festive": "节庆热闹",
    "mourn": "肃穆追思",
    "spring_festival": "新春喜庆",
    "new_year": "跨年庆典",
    "cherry_blossom": "樱花烂漫",
    "winter": "冬日静景",
    "autumn": "秋意层叠",
    "celebration": "欢庆时刻",
    "memorial": "纪念追思",
    "valentine": "浪漫告白",
    "christmas": "圣诞冬夜",
    "national_day": "国庆欢腾",
    "rainy_day": "细雨氛围",
    "stormy": "风暴来临",
    "sunny": "晴朗明快",
    "cloudy": "云雾轻覆",
    "spring": "春日生机",
    "summer": "夏日明亮",
    "thunderstorm": "雷雨交织",
}

EFFECT_SOURCE_DISPLAY_NAMES = {
    "custom": "自定义纪念日",
    "manual": "手动触发",
    "public": "公共节日",
    "schedule": "调度规则",
    "none": "未命中",
}

CALENDAR_TYPE_DISPLAY_NAMES = {
    "solar_fixed": "公历固定日",
    "solar_weekday": "公历按星期",
    "lunar_fixed": "农历固定日",
    "solar_term": "节气日",
}

EFFECT_OPTION_DESCRIPTIONS = {
    "fireworks": "适合跨年、国庆与庆典场景",
    "countdown_banner": "适合元旦、跨年与倒计时场景",
    "lanterns": "适合春节、元宵与中式节日",
    "firecrackers": "适合春节、除夕等热闹场景",
    "confetti": "适合祝贺、庆生与站庆场景",
    "golden_dust": "适合新春、国庆与节庆流光氛围",
    "floating_lights": "适合中元、中秋与冬夜静态光点氛围",
    "hearts": "适合情人节、七夕与温柔告白场景",
    "balloons": "适合儿童节、生日与站庆欢庆场景",
    "bubbles": "适合儿童节、夏季与轻盈梦幻氛围",
    "moonlight": "适合中秋、冬至与夜景静态氛围",
    "stars": "适合七夕、中秋、圣诞与星夜场景",
    "embers": "适合小年、除夕与暖焰灶火氛围",
    "rice_grains": "适合腊八与细碎粮食飘落氛围",
    "red_packets": "适合春节、新春与红包飘落场景",
    "ingots": "适合破五、迎财神与财运场景",
    "tangyuan": "适合元宵与团圆漂浮场景",
    "dragon_shape": "适合龙抬头与龙形轮廓场景",
    "willow_catkins": "适合清明与轻柔柳絮场景",
    "gear_icons": "适合劳动节与工业符号场景",
    "tie_icons": "适合父亲节与成熟礼赠场景",
    "dragon_boats": "适合端午与龙舟横渡场景",
    "zongzi": "适合端午与粽子飘落场景",
    "star_bridge": "适合七夕与鹊桥星桥场景",
    "feathers": "适合七夕与轻柔羽毛场景",
    "paper_charms": "适合中元与肃穆纸符场景",
    "lotus_lights": "适合中元与河灯静景场景",
    "chalk_writing": "适合教师节与粉笔字祝福场景",
    "osmanthus": "适合中秋与桂花夜香场景",
    "dumplings": "适合冬至与饺子团圆场景",
    "tree_lights": "适合圣诞与灯串装饰场景",
    "grayscale": "适合追思、纪念与庄重场景",
    "candles": "适合纪念、追思与夜间氛围",
    "petals": "适合节庆、教师节与温柔氛围",
    "sakura": "适合情人节、七夕与春日氛围",
    "snow": "适合冬至、圣诞与冬日氛围",
    "leaves": "适合重阳与秋季氛围",
    "rain": "适合雨季与天气类场景",
    "thunder": "适合雷雨与强烈天气氛围",
    "clouds": "适合中秋、冬至与朦胧场景",
    "sunshine": "适合儿童节、夏季与明快场景",
}

PUBLIC_HOLIDAY_CODE_DISPLAY_NAMES = {
    str(item.get("code")): str(item.get("name"))
    for item in effects_engine.PUBLIC_HOLIDAY_PRESETS
    if item.get("code") and item.get("name")
}

GLASS_INTENSITY_LEVELS = {"weak", "medium", "strong"}
DEFAULT_GLASS_INTENSITY = "medium"


def _extract_setting_value(setting: Optional[Setting], default: Any = None) -> Any:
    if not setting or setting.value is None:
        return default
    if isinstance(setting.value, dict):
        return setting.value.get("value", default)
    return setting.value


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


def get_effect_option_meta(effect: Optional[str]) -> Dict[str, str]:
    effect_key = str(effect or "").strip().lower()
    for option in AVAILABLE_EFFECT_OPTIONS:
        if option["value"] == effect_key:
            return {
                "value": option["value"],
                "label": option["label"],
                "icon": option["icon"],
                "description": EFFECT_OPTION_DESCRIPTIONS.get(option["value"], option["label"]),
            }
    return {
        "value": effect_key,
        "label": effect_key or "未命名特效",
        "icon": "✨",
        "description": "自定义特效",
    }


def get_effect_scene_label(scene: Optional[str]) -> str:
    normalized = normalize_effect_scene_name(scene)
    if not normalized:
        return "无特效"
    return EFFECT_SCENE_DISPLAY_NAMES.get(normalized, normalized)


def get_effect_source_label(source: Optional[str]) -> str:
    key = str(source or "").strip().lower()
    return EFFECT_SOURCE_DISPLAY_NAMES.get(key, key or "未命中")


def get_calendar_type_label(calendar_type: Optional[str]) -> str:
    key = str(calendar_type or "").strip().lower()
    return CALENDAR_TYPE_DISPLAY_NAMES.get(key, key or "未设置")


def _build_effect_options_for_display() -> List[Dict[str, Any]]:
    return [get_effect_option_meta(option["value"]) for option in AVAILABLE_EFFECT_OPTIONS]


def _build_effect_scene_options() -> List[Dict[str, Any]]:
    options: List[Dict[str, Any]] = []
    for scene_key in EFFECT_SCENE_PRESETS:
        options.append(
            {
                "value": scene_key,
                "label": get_effect_scene_label(scene_key),
                "effects": [get_effect_option_meta(effect) for effect in get_scene_effects(scene_key)],
            }
        )
    return options


def _build_effect_badges(effects: Optional[List[str]]) -> List[Dict[str, str]]:
    return [get_effect_option_meta(effect) for effect in effects or []]


def _build_public_holiday_display_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    display_items: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        display_items.append(
            {
                **item,
                "name": str(item.get("name") or PUBLIC_HOLIDAY_CODE_DISPLAY_NAMES.get(code) or "未命名公共节日").strip(),
                "calendar_type_label": get_calendar_type_label(item.get("calendar_type")),
                "effect_scene_label": get_effect_scene_label(item.get("effect_scene")),
                "effects_display": _build_effect_badges(item.get("effects")),
            }
        )
    return display_items


def _build_custom_anniversary_display_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    display_items: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        display_items.append(
            {
                **item,
                "date_type_label": get_calendar_type_label(item.get("date_type") or item.get("calendar_type")),
                "effect_scene_label": get_effect_scene_label(item.get("effect_scene")),
                "effects_display": _build_effect_badges(item.get("effects")),
            }
        )
    return display_items


def _build_resolved_effect_match_display_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    display_items: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        display_items.append(
            {
                **item,
                "source_label": get_effect_source_label(item.get("source")),
                "scene_label": get_effect_scene_label(item.get("scene")),
                "effects_display": _build_effect_badges(item.get("effects")),
            }
        )
    return display_items


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


def check_scheduled_effect_scene(db: Session) -> Optional[Dict[str, Any]]:
    enabled_setting = crud_setting.get_setting(db, key="effects_schedule_enabled")
    enabled = _extract_setting_value(enabled_setting, False)
    if not bool(enabled):
        return None

    resolved = effects_engine.resolve_active_effects_state(db, include_matches=True)
    for item in resolved.get("matched_items", []) or []:
        if item.get("source") == "schedule":
            return {
                "scene": item.get("scene"),
                "raw_scene": item.get("scene"),
                "effects": item.get("effects", []),
                "source": "schedule",
            }
    return None


def resolve_active_effects(db: Session) -> Dict[str, Any]:
    resolved = effects_engine.resolve_active_effects_state(db)
    source = str(resolved.get("source") or "none")
    source_alias = {
        "custom": "anniversary",
        "public": "anniversary",
        "manual": "manual",
        "schedule": "schedule",
        "none": "none",
    }
    resolved["source"] = source_alias.get(source, source)
    return resolved


def run_daily_effects_refresh_task() -> None:
    """
    每日节日特效刷新任务。

    当前阶段先统一走解析链并记录结果，确保后续正式接入
    公共节日实例生成与自定义纪念日清理时无需再改调度器结构。
    """
    session = db_manager.get_session()
    if session is None:
        logger.warning("每日节日特效刷新任务跳过：数据库会话不可用")
        return

    try:
        current_year = date.today().year
        effects_engine.ensure_public_holiday_catalog(session, current_year)
        resolved_effects = resolve_active_effects(session)
        logger.info(
            "每日节日特效刷新任务完成：scene=%s source=%s effects=%s",
            resolved_effects.get("scene"),
            resolved_effects.get("source"),
            resolved_effects.get("effects", []),
        )
    finally:
        session.close()


def run_public_holiday_rollover_task() -> None:
    """
    公共节日年度换年任务。

    当前阶段先保留正式任务入口并记录日志，后续接入公共节日
    年度实例生成逻辑时直接补充此函数即可。
    """
    session = db_manager.get_session()
    if session is None:
        logger.warning("公共节日换年任务跳过：数据库会话不可用")
        return

    try:
        next_year = date.today().year + 1
        effects_engine.rebuild_public_holiday_catalog(session, next_year)
        logger.info("公共节日换年任务完成：已重建 %s 年公共节日清单", next_year)
    finally:
        session.close()


def _build_settings_holder(
    *,
    anniversaries: list[dict[str, Any]],
    background_settings: dict[str, Any],
    public_holidays: Optional[list[dict[str, Any]]] = None,
    custom_anniversaries: Optional[list[dict[str, Any]]] = None,
    schedule_rules: Optional[list[dict[str, Any]]] = None,
):
    return type("Settings", (), {
        "anniversaries": anniversaries,
        "public_holidays": public_holidays or [],
        "custom_anniversaries": custom_anniversaries or anniversaries,
        "schedule_rules": schedule_rules or [],
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
    effects_schedule_setting = crud_setting.get_setting(db, key="effects_schedule_enabled")
    background_setting = crud_setting.get_setting(db, key="background_image_settings")

    effects_schedule_enabled = bool(_extract_setting_value(effects_schedule_setting, False))
    background_settings = background_setting.value.get("value") if background_setting else {"type": "none", "custom_url": None}
    custom_anniversaries = effects_engine.load_custom_anniversaries(db)
    public_catalog = effects_engine.ensure_public_holiday_catalog(db, date.today().year)
    schedule_rules = effects_engine.load_schedule_rules(db)
    current_resolved_effects = effects_engine.resolve_active_effects_state(db, include_matches=True)
    public_holidays_display = _build_public_holiday_display_items(public_catalog.get("items", []))
    custom_anniversaries_display = _build_custom_anniversary_display_items(custom_anniversaries)
    resolved_effect_matches = _build_resolved_effect_match_display_items(current_resolved_effects.get("matched_items", []))

    return {
        "request": request,
        "user": current_user,
        "effect_scene_presets": EFFECT_SCENE_PRESETS,
        "effect_scene_options": _build_effect_scene_options(),
        "effect_options": _build_effect_options_for_display(),
        "current_effect_scene": get_effect_scene_label(current_resolved_effects.get("scene")),
        "effects_schedule_enabled": effects_schedule_enabled,
        "background_settings": background_settings,
        "settings": _build_settings_holder(
            anniversaries=[],
            public_holidays=public_holidays_display,
            custom_anniversaries=custom_anniversaries_display,
            schedule_rules=schedule_rules,
            background_settings=background_settings,
        ),
        "public_holiday_catalog_year": public_catalog.get("year"),
        "resolved_effect_matches": resolved_effect_matches,
    }


# 主题管理页面已移至 main.py 中的动态路由注册系统
# 这样可以根据 ADMIN_PATH 配置动态生成路由，提高安全性
async def admin_theme_system_page(request: Request, db: Session, current_user: User):
    """主题系统页面 - 供 main.py 动态路由调用"""
    templates = get_templates()
    return templates.TemplateResponse(request, "admin/themes.html", _get_theme_page_context(request, current_user, db))


async def admin_effects_page(request: Request, db: Session, current_user: User):
    """节日特效引擎页面 - 供 main.py 动态路由调用"""
    templates = get_templates()
    return templates.TemplateResponse(request, "admin/effects.html", _get_effects_page_context(request, current_user, db))

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


async def save_public_holiday_settings(
    request: Request,
    db: Session,
    current_user: User,
    csrf_token: str,
) -> JSONResponse:
    """保存公共节日预设实例。"""
    verify_csrf_token(request, csrf_token)
    ensure_admin_user(current_user)

    data = await request.json()
    target_year = int(data.get("year") or date.today().year)
    holidays = data.get("holidays", [])
    catalog = effects_engine.normalize_public_holiday_payloads(target_year, holidays)
    effects_engine.save_public_holiday_catalog(db, catalog)
    return JSONResponse({
        "success": True,
        "message": f"已保存 {len(catalog.get('items', []))} 条公共节日配置",
        "year": target_year,
    })


async def rebuild_public_holiday_settings(
    request: Request,
    db: Session,
    current_user: User,
    csrf_token: str,
) -> JSONResponse:
    """重建指定年份的公共节日实例。"""
    verify_csrf_token(request, csrf_token)
    ensure_admin_user(current_user)

    data = await request.json()
    target_year = int(data.get("year") or date.today().year)
    catalog = effects_engine.rebuild_public_holiday_catalog(db, target_year)
    return JSONResponse({
        "success": True,
        "message": f"已重建 {target_year} 年公共节日清单",
        "year": target_year,
        "count": len(catalog.get("items", [])),
    })


async def save_custom_anniversary_settings(
    request: Request,
    db: Session,
    current_user: User,
    csrf_token: str,
) -> JSONResponse:
    """保存自定义纪念日。"""
    verify_csrf_token(request, csrf_token)
    ensure_admin_user(current_user)

    data = await request.json()
    anniversaries = data.get("anniversaries", [])
    normalized = effects_engine.normalize_custom_anniversary_payloads(anniversaries)
    effects_engine.save_custom_anniversaries(db, normalized)
    return JSONResponse({
        "success": True,
        "message": f"已保存 {len(normalized)} 条自定义纪念日规则",
        "count": len(normalized),
    })





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
