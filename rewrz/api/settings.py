from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import get_current_user
from ..crud import setting as crud_setting
from ..schemas import Setting, SettingCreate, SettingUpdate, User
from fastapi.templating import Jinja2Templates
from ..core.template_filters import get_templates
from typing import List, Dict, Any, Optional
import json
import os
from datetime import datetime
from ..core.template_context import DEFAULT_HOMEPAGE_SETTINGS, DEFAULT_BASE_SETTINGS
import bleach

router = APIRouter()
templates = get_templates()

def _get_settings_data(db: Session, request: Request, current_user: User) -> Dict[str, Any]:
    """Helper function to fetch and structure settings data."""
    
    def get_setting_value(key: str, default: Any = None):
        """Safely get a setting value, handling missing or malformed data."""
        setting = crud_setting.get_setting(db, key=key)
        if setting and isinstance(setting.value, dict) and "value" in setting.value:
            return setting.value["value"]
        return default

    def parse_json_list(raw_value: Any, default: Optional[list] = None) -> Any:
        """Parse a setting value into a list, accepting JSON string or list."""
        fallback = default if default is not None else []
        if isinstance(raw_value, list):
            return raw_value
        if isinstance(raw_value, str):
            try:
                parsed = json.loads(raw_value)
                return parsed if isinstance(parsed, list) else fallback
            except json.JSONDecodeError:
                return fallback
        return fallback

    social_links = parse_json_list(get_setting_value("social_links", []), [])
    anniversaries = parse_json_list(get_setting_value("anniversaries", None), None)
    if not anniversaries:
        anniversaries = parse_json_list(get_setting_value("anniversaries_json", "[]"), [])

    settings_data = {
        "site_title": get_setting_value("site_title", DEFAULT_BASE_SETTINGS["site_title"]),
        "tagline": get_setting_value("tagline", DEFAULT_BASE_SETTINGS["tagline"]),
        "site_url": get_setting_value("site_url", str(request.base_url)),
        "admin_email": get_setting_value("admin_email", current_user.email),
        "site_logo_light": get_setting_value("site_logo_light", ""),
        "site_logo_dark": get_setting_value("site_logo_dark", ""),
        "favicon": get_setting_value("favicon", ""),
        "copyright_info": get_setting_value("copyright_info", f"&copy; {datetime.now().year} RewrZ. All rights reserved."),
        "custom_footer_text": get_setting_value("custom_footer_text", ""),
        "icp_beian": get_setting_value("icp_beian", ""),
        "gongan_beian": get_setting_value("gongan_beian", ""),
        "social_links": social_links,
        "anniversaries": anniversaries,
        "sitemap_enabled": get_setting_value("sitemap_enabled", False),
        "noindex_site": get_setting_value("noindex_site", DEFAULT_BASE_SETTINGS["noindex_site"]),
        "block_ai_crawlers": get_setting_value("block_ai_crawlers", DEFAULT_BASE_SETTINGS["block_ai_crawlers"]),
        "rss_enabled": get_setting_value("rss_enabled", True),
        "rss_items_limit": get_setting_value("rss_items_limit", 20),
        "rss_cache_duration": get_setting_value("rss_cache_duration", 60),
        "rss_description": get_setting_value("rss_description", ""),
        "homepage_posts_limit": get_setting_value("homepage_posts_limit", 10),
        "archive_posts_limit": get_setting_value("archive_posts_limit", 20),
        "search_results_limit": get_setting_value("search_results_limit", 15),
        "related_posts_limit": get_setting_value("related_posts_limit", 5),
        "list_navigation_mode": get_setting_value("list_navigation_mode", "pagination"),
        "content_primary_mode": get_setting_value("content_primary_mode", "markdown"),
        "donation_enabled": get_setting_value("donation_enabled", False),
        "donation_title": get_setting_value("donation_title", '如果这篇文章对您有帮助，请考虑支持作者'),
        "donation_description": get_setting_value("donation_description", '您的支持是我创作的动力！'),
        "donation_qr_code_url": get_setting_value("donation_qr_code_url", ''),
        "donation_link_text": get_setting_value("donation_link_text", ''),
        "donation_link_url": get_setting_value("donation_link_url", ''),
        "donation_style_theme": get_setting_value("donation_style_theme", 'elegant'),
        "donation_show_position": get_setting_value("donation_show_position", 'article_end'),
        # 主页个性化设置
        "homepage_mode": get_setting_value("homepage_mode", DEFAULT_HOMEPAGE_SETTINGS["homepage_mode"]),
        "homepage_background_image_url": get_setting_value("homepage_background_image_url", DEFAULT_HOMEPAGE_SETTINGS["homepage_background_image_url"]),
        "homepage_background_video_url": get_setting_value("homepage_background_video_url", DEFAULT_HOMEPAGE_SETTINGS["homepage_background_video_url"]),
        "homepage_background_music_url": get_setting_value("homepage_background_music_url", DEFAULT_HOMEPAGE_SETTINGS["homepage_background_music_url"]),
        "homepage_music_autoplay": get_setting_value("homepage_music_autoplay", DEFAULT_HOMEPAGE_SETTINGS["homepage_music_autoplay"]),
    }
    return settings_data

@router.get("/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    settings_data = _get_settings_data(db, request, current_user)
    
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, 
        "user": current_user, 
        "settings": settings_data,
        "admin_path": getattr(request.state, 'admin_path', os.getenv('ADMIN_PATH', '/admin'))
    })

@router.post("/settings", response_class=HTMLResponse)
async def update_admin_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_title: str = Form(...),
    tagline: str = Form(...),
    site_url: str = Form(...),
    admin_email: str = Form(...),
    site_logo_light: Optional[str] = Form(None),
    site_logo_dark: Optional[str] = Form(None),
    favicon: Optional[str] = Form(None),
    copyright_info: str = Form(...),
    custom_footer_text: Optional[str] = Form(None),
    icp_beian: Optional[str] = Form(None),
    gongan_beian: Optional[str] = Form(None),
    social_links_json: str = Form("[]"), # Expecting a JSON string for social links
    anniversaries_json: str = Form("[]"), # Expecting a JSON string for anniversaries
    sitemap_enabled: bool = Form(False),
    noindex_site: bool = Form(DEFAULT_BASE_SETTINGS["noindex_site"]),
    block_ai_crawlers: bool = Form(DEFAULT_BASE_SETTINGS["block_ai_crawlers"]),
    rss_enabled: bool = Form(False),
    rss_items_limit: int = Form(20),
    rss_cache_duration: int = Form(60),
    rss_description: Optional[str] = Form(None),
    homepage_posts_limit: int = Form(10),
    archive_posts_limit: int = Form(20),
    search_results_limit: int = Form(15),
    list_navigation_mode: str = Form("pagination"),
    related_posts_limit: int = Form(5),
    content_primary_mode: str = Form("markdown"),
    # 打赏功能相关参数
    donation_enabled: bool = Form(False),
    donation_title: str = Form('如果这篇文章对您有帮助，请考虑支持作者'),
    donation_description: str = Form('您的支持是我创作的动力！'),
    donation_qr_code_url: Optional[str] = Form(None),
    donation_link_text: Optional[str] = Form(None),
    donation_link_url: Optional[str] = Form(None),
    donation_style_theme: str = Form('elegant'),
    donation_show_position: str = Form('article_end'),
    # 主页个性化设置相关参数
    homepage_mode: str = Form(DEFAULT_HOMEPAGE_SETTINGS["homepage_mode"]),
    homepage_background_image_url: Optional[str] = Form(None),
    homepage_background_video_url: Optional[str] = Form(None),
    homepage_background_music_url: Optional[str] = Form(None),
    homepage_music_autoplay: bool = Form(DEFAULT_HOMEPAGE_SETTINGS["homepage_music_autoplay"]),
    csrf_token: str = Form(...),
):
    from ..core.security import verify_csrf_token
    verify_csrf_token(request, csrf_token)

    try:
        social_links = json.loads(social_links_json)
        anniversaries = json.loads(anniversaries_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for social links or anniversaries.")

    # Sanitize custom footer HTML to prevent XSS while allowing basic formatting and links
    if custom_footer_text:
        allowed_tags = [
            'a', 'strong', 'em', 'code', 'br', 'span', 'p', 'ul', 'ol', 'li', 'small', 'i', 'b', 'u'
        ]
        allowed_attributes = {
            'a': ['href', 'title', 'target', 'rel'],
            'span': ['class'],
            'p': ['class'],
            'i': ['class']
        }
        custom_footer_text = bleach.clean(
            custom_footer_text,
            tags=allowed_tags,
            attributes=allowed_attributes,
            strip=True
        )
    else:
        custom_footer_text = ''

    normalized_list_navigation_mode = (
        list_navigation_mode if list_navigation_mode in {"pagination", "ajax", "infinite_scroll"} else "pagination"
    )

    settings_to_update = {
        "site_title": site_title,
        "tagline": tagline,
        "site_url": site_url,
        "admin_email": admin_email,
        "site_logo_light": site_logo_light,
        "site_logo_dark": site_logo_dark,
        "favicon": favicon,
        "copyright_info": copyright_info,
        "custom_footer_text": custom_footer_text,
        "icp_beian": icp_beian,
        "gongan_beian": gongan_beian,
        "social_links": social_links,
        "anniversaries_json": anniversaries_json,  # 保存原始JSON字符串
        "anniversaries": anniversaries,  # 保存解析后的数据（向后兼容）
        "sitemap_enabled": sitemap_enabled,
        "noindex_site": noindex_site,
        "block_ai_crawlers": block_ai_crawlers,
        "rss_enabled": rss_enabled,
        "rss_items_limit": rss_items_limit,
        "rss_cache_duration": rss_cache_duration,
        "rss_description": rss_description,
        "homepage_posts_limit": homepage_posts_limit,
        "archive_posts_limit": archive_posts_limit,
        "search_results_limit": search_results_limit,
        "list_navigation_mode": normalized_list_navigation_mode,
        "related_posts_limit": related_posts_limit,
        "content_primary_mode": content_primary_mode if content_primary_mode in {"markdown", "html"} else "markdown",
        "donation_enabled": donation_enabled,
        "donation_title": donation_title,
        "donation_description": donation_description,
        "donation_qr_code_url": donation_qr_code_url or '',
        "donation_link_text": donation_link_text or '',
        "donation_link_url": donation_link_url or '',
        "donation_style_theme": donation_style_theme,
        "donation_show_position": donation_show_position,
        # 主页个性化设置
        "homepage_mode": homepage_mode,
        "homepage_background_image_url": homepage_background_image_url or '',
        "homepage_background_video_url": homepage_background_video_url or '',
        "homepage_background_music_url": homepage_background_music_url or '',
        "homepage_music_autoplay": homepage_music_autoplay,
    }

    for key, value in settings_to_update.items():
        db_setting = crud_setting.get_setting(db, key=key)
        update_payload = {"value": value}
        if db_setting:
            crud_setting.update_setting(db, key=key, setting_update=SettingUpdate(value=update_payload))
        else:
            crud_setting.create_setting(db, setting=SettingCreate(key=key, value=update_payload, description=f"Global setting for {key.replace('_', ' ')}"))
    
    # Re-fetch settings using the helper function to ensure the template gets the latest data
    settings_data = _get_settings_data(db, request, current_user)

    return templates.TemplateResponse("admin/settings.html", {
        "request": request, 
        "user": current_user, 
        "settings": settings_data, 
        "message": "设置已保存！",
        "admin_path": getattr(request.state, 'admin_path', os.getenv('ADMIN_PATH', '/admin'))
    })

@router.post("/api/v1/update-admin-path")
@router.post("/api/update-admin-path")
async def update_admin_path(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新后台路径API端点"""
    try:
        from ..core.security import verify_csrf_token

        csrf_token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
        if not csrf_token:
            return JSONResponse({"success": False, "error": "CSRF token missing"}, status_code=403)
        verify_csrf_token(request, csrf_token)

        # 解析JSON请求体
        body = await request.json()
        path_type = body.get("path_type", "random")
        
        # 导入后台路径生成器
        from ..core.admin_path_generator import generate_admin_path, validate_admin_path
        
        # 根据路径类型生成新路径
        if path_type == "custom":
            custom_path = body.get("custom_path", "")
            is_valid, error_msg = validate_admin_path(custom_path)
            if not is_valid:
                return JSONResponse({"success": False, "error": error_msg})
            new_path = custom_path
        elif path_type == "brand":
            brand_name = body.get("brand_name", "rewrz")
            new_path = generate_admin_path("brand", brand=brand_name)
        elif path_type == "random":
            random_length = body.get("random_length", 8)
            new_path = generate_admin_path("classic", random_length=random_length)
        else:
            return JSONResponse({"success": False, "error": "无效的路径类型"})
        
        # 确保路径以/开头且不以/结尾
        if not new_path.startswith("/"):
            new_path = "/" + new_path
        if new_path.endswith("/") and len(new_path) > 1:
            new_path = new_path.rstrip("/")
        
        # 更新.env文件
        env_file_path = ".env"
        if os.path.exists(env_file_path):
            # 读取现有的.env文件内容
            with open(env_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # 更新ADMIN_PATH变量
            admin_path_updated = False
            for i, line in enumerate(lines):
                if line.strip().startswith("ADMIN_PATH="):
                    lines[i] = f"ADMIN_PATH={new_path}\n"
                    admin_path_updated = True
                    break
            
            # 如果没有找到ADMIN_PATH变量，添加到文件末尾
            if not admin_path_updated:
                if not lines or not lines[-1].endswith("\n"):
                    lines.append("\n")
                lines.append(f"ADMIN_PATH={new_path}\n")
            
            # 写回.env文件
            with open(env_file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            
            # 更新环境变量（需要重启应用才能生效）
            os.environ["ADMIN_PATH"] = new_path
            
            return JSONResponse({
                "success": True, 
                "new_path": new_path,
                "message": "后台路径已成功更新"
            })
        else:
            return JSONResponse({"success": False, "error": ".env文件不存在"})
            
    except HTTPException as e:
        return JSONResponse({"success": False, "error": str(e.detail)}, status_code=e.status_code)
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "error": "无效的JSON数据"})
    except Exception as e:
        return JSONResponse({"success": False, "error": f"更新失败: {str(e)}"})
