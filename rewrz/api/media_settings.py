"""
媒体设置API模块

提供媒体配置管理的HTTP接口，包括：
1. 媒体设置页面
2. 媒体配置读取和更新
3. 文件上传安全配置
"""

import os
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.template_filters import get_templates
from ..core.media_config import get_media_settings_schema
from ..crud import setting as crud_setting
from ..schemas import User, SettingCreate, SettingUpdate
from ..core.template_context import DEFAULT_BASE_SETTINGS

router = APIRouter()
templates = get_templates()


# 媒体设置页面已移至 main.py 中的动态路由注册系统
async def media_settings_page(
    request: Request,
    db: Session,
    current_user: User
):
    """
    媒体设置页面
    
    显示媒体处理和上传安全配置界面
    """
    # 获取所有媒体相关设置
    media_settings = {}
    settings_schema = get_media_settings_schema()
    
    # 获取所有媒体设置的当前值
    all_settings = crud_setting.get_settings_by_category(db, "media")
    for setting in all_settings:
        media_settings[setting.key] = setting.value.get("value") if setting.value else None
    
    return templates.TemplateResponse("admin/media_settings.html", {
        "request": request,
        "user": current_user,
        "media_settings": media_settings,
        "settings_schema": settings_schema,
        "admin_path": getattr(request.state, 'admin_path', os.getenv('ADMIN_PATH', '/admin'))
    })


# 媒体设置更新路由已移至 main.py 中的动态路由注册系统
async def update_media_settings(
    request: Request,
    db: Session,
    current_user: User,
    # 图像处理设置
    media_image_quality: int = Form(85),
    media_max_image_size: int = Form(2048),
    media_enable_webp: bool = Form(False),
    media_auto_compress: bool = Form(False),
    
    # 缩略图设置
    media_generate_thumbnails: bool = Form(False),
    media_thumbnail_quality: int = Form(80),
    
    # 上传限制
    media_max_file_size: int = Form(52428800),  # 50MB
    
    # 文件格式配置
    media_allowed_image_formats: str = Form("jpg,jpeg,png,gif,bmp,webp,tiff"),
    media_allowed_video_formats: str = Form("mp4,avi,mov,wmv,flv,webm,mkv"),
    media_allowed_audio_formats: str = Form("mp3,wav,flac,aac,ogg,m4a"),
    media_allowed_document_formats: str = Form("pdf,doc,docx,txt,md"),
    
    # 安全设置
    media_extract_exif: bool = Form(False),
    media_remove_exif: bool = Form(False),
    
    # 高级功能
    media_enable_watermark: bool = Form(False),
    media_watermark_text: str = Form(DEFAULT_BASE_SETTINGS["site_title"]),
    media_watermark_opacity: float = Form(0.5),
    
    # 其他设置
    media_enable_responsive: bool = Form(False),
    media_progressive_jpeg: bool = Form(False),
    media_enable_cdn: bool = Form(False),
    media_cdn_url: str = Form(""),
    media_auto_cleanup: bool = Form(False),
    media_cleanup_days: int = Form(30),
    
    csrf_token: str = Form(...)
):
    """
    更新媒体设置
    
    保存所有媒体处理和安全配置
    """
    from ..core.security import verify_csrf_token
    verify_csrf_token(request, csrf_token)
    
    # 准备要更新的设置
    settings_to_update = {
        "media_image_quality": media_image_quality,
        "media_max_image_size": media_max_image_size,
        "media_enable_webp": media_enable_webp,
        "media_auto_compress": media_auto_compress,
        "media_generate_thumbnails": media_generate_thumbnails,
        "media_thumbnail_quality": media_thumbnail_quality,
        "media_max_file_size": media_max_file_size,
        "media_allowed_image_formats": media_allowed_image_formats,
        "media_allowed_video_formats": media_allowed_video_formats,
        "media_allowed_audio_formats": media_allowed_audio_formats,
        "media_allowed_document_formats": media_allowed_document_formats,
        "media_extract_exif": media_extract_exif,
        "media_remove_exif": media_remove_exif,
        "media_enable_watermark": media_enable_watermark,
        "media_watermark_text": media_watermark_text,
        "media_watermark_opacity": media_watermark_opacity,
        "media_enable_responsive": media_enable_responsive,
        "media_progressive_jpeg": media_progressive_jpeg,
        "media_enable_cdn": media_enable_cdn,
        "media_cdn_url": media_cdn_url,
        "media_auto_cleanup": media_auto_cleanup,
        "media_cleanup_days": media_cleanup_days,
    }
    
    # 验证文件格式配置
    format_errors = []
    
    # 验证图像格式
    image_formats = [fmt.strip().lower() for fmt in media_allowed_image_formats.split(',') if fmt.strip()]
    if not image_formats:
        format_errors.append("至少需要允许一种图像格式")
    
    # 验证文件大小限制
    if media_max_file_size < 1024 * 1024:  # 最小1MB
        format_errors.append("文件大小限制不能小于1MB")
    elif media_max_file_size > 500 * 1024 * 1024:  # 最大500MB
        format_errors.append("文件大小限制不能超过500MB")
    
    if format_errors:
        return JSONResponse({
            "success": False,
            "error": "配置验证失败",
            "details": format_errors
        }, status_code=400)
    
    try:
        # 更新每个设置
        for key, value in settings_to_update.items():
            setting = crud_setting.get_setting(db, key)
            if setting:
                # 更新现有设置
                setting_update = SettingUpdate(value={"value": value})
                crud_setting.update_setting(db, setting.id, setting_update)
            else:
                # 创建新设置
                setting_create = SettingCreate(
                    key=key,
                    value={"value": value},
                    description=f"媒体设置: {key}",
                    category="media",
                    type=_get_setting_type(value)
                )
                crud_setting.create_setting(db, setting_create)
        
        return JSONResponse({
            "success": True,
            "message": "媒体设置已更新",
            "redirect_url": f"{getattr(request.state, 'admin_path', '/admin')}/media/settings"
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"保存设置失败: {str(e)}"
        }, status_code=500)


# 获取当前媒体设置路由已移至 main.py 中的动态路由注册系统
async def get_current_media_settings(
    db: Session,
    current_user: User
):
    """
    获取当前媒体设置
    
    返回所有媒体相关的设置值
    """
    try:
        media_settings = {}
        all_settings = crud_setting.get_settings_by_category(db, "media")
        
        for setting in all_settings:
            media_settings[setting.key] = setting.value.get("value") if setting.value else None
        
        return JSONResponse({
            "success": True,
            "settings": media_settings
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"获取设置失败: {str(e)}"
        }, status_code=500)


def _get_setting_type(value):
    """根据值确定设置类型"""
    if isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "float"
    else:
        return "string"
