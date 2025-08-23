"""
错误处理配置API模块

提供错误处理相关的配置接口，包括：
1. 错误页面配置
2. 性能优化选项
3. 错误日志设置
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..core.template_filters import get_templates
from ..core.database import get_db
from ..schemas import User
from ..core.security import get_current_user
from ..crud import setting as setting_crud
from ..core.config import settings
from typing import Optional
import json

router = APIRouter()
templates = get_templates()


@router.get("/error-settings", response_class=HTMLResponse)
async def error_settings_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    错误处理设置页面
    """
    # 获取当前错误处理配置
    error_config = setting_crud.get_setting(db, key="error_handling_config")
    current_config = error_config.value.get("value", {}) if error_config and error_config.value else {}
    
    return templates.TemplateResponse("admin/error_settings.html", {
        "request": request,
        "user": current_user,
        "admin_path": settings.ADMIN_PATH.rstrip('/'),
        "error_config": current_config
    })


@router.post("/error-settings")
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
    enable_error_caching: bool = Form(True),
    error_cache_duration: int = Form(3600),
    enable_error_logging: bool = Form(True),
    log_level: str = Form("INFO"),
    enable_performance_optimization: bool = Form(True),
    related_posts_cache_strategy: str = Form("aggressive"),
    reading_time_cache_duration: int = Form(7200),
    csrf_token: str = Form(...)
):
    """
    更新错误处理设置
    """
    # 验证CSRF令牌
    if not csrf_token or csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    # 构建配置数据
    config_data = {
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
    }
    
    # 保存配置
    setting_crud.update_setting(
        db, 
        key="error_handling_config", 
        value={"value": config_data}
    )
    
    return {"message": "错误处理配置已更新", "config": config_data}


def get_error_handling_config(db: Session) -> dict:
    """
    获取错误处理配置
    
    Args:
        db: 数据库会话
        
    Returns:
        dict: 错误处理配置
    """
    config = setting_crud.get_setting(db, key="error_handling_config")
    return config.value.get("value", {}) if config and config.value else {}


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