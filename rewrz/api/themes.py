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
from typing import Dict, Any, Optional, List
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

# 预定义主题配置
DEFAULT_THEMES = {
    "light": {
        "name": "浅色主题",
        "variables": {
            "--color-primary": "#4f46e5",
            "--color-secondary": "#6b7280", 
            "--color-background": "#f9fafb",
            "--color-text": "#1f2937",
            "--color-text-light": "#4b5563",
            "--color-border": "#e5e7eb",
            "--color-card-bg": "#ffffff"
        }
    },
    "dark": {
        "name": "深色主题",
        "variables": {
            "--color-primary": "#818cf8",
            "--color-secondary": "#9ca3af",
            "--color-background": "#1f2937",
            "--color-text": "#f9fafb", 
            "--color-text-light": "#d1d5db",
            "--color-border": "#374151",
            "--color-card-bg": "#374151"
        }
    },
    "nature": {
        "name": "自然主题",
        "variables": {
            "--color-primary": "#10b981",
            "--color-secondary": "#6b7280",
            "--color-background": "#f0fdf4",
            "--color-text": "#1f2937",
            "--color-text-light": "#4b5563",
            "--color-border": "#d1fae5",
            "--color-card-bg": "#ffffff"
        }
    },
    "ocean": {
        "name": "海洋主题",
        "variables": {
            "--color-primary": "#0ea5e9",
            "--color-secondary": "#6b7280",
            "--color-background": "#f0f9ff",
            "--color-text": "#1f2937",
            "--color-text-light": "#4b5563",
            "--color-border": "#bae6fd",
            "--color-card-bg": "#ffffff"
        }
    },
    "sunset": {
        "name": "夕阳主题",
        "variables": {
            "--color-primary": "#f97316",
            "--color-secondary": "#6b7280",
            "--color-background": "#fff7ed",
            "--color-text": "#1f2937",
            "--color-text-light": "#4b5563",
            "--color-border": "#fed7aa",
            "--color-card-bg": "#ffffff"
        }
    }
}

# 氛围主题配置
ATMOSPHERE_THEMES = {
    "festive": {
        "name": "节日氛围",
        "description": "春节、圣诞节等节日主题",
        "css_class": "atmosphere-festive",
        "variables": {
            "--color-primary": "#ef4444",
            "--color-secondary": "#fbbf24"
        }
    },
    "memorial": {
        "name": "纪念氛围", 
        "description": "纪念日、哀悼日等肃穆主题",
        "css_class": "atmosphere-memorial",
        "variables": {
            "--color-primary": "#6b7280",
            "--color-secondary": "#9ca3af"
        }
    },
    "celebration": {
        "name": "庆祝氛围",
        "description": "生日、周年等庆祝主题",
        "css_class": "atmosphere-celebration", 
        "variables": {
            "--color-primary": "#8b5cf6",
            "--color-secondary": "#f59e0b"
        }
    }
}

@router.get("/admin/themes", response_class=HTMLResponse)
async def admin_themes_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """主题管理页面"""
    templates = get_templates()
    # 获取当前主题设置
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
    atmosphere_setting = crud_setting.get_setting(db, key="current_atmosphere")
    auto_theme_setting = crud_setting.get_setting(db, key="auto_theme_enabled")
    theme_schedule_setting = crud_setting.get_setting(db, key="theme_schedule")
    
    current_theme = theme_setting.value.get("value") if theme_setting else "light"
    custom_themes = custom_themes_setting.value.get("value") if custom_themes_setting else {}
    current_atmosphere = atmosphere_setting.value.get("value") if atmosphere_setting else None
    auto_theme_enabled = auto_theme_setting.value.get("value") if auto_theme_setting else False
    theme_schedule = theme_schedule_setting.value.get("value") if theme_schedule_setting else []
    
    return templates.TemplateResponse("admin/themes.html", {
        "request": request,
        "user": current_user,
        "current_theme": current_theme,
        "default_themes": DEFAULT_THEMES,
        "custom_themes": custom_themes,
        "atmosphere_themes": ATMOSPHERE_THEMES,
        "current_atmosphere": current_atmosphere,
        "auto_theme_enabled": auto_theme_enabled,
        "theme_schedule": theme_schedule
    })

@router.post("/admin/themes/update")
async def update_theme_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_theme: str = Form(...),
    current_atmosphere: Optional[str] = Form(None),
    auto_theme_enabled: bool = Form(False),
    csrf_token: str = Form(...)
):
    """更新主题设置"""
    verify_csrf_token(request, csrf_token)
    
    # 更新当前主题
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    if theme_setting:
        crud_setting.update_setting(db, key="current_theme", setting_update=SettingUpdate(value={"value": current_theme}))
    else:
        crud_setting.create_setting(db, setting=SettingCreate(
            key="current_theme", 
            value={"value": current_theme}, 
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
    
    return JSONResponse({"success": True, "message": "主题设置已更新"})

@router.post("/admin/themes/custom")
async def create_custom_theme(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    theme_name: str = Form(...),
    theme_data: str = Form(...),
    csrf_token: str = Form(...)
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

@router.delete("/admin/themes/custom/{theme_name}")
async def delete_custom_theme(
    theme_name: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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

@router.post("/admin/themes/schedule")
async def update_theme_schedule(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    schedule_data: str = Form(...),
    csrf_token: str = Form(...)
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

@router.get("/api/theme/current")
async def get_current_theme(request: Request, db: Session = Depends(get_db)):
    """获取当前主题配置（前端API）"""
    # 获取当前主题设置
    theme_setting = crud_setting.get_setting(db, key="current_theme")
    current_theme = theme_setting.value.get("value") if theme_setting else "light"
    
    # 获取氛围主题
    atmosphere_setting = crud_setting.get_setting(db, key="current_atmosphere") 
    current_atmosphere = atmosphere_setting.value.get("value") if atmosphere_setting else None
    
    # 检查是否有自动调度的主题
    if current_atmosphere is None:
        current_atmosphere = check_scheduled_atmosphere(db)
    
    # 构建主题配置
    theme_config = {}
    
    # 基础主题变量
    if current_theme in DEFAULT_THEMES:
        theme_config.update(DEFAULT_THEMES[current_theme]["variables"])
    else:
        # 检查自定义主题
        custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
        custom_themes = custom_themes_setting.value.get("value") if custom_themes_setting else {}
        if current_theme in custom_themes:
            theme_config.update(custom_themes[current_theme]["variables"])
        else:
            # 默认回退到浅色主题
            theme_config.update(DEFAULT_THEMES["light"]["variables"])
    
    # 氛围主题覆盖
    atmosphere_class = ""
    if current_atmosphere and current_atmosphere in ATMOSPHERE_THEMES:
        atmosphere_config = ATMOSPHERE_THEMES[current_atmosphere]
        theme_config.update(atmosphere_config["variables"])
        atmosphere_class = atmosphere_config["css_class"]
    
    return JSONResponse({
        "theme": current_theme,
        "atmosphere": current_atmosphere,
        "atmosphere_class": atmosphere_class,
        "variables": theme_config
    })

def check_scheduled_atmosphere(db: Session) -> Optional[str]:
    """检查是否有计划中的氛围主题"""
    schedule_setting = crud_setting.get_setting(db, key="theme_schedule")
    if not schedule_setting:
        return None
        
    schedule = schedule_setting.value.get("value", [])
    today = date.today()
    
    for item in schedule:
        start_date = datetime.strptime(item["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(item["end_date"], "%Y-%m-%d").date()
        
        if start_date <= today <= end_date:
            return item.get("atmosphere")
    
    return None

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