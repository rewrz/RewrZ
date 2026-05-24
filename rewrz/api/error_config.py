"""
错误处理配置API模块

提供错误处理相关的配置接口，包括：
1. 错误页面配置
2. 性能优化选项
3. 错误日志设置
"""

from copy import deepcopy
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..core.template_filters import get_templates
from ..core.database import get_db
from ..schemas import User, SettingCreate, SettingUpdate
from ..core.security import get_current_user, verify_csrf_token
from ..crud import setting as setting_crud
from ..core.config import settings
from typing import Optional, Dict, Any

router = APIRouter()
templates = get_templates()

DEFAULT_ERROR_CONFIG: Dict[str, Any] = {
    "enable_custom_error_pages": False,
    "error_page_template": "default",
    "custom_error_messages": {
        "404": {"title": "页面未找到", "message": "抱歉，您访问的页面不存在。"},
        "500": {"title": "服务器内部错误", "message": "抱歉，服务器遇到了一些问题，请稍后再试。"},
        "403": {"title": "访问被禁止", "message": "抱歉，您没有权限访问此页面。"},
        "400": {"title": "请求错误", "message": "抱歉，您的请求存在问题，请检查后重试。"},
    },
    "enable_error_caching": True,
    "error_cache_duration": 3600,
    "enable_error_logging": True,
    "log_level": "INFO",
    "enable_performance_optimization": True,
    "related_posts_cache_strategy": "aggressive",
    "reading_time_cache_duration": 7200,
}

ALLOWED_ERROR_PAGE_TEMPLATES = {"default", "minimal", "detailed", "friendly"}
ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
ALLOWED_CACHE_STRATEGIES = {"aggressive", "moderate", "conservative"}


def _merge_error_config(saved_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """深度合并错误处理配置，确保模板渲染所需字段完整。"""
    merged = deepcopy(DEFAULT_ERROR_CONFIG)
    if not isinstance(saved_config, dict):
        return merged

    for key, value in saved_config.items():
        if key == "custom_error_messages" and isinstance(value, dict):
            for status_code, msg_data in value.items():
                if status_code not in merged["custom_error_messages"] or not isinstance(msg_data, dict):
                    continue
                merged["custom_error_messages"][status_code].update({
                    "title": msg_data.get("title", merged["custom_error_messages"][status_code]["title"]),
                    "message": msg_data.get("message", merged["custom_error_messages"][status_code]["message"]),
                })
        else:
            merged[key] = value
    return merged


def _normalize_error_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """校验并规范化配置值，避免非法参数写入数据库。"""
    normalized = _merge_error_config(config_data)

    if normalized["error_page_template"] not in ALLOWED_ERROR_PAGE_TEMPLATES:
        normalized["error_page_template"] = DEFAULT_ERROR_CONFIG["error_page_template"]

    normalized["log_level"] = str(normalized.get("log_level", "INFO")).upper()
    if normalized["log_level"] not in ALLOWED_LOG_LEVELS:
        normalized["log_level"] = DEFAULT_ERROR_CONFIG["log_level"]

    if normalized["related_posts_cache_strategy"] not in ALLOWED_CACHE_STRATEGIES:
        normalized["related_posts_cache_strategy"] = DEFAULT_ERROR_CONFIG["related_posts_cache_strategy"]

    try:
        normalized["error_cache_duration"] = max(60, min(int(normalized["error_cache_duration"]), 86400))
    except (TypeError, ValueError):
        normalized["error_cache_duration"] = DEFAULT_ERROR_CONFIG["error_cache_duration"]

    try:
        normalized["reading_time_cache_duration"] = max(60, min(int(normalized["reading_time_cache_duration"]), 86400))
    except (TypeError, ValueError):
        normalized["reading_time_cache_duration"] = DEFAULT_ERROR_CONFIG["reading_time_cache_duration"]

    return normalized


async def error_settings_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    错误处理设置页面
    """
    # 获取当前错误处理配置
    error_config_setting = setting_crud.get_setting(db, key="error_handling_config")
    saved_config = error_config_setting.value.get("value", {}) if error_config_setting and error_config_setting.value else {}
    config = _normalize_error_config(saved_config)

    return templates.TemplateResponse("admin/error_settings.html", {
        "request": request,
        "user": current_user,
        "admin_path": getattr(request.state, "admin_path", settings.ADMIN_PATH.rstrip('/')),
        "error_config": config,
        "message": None,
    })


async def update_error_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    enable_custom_error_pages: bool = Form(False),
    error_page_template: str = Form("default"),
    custom_error_404_title: str = Form("页面未找到"),
    custom_error_404_message: str = Form("抱歉，您访问的页面不存在。"),
    custom_error_500_title: str = Form("服务器内部错误"),
    custom_error_500_message: str = Form("抱歉，服务器遇到了一些问题，请稍后再试。"),
    custom_error_403_title: str = Form("访问被禁止"),
    custom_error_403_message: str = Form("抱歉，您没有权限访问此页面。"),
    custom_error_400_title: str = Form("请求错误"),
    custom_error_400_message: str = Form("抱歉，您的请求存在问题，请检查后重试。"),
    enable_error_caching: bool = Form(False),
    error_cache_duration: int = Form(3600),
    enable_error_logging: bool = Form(False),
    log_level: str = Form("INFO"),
    enable_performance_optimization: bool = Form(False),
    related_posts_cache_strategy: str = Form("aggressive"),
    reading_time_cache_duration: int = Form(7200),
    csrf_token: str = Form(...)
):
    """
    更新错误处理设置
    """
    verify_csrf_token(request, csrf_token)
    
    # 构建配置数据
    config_data = _normalize_error_config({
        "enable_custom_error_pages": enable_custom_error_pages,
        "error_page_template": error_page_template,
        "custom_error_messages": {
            "404": {
                "title": custom_error_404_title,
                "message": custom_error_404_message
            },
            "500": {
                "title": custom_error_500_title,
                "message": custom_error_500_message
            },
            "403": {
                "title": custom_error_403_title,
                "message": custom_error_403_message
            },
            "400": {
                "title": custom_error_400_title,
                "message": custom_error_400_message
            }
        },
        "enable_error_caching": enable_error_caching,
        "error_cache_duration": error_cache_duration,
        "enable_error_logging": enable_error_logging,
        "log_level": log_level,
        "enable_performance_optimization": enable_performance_optimization,
        "related_posts_cache_strategy": related_posts_cache_strategy,
        "reading_time_cache_duration": reading_time_cache_duration
    })

    # 保存配置（不存在则创建）
    existing_setting = setting_crud.get_setting(db, key="error_handling_config")
    if existing_setting:
        setting_crud.update_setting(
            db=db,
            key="error_handling_config",
            setting_update=SettingUpdate(value={"value": config_data}),
        )
    else:
        setting_crud.create_setting(
            db=db,
            setting=SettingCreate(
                key="error_handling_config",
                value={"value": config_data},
                description="错误处理配置",
            ),
        )

    return templates.TemplateResponse("admin/error_settings.html", {
        "request": request,
        "user": current_user,
        "admin_path": getattr(request.state, "admin_path", settings.ADMIN_PATH.rstrip('/')),
        "error_config": config_data,
        "message": "错误处理设置已保存",
    })


def get_error_handling_config(db: Session) -> dict:
    """
    获取错误处理配置
    
    Args:
        db: 数据库会话
        
    Returns:
        dict: 错误处理配置
    """
    config = setting_crud.get_setting(db, key="error_handling_config")
    raw = config.value.get("value", {}) if config and config.value else {}
    return _normalize_error_config(raw)


def is_custom_error_pages_enabled(db: Session) -> bool:
    """
    检查是否启用了自定义错误页面
    
    Args:
        db: 数据库会话
        
    Returns:
        bool: 是否启用自定义错误页面
    """
    config = get_error_handling_config(db)
    return config.get("enable_custom_error_pages", False)


def get_error_page_template(db: Session) -> str:
    """
    获取错误页面模板类型
    
    Args:
        db: 数据库会话
        
    Returns:
        str: 错误页面模板类型
    """
    config = get_error_handling_config(db)
    return config.get("error_page_template", "default")


def get_custom_error_message(db: Session, status_code: int) -> dict:
    """
    获取自定义错误消息
    
    Args:
        db: 数据库会话
        status_code: HTTP状态码
        
    Returns:
        dict: 自定义错误消息
    """
    config = get_error_handling_config(db)
    custom_messages = config.get("custom_error_messages", {})
    return custom_messages.get(str(status_code), {})


def is_error_caching_enabled(db: Session) -> bool:
    """
    检查是否启用了错误缓存
    
    Args:
        db: 数据库会话
        
    Returns:
        bool: 是否启用错误缓存
    """
    config = get_error_handling_config(db)
    return config.get("enable_error_caching", True)


def get_error_cache_duration(db: Session) -> int:
    """
    获取错误缓存持续时间
    
    Args:
        db: 数据库会话
        
    Returns:
        int: 缓存持续时间（秒）
    """
    config = get_error_handling_config(db)
    return config.get("error_cache_duration", 3600)


def is_error_logging_enabled(db: Session) -> bool:
    """
    检查是否启用了错误日志记录
    
    Args:
        db: 数据库会话
        
    Returns:
        bool: 是否启用错误日志记录
    """
    config = get_error_handling_config(db)
    return config.get("enable_error_logging", True)


def get_log_level(db: Session) -> str:
    """
    获取日志级别
    
    Args:
        db: 数据库会话
        
    Returns:
        str: 日志级别
    """
    config = get_error_handling_config(db)
    return config.get("log_level", "INFO")


def is_performance_optimization_enabled(db: Session) -> bool:
    """
    检查是否启用了性能优化
    
    Args:
        db: 数据库会话
        
    Returns:
        bool: 是否启用性能优化
    """
    config = get_error_handling_config(db)
    return config.get("enable_performance_optimization", True)


def get_related_posts_cache_strategy(db: Session) -> str:
    """
    获取相关文章缓存策略
    
    Args:
        db: 数据库会话
        
    Returns:
        str: 缓存策略
    """
    config = get_error_handling_config(db)
    return config.get("related_posts_cache_strategy", "aggressive")


def get_reading_time_cache_duration(db: Session) -> int:
    """
    获取阅读时间缓存持续时间
    
    Args:
        db: 数据库会话
        
    Returns:
        int: 缓存持续时间（秒）
    """
    config = get_error_handling_config(db)
    return config.get("reading_time_cache_duration", 7200)
