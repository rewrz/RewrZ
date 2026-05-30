"""
评论设置API模块

提供评论系统和反垃圾评论系统的后台配置界面，包括：
1. 评论设置页面
2. 反垃圾三层防护配置
3. Akismet API配置
4. 验证码设置
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from ..core.admin_path import get_admin_path, get_request_admin_path
from ..core.database import get_db
from ..core.security import get_current_user, generate_csrf_token # 导入 generate_csrf_token
from ..core.template_filters import get_templates
from ..crud import setting as crud_setting
from ..schemas import User, SettingCreate, SettingUpdate
from ..core.akismet_client import get_akismet_client

router = APIRouter()
templates = get_templates()
ADMIN_PATH = get_admin_path()


def _checkbox_to_bool(raw_value: Optional[str]) -> bool:
    if raw_value is None:
        return False
    normalized = str(raw_value).strip().lower()
    return normalized in {"1", "true", "on", "yes", "checked"}


# 评论设置页面已移至 main.py 中的动态路由注册系统
async def comment_settings_page(
    request: Request,
    db: Session,
    current_user: User
):
    """
    评论设置页面
    
    显示评论系统和反垃圾配置界面
    """
    # 获取所有反垃圾相关设置
    comment_settings = {}
    
    # 第一层设置
    comment_settings['honeypot_enabled'] = crud_setting.get_setting(db, "anti_spam_honeypot_enabled")
    comment_settings['time_threshold'] = crud_setting.get_setting(db, "anti_spam_time_threshold")
    
    # 第二层设置
    comment_settings['max_links'] = crud_setting.get_setting(db, "anti_spam_max_links")
    comment_settings['keyword_filter'] = crud_setting.get_setting(db, "anti_spam_keyword_filter")
    comment_settings['keywords'] = crud_setting.get_setting(db, "anti_spam_keywords")
    comment_settings['akismet_enabled'] = crud_setting.get_setting(db, "anti_spam_akismet_enabled")
    comment_settings['akismet_key'] = crud_setting.get_setting(db, "anti_spam_akismet_key")
    
    # 第三层设置
    comment_settings['captcha_enabled'] = crud_setting.get_setting(db, "anti_spam_captcha_enabled")
    comment_settings['captcha_threshold'] = crud_setting.get_setting(db, "anti_spam_captcha_threshold")
    
    # 动作设置
    comment_settings['moderate_threshold'] = crud_setting.get_setting(db, "anti_spam_moderate_threshold")
    comment_settings['block_threshold'] = crud_setting.get_setting(db, "anti_spam_block_threshold")
    
    # 转换为模板可用的格式
    settings_data = {}
    for key, setting in comment_settings.items():
        if setting:
            settings_data[key] = setting.value.get("value") if setting.value else None
        else:
            # 提供默认值
            default_values = {
                'honeypot_enabled': True,
                'time_threshold': 5,
                'max_links': 2,
                'keyword_filter': True,
                'keywords': ["优惠", "促销", "打折", "免费", "赚钱", "兼职", "代刷", "加QQ", "加微信"],
                'akismet_enabled': False,
                'akismet_key': "",
                'captcha_enabled': True,
                'captcha_threshold': 0.6,
                'moderate_threshold': 0.5,
                'block_threshold': 0.8
            }
            settings_data[key] = default_values.get(key)
    
    return templates.TemplateResponse("admin/comment_settings.html", {
        "request": request,
        "user": current_user,
        "settings": settings_data,
        "admin_path": get_request_admin_path(request),
        "csrf_token": generate_csrf_token # 将 csrf_token 函数传递给模板
    })


# 评论设置更新路由
@router.post(f"{ADMIN_PATH}/api/v1/comments/settings")
async def update_comment_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
    # 第一层：无感防御设置
    honeypot_enabled: Optional[str] = Form(None),
    time_threshold: int = Form(5),
    
    # 第二层：内容分析设置
    max_links: int = Form(2),
    keyword_filter: Optional[str] = Form(None),
    keywords: str = Form(""),  # 一行一个关键词
    akismet_enabled: Optional[str] = Form(None),
    akismet_key: str = Form(""),
    
    # 第三层：验证码设置
    captcha_enabled: Optional[str] = Form(None),
    captcha_threshold: float = Form(0.6),
    
    # 动作阈值设置
    moderate_threshold: float = Form(0.5),
    block_threshold: float = Form(0.8),
    
    csrf_token: str = Form(...)
):
    """
    更新评论设置
    
    保存所有反垃圾评论系统配置
    """
    from ..core.security import verify_csrf_token
    verify_csrf_token(request, csrf_token)

    honeypot_enabled_flag = _checkbox_to_bool(honeypot_enabled)
    keyword_filter_flag = _checkbox_to_bool(keyword_filter)
    akismet_enabled_flag = _checkbox_to_bool(akismet_enabled)
    captcha_enabled_flag = _checkbox_to_bool(captcha_enabled)
    normalized_akismet_key = (akismet_key or "").strip()
    
    # 验证设置
    errors = []
    
    # 验证时间阈值
    if time_threshold < 1 or time_threshold > 60:
        errors.append("时间阈值必须在1-60秒之间")
    
    # 验证链接数量
    if max_links < 0 or max_links > 10:
        errors.append("链接数量限制必须在0-10之间")
    
    # 验证阈值
    if not (0.0 <= captcha_threshold <= 1.0):
        errors.append("验证码阈值必须在0.0-1.0之间")
    if not (0.0 <= moderate_threshold <= 1.0):
        errors.append("审核阈值必须在0.0-1.0之间")
    if not (0.0 <= block_threshold <= 1.0):
        errors.append("阻止阈值必须在0.0-1.0之间")
    
    # 验证Akismet设置
    if akismet_enabled_flag:
        if not normalized_akismet_key:
            errors.append("启用 Akismet 前请填写 API 密钥并测试通过")
        else:
            site_url_setting = crud_setting.get_setting(db, "site_url")
            site_url = site_url_setting.value.get("value") if site_url_setting else "http://localhost"
            
            akismet_client = get_akismet_client(normalized_akismet_key, site_url)
            if akismet_client:
                try:
                    is_valid = await akismet_client.verify_key()
                    if not is_valid:
                        errors.append("Akismet API密钥无效，请先测试通过后再保存")
                except Exception as e:
                    errors.append(f"验证Akismet密钥时出错: {str(e)}")
            else:
                errors.append("无法创建Akismet客户端")
    
    if errors:
        return JSONResponse({
            "success": False,
            "error": "配置验证失败",
            "details": errors
        }, status_code=400)
    
    # 处理关键词列表
    keyword_list = []
    if keywords.strip():
        keyword_list = [kw.strip() for kw in keywords.split('\n') if kw.strip()]
    
    # 准备要更新的设置
    settings_to_update = {
        "anti_spam_honeypot_enabled": honeypot_enabled_flag,
        "anti_spam_time_threshold": time_threshold,
        "anti_spam_max_links": max_links,
        "anti_spam_keyword_filter": keyword_filter_flag,
        "anti_spam_keywords": keyword_list,
        "anti_spam_akismet_enabled": akismet_enabled_flag,
        "anti_spam_akismet_key": normalized_akismet_key,
        "anti_spam_captcha_enabled": captcha_enabled_flag,
        "anti_spam_captcha_threshold": captcha_threshold,
        "anti_spam_moderate_threshold": moderate_threshold,
        "anti_spam_block_threshold": block_threshold,
    }
    
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
                    description=f"反垃圾评论设置: {key}",
                    category="anti_spam",
                    type=_get_setting_type(value)
                )
                crud_setting.create_setting(db, setting_create)
        
        return JSONResponse({
            "success": True,
            "message": "评论设置已更新",
            "redirect_url": f"{get_request_admin_path(request)}/comment-settings"
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"保存设置失败: {str(e)}"
        }, status_code=500)


# Akismet测试路由
@router.get(f"{ADMIN_PATH}/api/v1/comments/test-akismet")
async def test_akismet_key(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    api_key: str = "",
):
    """
    测试Akismet API密钥
    
    验证提供的API密钥是否有效
    """
    if not api_key:
        return JSONResponse({
            "success": False,
            "error": "请提供API密钥"
        }, status_code=400)
    
    try:
        # 获取站点URL
        site_url_setting = crud_setting.get_setting(db, "site_url")
        site_url = site_url_setting.value.get("value") if site_url_setting else "http://localhost"
        
        # 创建Akismet客户端并验证
        akismet_client = get_akismet_client(api_key, site_url)
        if not akismet_client:
            return JSONResponse({
                "success": False,
                "error": "无法创建Akismet客户端"
            }, status_code=400)
        
        is_valid = await akismet_client.verify_key()
        
        return JSONResponse({
            "success": True,
            "valid": is_valid,
            "message": "API密钥有效" if is_valid else "API密钥无效"
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"验证失败: {str(e)}"
        }, status_code=500)


def _get_setting_type(value):
    """根据值确定设置类型"""
    if isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, list):
        return "array"
    else:
        return "string"
