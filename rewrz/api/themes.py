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
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..crud import setting as crud_setting
from ..schemas import Setting, SettingCreate, SettingUpdate, User

router = APIRouter()

# 预定义主题配置（统一为 5 种预设，兼容旧键名）
DEFAULT_THEMES = {
    "light": {
        "name": "浅色主题",
        "variables": {
            "--color-primary": "#4f46e5",
            "--color-primary-hover": "#4338ca",
            "--color-secondary": "#6b7280",
            "--color-background": "#ffffff",
            "--color-background-alt": "#f8fafc",
            "--color-text": "#1e293b",
            "--color-text-light": "#64748b",
            "--color-text-muted": "#94a3b8",
            "--color-border": "#e2e8f0",
            "--color-border-light": "#f1f5f9",
            "--color-card-bg": "#ffffff",
            "--color-card-shadow": "rgba(0, 0, 0, 0.1)",
            "--color-nav-bg": "rgba(255, 255, 255, 0.8)",
            "--color-footer-bg": "#f8fafc",
            "--backdrop-blur": "blur(10px)"
        }
    },
    "dark": {
        "name": "深色主题",
        "variables": {
            "--color-primary": "#6366f1",
            "--color-primary-hover": "#4f46e5",
            "--color-secondary": "#94a3b8",
            "--color-background": "#0f172a",
            "--color-background-alt": "#1e293b",
            "--color-text": "#f1f5f9",
            "--color-text-light": "#cbd5e1",
            "--color-text-muted": "#94a3b8",
            "--color-border": "#334155",
            "--color-border-light": "#475569",
            "--color-card-bg": "#1e293b",
            "--color-card-shadow": "rgba(0, 0, 0, 0.3)",
            "--color-nav-bg": "rgba(15, 23, 42, 0.8)",
            "--color-footer-bg": "#1e293b",
            "--backdrop-blur": "blur(10px)"
        }
    },
    "nature": {
        "name": "自然主题",
        "variables": {
            "--color-primary": "#059669",
            "--color-primary-hover": "#047857",
            "--color-secondary": "#6b7280",
            "--color-background": "#f0fdf4",
            "--color-background-alt": "#dcfce7",
            "--color-text": "#14532d",
            "--color-text-light": "#166534",
            "--color-text-muted": "#22c55e",
            "--color-border": "#bbf7d0",
            "--color-border-light": "#dcfce7",
            "--color-card-bg": "#ffffff",
            "--color-card-shadow": "rgba(5, 150, 105, 0.1)",
            "--color-nav-bg": "rgba(240, 253, 244, 0.9)",
            "--color-footer-bg": "#dcfce7",
            "--backdrop-blur": "blur(12px)"
        }
    },
    "ocean": {
        "name": "海洋主题",
        "variables": {
            "--color-primary": "#0ea5e9",
            "--color-primary-hover": "#0284c7",
            "--color-secondary": "#64748b",
            "--color-background": "#f0f9ff",
            "--color-background-alt": "#e0f2fe",
            "--color-text": "#0c4a6e",
            "--color-text-light": "#0369a1",
            "--color-text-muted": "#0284c7",
            "--color-border": "#bae6fd",
            "--color-border-light": "#e0f2fe",
            "--color-card-bg": "#ffffff",
            "--color-card-shadow": "rgba(14, 165, 233, 0.1)",
            "--color-nav-bg": "rgba(240, 249, 255, 0.9)",
            "--color-footer-bg": "#e0f2fe",
            "--backdrop-blur": "blur(12px)"
        }
    },
    "sunset": {
        "name": "夕阳主题",
        "variables": {
            "--color-primary": "#f59e0b",
            "--color-primary-hover": "#d97706",
            "--color-secondary": "#78716c",
            "--color-background": "#fffbeb",
            "--color-background-alt": "#fef3c7",
            "--color-text": "#92400e",
            "--color-text-light": "#b45309",
            "--color-text-muted": "#f59e0b",
            "--color-border": "#fed7aa",
            "--color-border-light": "#fef3c7",
            "--color-card-bg": "#ffffff",
            "--color-card-shadow": "rgba(245, 158, 11, 0.1)",
            "--color-nav-bg": "rgba(255, 251, 235, 0.9)",
            "--color-footer-bg": "#fef3c7",
            "--backdrop-blur": "blur(12px)"
        }
    }
}

# 历史主题键兼容映射
BACKWARD_COMPAT_THEME_ALIASES = {
    "auto": "light",
    "forest": "nature"
}

# 氛围主题配置
ATMOSPHERE_THEMES = {
    "festive": {
        "name": "节日氛围",
        "description": "春节、圣诞节等节日主题",
        "css_class": "atmosphere-festive",
        "effects": ["fireworks", "confetti", "lanterns"],
        "variables": {
            "--color-primary": "#ef4444",
            "--color-secondary": "#fbbf24"
        }
    },
    "memorial": {
        "name": "纪念氛围", 
        "description": "纪念日、哀悼日等肃穆主题",
        "css_class": "atmosphere-memorial",
        "effects": ["grayscale", "candles"],
        "variables": {
            "--color-primary": "#6b7280",
            "--color-secondary": "#9ca3af"
        }
    },
    "celebration": {
        "name": "庆祝氛围",
        "description": "生日、周年等庆祝主题",
        "css_class": "atmosphere-celebration", 
        "effects": ["fireworks", "confetti"],
        "variables": {
            "--color-primary": "#8b5cf6",
            "--color-secondary": "#f59e0b"
        }
    }
}

# 氛围别名：将扩展类型映射到基础氛围样式
ATMOSPHERE_THEME_ALIASES = {
    "mourn": "memorial",
    "spring_festival": "festive",
    "new_year": "celebration",
    "cherry_blossom": "celebration",
    "winter": "memorial",
    "autumn": "celebration",
    "valentine": "celebration",
    "christmas": "festive",
    "national_day": "festive",
    "rainy_day": "memorial",
    "stormy": "memorial",
    "sunny": "celebration",
    "cloudy": "memorial",
    "spring": "celebration",
    "summer": "celebration",
    "thunderstorm": "memorial"
}

# 扩展氛围默认特效映射（与前端 effect-manager 保持一致）
ATMOSPHERE_EFFECT_PRESETS = {
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
    normalized = BACKWARD_COMPAT_THEME_ALIASES.get(normalized, normalized)
    return normalized if normalized in DEFAULT_THEMES else "light"


def resolve_theme_name(theme_name: Optional[str], custom_themes: Optional[Dict[str, Any]] = None) -> str:
    raw_theme = str(theme_name).strip() if theme_name else ""
    if not raw_theme:
        return "light"

    normalized_default = BACKWARD_COMPAT_THEME_ALIASES.get(raw_theme.lower(), raw_theme.lower())
    if normalized_default in DEFAULT_THEMES:
        return normalized_default

    if custom_themes:
        if raw_theme in custom_themes:
            return raw_theme
        if raw_theme.lower() in custom_themes:
            return raw_theme.lower()

    return "light"


def normalize_atmosphere_name(atmosphere: Optional[str]) -> Optional[str]:
    if not atmosphere:
        return None

    normalized = str(atmosphere).strip().lower()
    return ATMOSPHERE_THEME_ALIASES.get(normalized, normalized)


def get_atmosphere_effects(atmosphere: Optional[str], explicit_effects: Optional[List[str]] = None) -> List[str]:
    if explicit_effects:
        return explicit_effects

    if not atmosphere:
        return []

    atmosphere_key = str(atmosphere).strip().lower()
    if atmosphere_key in ATMOSPHERE_EFFECT_PRESETS:
        return ATMOSPHERE_EFFECT_PRESETS[atmosphere_key]

    normalized = normalize_atmosphere_name(atmosphere_key)
    if normalized in ATMOSPHERE_THEMES:
        return ATMOSPHERE_THEMES[normalized].get("effects", [])

    return []

# 主题管理页面已移至 main.py 中的动态路由注册系统
# 这样可以根据 ADMIN_PATH 配置动态生成路由，提高安全性
async def admin_themes_page(request: Request, db: Session, current_user: User):
    """主题管理页面 - 供 main.py 动态路由调用"""
    templates = get_templates()
    # 获取当前主题设置
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
    atmosphere_setting = crud_setting.get_setting(db, key="current_atmosphere")
    auto_theme_setting = crud_setting.get_setting(db, key="auto_theme_enabled")
    theme_schedule_setting = crud_setting.get_setting(db, key="theme_schedule")
    background_setting = crud_setting.get_setting(db, key="background_image_settings")
    
    current_theme = normalize_theme_name(_extract_setting_value(theme_setting, "light"))
    custom_themes = custom_themes_setting.value.get("value") if custom_themes_setting else {}
    current_atmosphere, _ = parse_atmosphere_setting(atmosphere_setting)
    auto_theme_enabled = bool(_extract_setting_value(auto_theme_setting, False))
    theme_schedule = theme_schedule_setting.value.get("value") if theme_schedule_setting else []
    background_settings = background_setting.value.get("value") if background_setting else {"type": "none", "custom_url": None}
    
    # 获取纪念日设置
    anniversaries_setting = crud_setting.get_setting(db, key="anniversaries_json")
    anniversaries = []
    if anniversaries_setting and anniversaries_setting.value:
        try:
            anniversaries_json = anniversaries_setting.value.get("value") if isinstance(anniversaries_setting.value, dict) else anniversaries_setting.value
            anniversaries = json.loads(anniversaries_json) if isinstance(anniversaries_json, str) else anniversaries_json
        except:
            anniversaries = []
    
    # 创建settings对象
    settings = type('Settings', (), {
        'anniversaries': anniversaries,
        'background_image_settings': background_settings
    })()
    
    return templates.TemplateResponse("admin/themes.html", {
        "request": request,
        "user": current_user,
        "current_theme": current_theme,
        "default_themes": DEFAULT_THEMES,
        "custom_themes": custom_themes,
        "atmosphere_themes": ATMOSPHERE_THEMES,
        "current_atmosphere": current_atmosphere,
        "auto_theme_enabled": auto_theme_enabled,
        "theme_schedule": theme_schedule,
        "background_settings": background_settings,
        "settings": settings
    })

# 主题更新路由已移至 main.py 中的动态路由注册系统
async def update_theme_settings(
    request: Request,
    db: Session,
    current_user: User,
    current_theme: str,
    current_atmosphere: Optional[str],
    auto_theme_enabled: bool,
    csrf_token: str
):
    """更新主题设置"""
    verify_csrf_token(request, csrf_token)
    
    normalized_current_theme = normalize_theme_name(current_theme)

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
    
    # 更新氛围主题
    atmosphere_setting = crud_setting.get_setting(db, key="current_atmosphere")
    if atmosphere_setting:
        crud_setting.update_setting(db, key="current_atmosphere", setting_update=SettingUpdate(value={"value": current_atmosphere}))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(
            key="current_atmosphere",
            value={"value": current_atmosphere},
            description="当前氛围主题",
            category="theme"
        ))
    
    # 更新自动主题设置
    auto_setting = crud_setting.get_setting(db, key="auto_theme_enabled")
    if auto_setting:
        crud_setting.update_setting(db, key="auto_theme_enabled", setting_update=SettingUpdate(value={"value": auto_theme_enabled}))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(
            key="auto_theme_enabled",
            value={"value": auto_theme_enabled}, 
            description="是否启用自动主题切换",
            category="theme"
        ))
    
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
    current_user: User
):
    """删除自定义主题"""
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
    """更新主题调度设置"""
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
            description="主题自动调度配置",
            category="theme"
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
    """获取当前主题配置（前端API）"""
    # 获取当前主题设置
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    stored_theme = _extract_setting_value(theme_setting, "light")
    
    # 获取氛围主题
    atmosphere_setting = crud_setting.get_setting(db, key="current_atmosphere")
    current_atmosphere, current_effects = parse_atmosphere_setting(atmosphere_setting)
    
    # 检查是否有自动调度的主题
    if current_atmosphere is None:
        current_atmosphere = check_scheduled_atmosphere(db)
    normalized_atmosphere = normalize_atmosphere_name(current_atmosphere)
    current_effects = get_atmosphere_effects(current_atmosphere, current_effects)
    
    # 获取背景图片设置
    background_setting = crud_setting.get_setting(db, key="background_image_settings")
    background_settings = background_setting.value.get("value") if background_setting else {"type": "none", "custom_url": None}
    
    # 构建主题配置
    theme_variables: Dict[str, Any] = {}
    custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
    custom_themes = custom_themes_setting.value.get("value") if custom_themes_setting else {}
    current_theme = resolve_theme_name(stored_theme, custom_themes)
    
    # 基础主题变量
    if current_theme in DEFAULT_THEMES:
        theme_variables.update(DEFAULT_THEMES[current_theme]["variables"])
    else:
        if current_theme in custom_themes:
            theme_variables.update(custom_themes[current_theme]["variables"])
        else:
            # 默认回退到浅色主题
            theme_variables.update(DEFAULT_THEMES["light"]["variables"])
    
    # 氛围主题覆盖
    atmosphere_class = ""
    if normalized_atmosphere and normalized_atmosphere in ATMOSPHERE_THEMES:
        atmosphere_config = ATMOSPHERE_THEMES[normalized_atmosphere]
        theme_variables.update(atmosphere_config["variables"])
        atmosphere_class = atmosphere_config["css_class"]
    
    return JSONResponse({
        "theme": current_theme,
        "atmosphere": current_atmosphere,
        "normalized_atmosphere": normalized_atmosphere,
        "atmosphere_class": atmosphere_class,
        "atmosphere_effects": current_effects,
        "background": background_settings,
        "variables": theme_variables
    })

def check_scheduled_atmosphere(db: Session) -> Optional[str]:
    """检查是否有计划中的氛围主题"""
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
            atmosphere = item.get("atmosphere")
            if atmosphere:
                return str(atmosphere).strip().lower()
    
    return None

@router.get("/api/v1/theme/variables.css")
@router.get("/api/theme/variables.css")
async def theme_variables_css(request: Request, db: Session = Depends(get_db)):
    """动态生成CSS变量文件"""
    from fastapi.responses import Response
    
    # 获取当前主题配置
    theme_response = await get_current_theme(request, db)
    theme_data = json.loads(theme_response.body)
    
    # 构建CSS内容
    css_content = ":root {\n"
    for var_name, var_value in theme_data["variables"].items():
        css_content += f"    {var_name}: {var_value};\n"
    css_content += "}\n"
    
    # 添加氛围主题样式
    if theme_data["atmosphere_class"]:
        css_content += f"""
.{theme_data['atmosphere_class']} {{
    /* 氛围主题特殊样式 */
}}
"""
    
    return Response(content=css_content, media_type="text/css")

@router.post("/api/v1/theme/update")
@router.post("/api/theme/update")
async def update_theme_realtime(
    request: Request,
    theme: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """实时更新主题设置"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    # 验证主题是否存在
    normalized_default_theme = BACKWARD_COMPAT_THEME_ALIASES.get(str(theme).strip().lower(), str(theme).strip().lower())
    if normalized_default_theme not in DEFAULT_THEMES:
        custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
        custom_themes = custom_themes_setting.value.get("value") if custom_themes_setting else {}
        if theme not in custom_themes:
            raise HTTPException(status_code=400, detail="主题不存在")
        theme_to_save = theme
    else:
        theme_to_save = normalized_default_theme
    
    # 更新主题设置
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    if theme_setting:
        crud_setting.update_setting(db, key="current_theme", setting_update=SettingUpdate(value={"value": theme_to_save}))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(key="current_theme", value={"value": theme_to_save}))
    
    return JSONResponse({"success": True, "theme": theme_to_save})

@router.post("/api/v1/atmosphere/update")
@router.post("/api/atmosphere/update")
async def update_atmosphere_realtime(
    request: Request,
    atmosphere: Optional[str] = Form(None),
    effects: List[str] = Form([]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """实时更新氛围模式设置"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    # 验证氛围主题是否存在
    if atmosphere and atmosphere not in ATMOSPHERE_THEMES:
        raise HTTPException(status_code=400, detail="氛围主题不存在")
    
    # 更新氛围设置
    atmosphere_setting = crud_setting.get_setting(db, key="current_atmosphere")
    atmosphere_data = {
        "value": atmosphere,
        "effects": effects,
        "updated_at": datetime.now().isoformat()
    }
    
    if atmosphere_setting:
        crud_setting.update_setting(db, key="current_atmosphere", setting_update=SettingUpdate(value=atmosphere_data))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(key="current_atmosphere", value=atmosphere_data))
    
    return JSONResponse({"success": True, "atmosphere": atmosphere, "effects": effects})

@router.get("/api/v1/theme/sync")
@router.get("/api/theme/sync")
async def sync_theme_settings(request: Request, db: Session = Depends(get_db)):
    """同步主题设置 - 用于前端实时获取最新配置"""
    # 获取当前主题
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
    custom_themes = custom_themes_setting.value.get("value") if custom_themes_setting else {}
    current_theme = resolve_theme_name(_extract_setting_value(theme_setting, "light"), custom_themes)
    
    # 获取当前氛围
    atmosphere_setting = crud_setting.get_setting(db, key="current_atmosphere")
    current_atmosphere, current_effects = parse_atmosphere_setting(atmosphere_setting)
    if current_atmosphere is None:
        current_atmosphere = check_scheduled_atmosphere(db)
    current_effects = get_atmosphere_effects(current_atmosphere, current_effects)
    normalized_atmosphere = normalize_atmosphere_name(current_atmosphere)

    atmosphere_payload = None
    if current_atmosphere:
        atmosphere_payload = {
            "value": current_atmosphere,
            "normalized": normalized_atmosphere,
            "effects": current_effects
        }
    
    # 获取主页设置
    homepage_setting = crud_setting.get_setting(db, key="homepage_mode")
    homepage_mode = homepage_setting.value.get("value") if homepage_setting else "default"
    
    # 获取背景图片设置
    background_setting = crud_setting.get_setting(db, key="background_image_settings")
    background_settings = background_setting.value.get("value") if background_setting else {"type": "none", "custom_url": None}
    
    return JSONResponse({
        "theme": current_theme,
        "atmosphere": atmosphere_payload,
        "homepage_mode": homepage_mode,
        "background": background_settings,
        "timestamp": datetime.now().isoformat()
    })
