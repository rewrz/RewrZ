from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi import APIRouter, Depends, Request, Form
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

router = APIRouter()
templates = get_templates()

@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    site_title_setting = crud_setting.get_setting(db, key="site_title")
    tagline_setting = crud_setting.get_setting(db, key="tagline")
    site_url_setting = crud_setting.get_setting(db, key="site_url")
    admin_email_setting = crud_setting.get_setting(db, key="admin_email")
    site_logo_light_setting = crud_setting.get_setting(db, key="site_logo_light")
    site_logo_dark_setting = crud_setting.get_setting(db, key="site_logo_dark")
    favicon_setting = crud_setting.get_setting(db, key="favicon")
    
    copyright_info_setting = crud_setting.get_setting(db, key="copyright_info")
    custom_footer_text_setting = crud_setting.get_setting(db, key="custom_footer_text")
    icp_beian_setting = crud_setting.get_setting(db, key="icp_beian")
    gongan_beian_setting = crud_setting.get_setting(db, key="gongan_beian")

    social_links_setting = crud_setting.get_setting(db, key="social_links")
    anniversaries_setting = crud_setting.get_setting(db, key="anniversaries")
    sitemap_enabled_setting = crud_setting.get_setting(db, key="sitemap_enabled")
    noindex_site_setting = crud_setting.get_setting(db, key="noindex_site")
    block_ai_crawlers_setting = crud_setting.get_setting(db, key="block_ai_crawlers")

    # RSS订阅设置
    rss_enabled_setting = crud_setting.get_setting(db, key="rss_enabled")
    rss_items_limit_setting = crud_setting.get_setting(db, key="rss_items_limit")
    rss_cache_duration_setting = crud_setting.get_setting(db, key="rss_cache_duration")
    rss_description_setting = crud_setting.get_setting(db, key="rss_description")

    # 页面显示配置设置
    homepage_posts_limit_setting = crud_setting.get_setting(db, key="homepage_posts_limit")
    archive_posts_limit_setting = crud_setting.get_setting(db, key="archive_posts_limit")
    search_results_limit_setting = crud_setting.get_setting(db, key="search_results_limit")
    related_posts_limit_setting = crud_setting.get_setting(db, key="related_posts_limit")

    settings_data = {
        "site_title": site_title_setting.value.get("value") if site_title_setting else "RewrZ",
        "tagline": tagline_setting.value.get("value") if tagline_setting else "A Personal Blog System",
        "site_url": site_url_setting.value.get("value") if site_url_setting else request.url.scheme + "://" + request.url.netloc,
        "admin_email": admin_email_setting.value.get("value") if admin_email_setting else current_user.email,
        "site_logo_light": site_logo_light_setting.value.get("value") if site_logo_light_setting else "",
        "site_logo_dark": site_logo_dark_setting.value.get("value") if site_logo_dark_setting else "",
        "favicon": favicon_setting.value.get("value") if favicon_setting else "",
        "copyright_info": copyright_info_setting.value.get("value") if copyright_info_setting else "&copy; {year} RewrZ. All rights reserved.",
        "custom_footer_text": custom_footer_text_setting.value.get("value") if custom_footer_text_setting else "",
        "icp_beian": icp_beian_setting.value.get("value") if icp_beian_setting else "",
        "gongan_beian": gongan_beian_setting.value.get("value") if gongan_beian_setting else "",
        "social_links": social_links_setting.value.get("value") if social_links_setting else [],
        "anniversaries": anniversaries_setting.value.get("value") if anniversaries_setting else [],
        "sitemap_enabled": sitemap_enabled_setting.value.get("value") if sitemap_enabled_setting else False,
        "noindex_site": noindex_site_setting.value.get("value") if noindex_site_setting else False,
        "block_ai_crawlers": block_ai_crawlers_setting.value.get("value") if block_ai_crawlers_setting else False,
        "rss_enabled": rss_enabled_setting.value.get("value") if rss_enabled_setting else True,
        "rss_items_limit": rss_items_limit_setting.value.get("value") if rss_items_limit_setting else 20,
        "rss_cache_duration": rss_cache_duration_setting.value.get("value") if rss_cache_duration_setting else 60,
        "rss_description": rss_description_setting.value.get("value") if rss_description_setting else "",
        "homepage_posts_limit": homepage_posts_limit_setting.value.get("value") if homepage_posts_limit_setting else 10,
        "archive_posts_limit": archive_posts_limit_setting.value.get("value") if archive_posts_limit_setting else 20,
        "search_results_limit": search_results_limit_setting.value.get("value") if search_results_limit_setting else 15,
        "related_posts_limit": related_posts_limit_setting.value.get("value") if related_posts_limit_setting else 5,
    }

    return templates.TemplateResponse("admin/settings.html", {
        "request": request, 
        "user": current_user, 
        "settings": settings_data,
        "admin_path": getattr(request.state, 'admin_path', os.getenv('ADMIN_PATH', '/admin'))
    })

@router.post("/admin/settings", response_class=HTMLResponse)
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
    noindex_site: bool = Form(False),
    block_ai_crawlers: bool = Form(False),
    rss_enabled: bool = Form(False),
    rss_items_limit: int = Form(20),
    rss_cache_duration: int = Form(60),
    rss_description: Optional[str] = Form(None),
    homepage_posts_limit: int = Form(10),
    archive_posts_limit: int = Form(20),
    search_results_limit: int = Form(15),
    related_posts_limit: int = Form(5),
    # 打赏功能相关参数
    donation_enabled: bool = Form(False),
    donation_title: str = Form('如果这篇文章对您有帮助，请考虑支持作者'),
    donation_description: str = Form('您的支持是我创作的动力！'),
    donation_qr_code_url: Optional[str] = Form(None),
    donation_link_text: Optional[str] = Form(None),
    donation_link_url: Optional[str] = Form(None),
    donation_style_theme: str = Form('elegant'),
    donation_show_position: str = Form('article_end'),
    csrf_token: str = Form(...),
):
    from ..core.security import verify_csrf_token
    verify_csrf_token(request, csrf_token)

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
        "social_links": json.loads(social_links_json),
        "anniversaries": json.loads(anniversaries_json),
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
        "related_posts_limit": related_posts_limit,
        # 打赏功能相关设置
        "donation_enabled": donation_enabled,
        "donation_title": donation_title,
        "donation_description": donation_description,
        "donation_qr_code_url": donation_qr_code_url or '',
        "donation_link_text": donation_link_text or '',
        "donation_link_url": donation_link_url or '',
        "donation_style_theme": donation_style_theme,
        "donation_show_position": donation_show_position,
    }

    for key, value in settings_to_update.items():
        db_setting = crud_setting.get_setting(db, key=key)
        if db_setting:
            crud_setting.update_setting(db, key=key, setting_update=SettingUpdate(value={"value": value}))
        else:
            crud_setting.create_setting(db, setting=SettingCreate(key=key, value={"value": value}, description=f"Global setting for {key.replace('_', ' ')}"))
    
    # Re-fetch settings to ensure the template gets the latest data
    site_title_setting = crud_setting.get_setting(db, key="site_title")
    tagline_setting = crud_setting.get_setting(db, key="tagline")
    site_url_setting = crud_setting.get_setting(db, key="site_url")
    admin_email_setting = crud_setting.get_setting(db, key="admin_email")
    site_logo_light_setting = crud_setting.get_setting(db, key="site_logo_light")
    site_logo_dark_setting = crud_setting.get_setting(db, key="site_logo_dark")
    favicon_setting = crud_setting.get_setting(db, key="favicon")
    
    copyright_info_setting = crud_setting.get_setting(db, key="copyright_info")
    custom_footer_text_setting = crud_setting.get_setting(db, key="custom_footer_text")
    icp_beian_setting = crud_setting.get_setting(db, key="icp_beian")
    gongan_beian_setting = crud_setting.get_setting(db, key="gongan_beian")

    social_links_setting = crud_setting.get_setting(db, key="social_links")
    anniversaries_setting = crud_setting.get_setting(db, key="anniversaries")
    sitemap_enabled_setting = crud_setting.get_setting(db, key="sitemap_enabled")
    noindex_site_setting = crud_setting.get_setting(db, key="noindex_site")
    block_ai_crawlers_setting = crud_setting.get_setting(db, key="block_ai_crawlers")

    # 重新获取RSS设置
    rss_enabled_setting = crud_setting.get_setting(db, key="rss_enabled")
    rss_items_limit_setting = crud_setting.get_setting(db, key="rss_items_limit")
    rss_cache_duration_setting = crud_setting.get_setting(db, key="rss_cache_duration")
    rss_description_setting = crud_setting.get_setting(db, key="rss_description")

    # 重新获取页面显示配置设置
    homepage_posts_limit_setting = crud_setting.get_setting(db, key="homepage_posts_limit")
    archive_posts_limit_setting = crud_setting.get_setting(db, key="archive_posts_limit")
    search_results_limit_setting = crud_setting.get_setting(db, key="search_results_limit")
    related_posts_limit_setting = crud_setting.get_setting(db, key="related_posts_limit")
    
    # 重新获取打赏功能相关设置
    donation_enabled_setting = crud_setting.get_setting(db, key="donation_enabled")
    donation_title_setting = crud_setting.get_setting(db, key="donation_title")
    donation_description_setting = crud_setting.get_setting(db, key="donation_description")
    donation_qr_code_url_setting = crud_setting.get_setting(db, key="donation_qr_code_url")
    donation_link_text_setting = crud_setting.get_setting(db, key="donation_link_text")
    donation_link_url_setting = crud_setting.get_setting(db, key="donation_link_url")
    donation_style_theme_setting = crud_setting.get_setting(db, key="donation_style_theme")
    donation_show_position_setting = crud_setting.get_setting(db, key="donation_show_position")

    settings_data = {
        "site_title": site_title_setting.value.get("value") if site_title_setting else "RewrZ",
        "tagline": tagline_setting.value.get("value") if tagline_setting else "A Personal Blog System",
        "site_url": site_url_setting.value.get("value") if site_url_setting else request.url.scheme + "://" + request.url.netloc,
        "admin_email": admin_email_setting.value.get("value") if admin_email_setting else current_user.email,
        "site_logo_light": site_logo_light_setting.value.get("value") if site_logo_light_setting else "",
        "site_logo_dark": site_logo_dark_setting.value.get("value") if site_logo_dark_setting else "",
        "favicon": favicon_setting.value.get("value") if favicon_setting else "",
        "copyright_info": copyright_info_setting.value.get("value") if copyright_info_setting else "&copy; {year} RewrZ. All rights reserved.",
        "custom_footer_text": custom_footer_text_setting.value.get("value") if custom_footer_text_setting else "",
        "icp_beian": icp_beian_setting.value.get("value") if icp_beian_setting else "",
        "gongan_beian": gongan_beian_setting.value.get("value") if gongan_beian_setting else "",
        "social_links": social_links_setting.value.get("value") if social_links_setting else [],
        "anniversaries": anniversaries_setting.value.get("value") if anniversaries_setting else [],
        "sitemap_enabled": sitemap_enabled_setting.value.get("value") if sitemap_enabled_setting else False,
        "noindex_site": noindex_site_setting.value.get("value") if noindex_site_setting else False,
        "block_ai_crawlers": block_ai_crawlers_setting.value.get("value") if block_ai_crawlers_setting else False,
        "rss_enabled": rss_enabled_setting.value.get("value") if rss_enabled_setting else True,
        "rss_items_limit": rss_items_limit_setting.value.get("value") if rss_items_limit_setting else 20,
        "rss_cache_duration": rss_cache_duration_setting.value.get("value") if rss_cache_duration_setting else 60,
        "rss_description": rss_description_setting.value.get("value") if rss_description_setting else "",
        "homepage_posts_limit": homepage_posts_limit_setting.value.get("value") if homepage_posts_limit_setting else 10,
        "archive_posts_limit": archive_posts_limit_setting.value.get("value") if archive_posts_limit_setting else 20,
        "search_results_limit": search_results_limit_setting.value.get("value") if search_results_limit_setting else 15,
        "related_posts_limit": related_posts_limit_setting.value.get("value") if related_posts_limit_setting else 5,
        # 打赏功能相关设置
        "donation_enabled": donation_enabled_setting.value.get("value") if donation_enabled_setting else False,
        "donation_title": donation_title_setting.value.get("value") if donation_title_setting else '如果这篇文章对您有帮助，请考虑支持作者',
        "donation_description": donation_description_setting.value.get("value") if donation_description_setting else '您的支持是我创作的动力！',
        "donation_qr_code_url": donation_qr_code_url_setting.value.get("value") if donation_qr_code_url_setting else '',
        "donation_link_text": donation_link_text_setting.value.get("value") if donation_link_text_setting else '',
        "donation_link_url": donation_link_url_setting.value.get("value") if donation_link_url_setting else '',
        "donation_style_theme": donation_style_theme_setting.value.get("value") if donation_style_theme_setting else 'elegant',
        "donation_show_position": donation_show_position_setting.value.get("value") if donation_show_position_setting else 'article_end',
    }

    return templates.TemplateResponse("admin/settings.html", {
        "request": request, 
        "user": current_user, 
        "settings": settings_data, 
        "message": "设置已保存！",
        "admin_path": getattr(request.state, 'admin_path', os.getenv('ADMIN_PATH', '/admin'))
    })

@router.post("/admin/api/update-admin-path")
async def update_admin_path(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新后台路径API端点"""
    try:
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
            
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "error": "无效的JSON数据"})
    except Exception as e:
        return JSONResponse({"success": False, "error": f"更新失败: {str(e)}"})
