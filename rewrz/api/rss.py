"""
RSS订阅 API 模块

提供RSS/Atom订阅功能，支持：
1. 全站RSS订阅
2. 分类RSS订阅
3. 标签RSS订阅  
4. 格式RSS订阅
5. RSS配置管理
"""
import html
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..crud import post as crud_post
from ..crud import category as crud_category
from ..crud import tag as crud_tag
from ..crud import format as crud_format
from ..crud import setting as crud_setting
from ..models import Post
from ..core.template_context import DEFAULT_BASE_SETTINGS

router = APIRouter()

def check_rss_enabled(db: Session) -> bool:
    """检查RSS是否启用"""
    rss_enabled_setting = crud_setting.get_setting(db, key="rss_enabled")
    return rss_enabled_setting.value.get("value", True) if rss_enabled_setting and rss_enabled_setting.value else True

def get_rss_config(db: Session) -> dict:
    """获取RSS配置"""
    rss_items_limit_setting = crud_setting.get_setting(db, key="rss_items_limit")
    rss_cache_duration_setting = crud_setting.get_setting(db, key="rss_cache_duration")
    rss_description_setting = crud_setting.get_setting(db, key="rss_description")
    
    return {
        "items_limit": rss_items_limit_setting.value.get("value", 20) if rss_items_limit_setting and rss_items_limit_setting.value else 20,
        "cache_duration": rss_cache_duration_setting.value.get("value", 60) if rss_cache_duration_setting and rss_cache_duration_setting.value else 60,
        "description": rss_description_setting.value.get("value", "") if rss_description_setting and rss_description_setting.value else ""
    }

@router.get("/feed.xml")
async def rss_feed(request: Request, db: Session = Depends(get_db)):
    """
    全站RSS订阅源
    
    生成包含最新文章的RSS 2.0格式订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"])

@router.get("/rss.xml") 
async def rss_feed_alt(request: Request, db: Session = Depends(get_db)):
    """RSS订阅源（备用路径）"""
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"])

@router.get("/atom.xml")
async def atom_feed(request: Request, db: Session = Depends(get_db)):
    """
    Atom格式订阅源
    
    生成包含最新文章的Atom 1.0格式订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
    
    rss_config = get_rss_config(db)
    return generate_atom_feed(request, db, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"])

@router.get("/feed/category/{category_slug}")
async def category_rss_feed(category_slug: str, request: Request, db: Session = Depends(get_db)):
    """
    分类RSS订阅源
    
    生成指定分类的RSS订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
        
    category = crud_category.get_category_by_slug(db, slug=category_slug)
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, category=category, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"])

@router.get("/feed/tag/{tag_slug}")
async def tag_rss_feed(tag_slug: str, request: Request, db: Session = Depends(get_db)):
    """
    标签RSS订阅源
    
    生成指定标签的RSS订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
        
    tag = crud_tag.get_tag_by_slug(db, slug=tag_slug)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, tag=tag, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"])

@router.get("/feed/format/{format_slug}")
async def format_rss_feed(format_slug: str, request: Request, db: Session = Depends(get_db)):
    """
    格式RSS订阅源
    
    生成指定格式的RSS订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
        
    format_obj = crud_format.get_format_by_slug(db, slug=format_slug)
    if not format_obj:
        raise HTTPException(status_code=404, detail="格式不存在")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, format_obj=format_obj, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"])

def generate_rss_feed(
    request: Request,
    db: Session,
    category=None,
    tag=None,
    format_obj=None,
    limit: int = 20,
    cache_duration: int = 60
):
    """
    生成RSS 2.0格式的订阅源
    
    Args:
        request: FastAPI请求对象
        db: 数据库会话
        category: 分类筛选
        tag: 标签筛选
        format_obj: 格式筛选
        limit: 文章数量限制
        cache_duration: 缓存时间（分钟）
    """
    # 获取站点信息
    site_info = get_site_info(db, request)
    
    # 获取文章列表
    posts = get_filtered_posts(db, category, tag, format_obj, limit)
    
    # 构建RSS标题和描述
    if category:
        feed_title = f"{site_info['title']} - {category.name}"
        feed_description = f"{site_info['description']} - {category.name}分类"
        feed_link = f"{site_info['base_url']}/archives/by-category/{category.slug}"
    elif tag:
        feed_title = f"{site_info['title']} - {tag.name}"
        feed_description = f"{site_info['description']} - {tag.name}标签"
        feed_link = f"{site_info['base_url']}/archives/by-tag/{tag.slug}"
    elif format_obj:
        feed_title = f"{site_info['title']} - {format_obj.name}"
        feed_description = f"{site_info['description']} - {format_obj.name}格式"
        feed_link = f"{site_info['base_url']}/formats/{format_obj.slug}"
    else:
        feed_title = site_info['title']
        feed_description = site_info['description']
        feed_link = site_info['base_url']
    
    # 生成RSS XML
    rss_xml = generate_rss_xml(
        title=feed_title,
        description=feed_description,
        link=feed_link,
        posts=posts,
        site_info=site_info
    )
    
    return Response(
        content=rss_xml,
        media_type="application/rss+xml; charset=utf-8",
        headers={"Cache-Control": f"max-age={cache_duration * 60}"}  # 使用配置的缓存时间
    )

def generate_atom_feed(request: Request, db: Session, limit: int = 20, cache_duration: int = 60):
    """生成Atom 1.0格式的订阅源"""
    site_info = get_site_info(db, request)
    posts = get_filtered_posts(db, limit=limit)
    
    atom_xml = generate_atom_xml(
        title=site_info['title'],
        subtitle=site_info['description'],
        link=site_info['base_url'],
        posts=posts,
        site_info=site_info
    )
    
    return Response(
        content=atom_xml,
        media_type="application/atom+xml; charset=utf-8",
        headers={"Cache-Control": f"max-age={cache_duration * 60}"}  # 使用配置的缓存时间
    )

def get_site_info(db: Session, request: Request) -> dict:
    """获取站点信息"""
    # 获取站点设置
    site_title_setting = crud_setting.get_setting(db, key="site_title")
    tagline_setting = crud_setting.get_setting(db, key="tagline")
    site_url_setting = crud_setting.get_setting(db, key="site_url")
    admin_email_setting = crud_setting.get_setting(db, key="admin_email")
    rss_description_setting = crud_setting.get_setting(db, key="rss_description")
    
    title = site_title_setting.value.get("value") if site_title_setting and site_title_setting.value else DEFAULT_BASE_SETTINGS["site_title"]
    default_description = tagline_setting.value.get("value") if tagline_setting and tagline_setting.value else DEFAULT_BASE_SETTINGS["tagline"]
    # 如果设置了自定义RSS描述，则使用自定义描述，否则使用站点标语
    description = rss_description_setting.value.get("value") if rss_description_setting and rss_description_setting.value and rss_description_setting.value.get("value") else default_description
    base_url = site_url_setting.value.get("value") if site_url_setting and site_url_setting.value else str(request.base_url).rstrip('/')
    admin_email = admin_email_setting.value.get("value") if admin_email_setting and admin_email_setting.value else "admin@example.com"
    
    return {
        "title": title,
        "description": description,
        "base_url": base_url,
        "admin_email": admin_email
    }

def get_filtered_posts(
    db: Session,
    category=None,
    tag=None,
    format_obj=None,
    limit: int = 20
) -> List[Post]:
    """获取筛选后的文章列表"""
    # 获取已发布的文章
    posts = crud_post.get_posts(db, skip=0, limit=limit, status="published")
    
    # 应用筛选条件
    filtered_posts = []
    for post in posts:
        if category and category not in post.categories:
            continue
        if tag and tag not in post.tags:
            continue
        if format_obj and format_obj not in post.formats:
            continue
        filtered_posts.append(post)
    
    return filtered_posts[:limit]

def generate_rss_xml(title: str, description: str, link: str, posts: List[Post], site_info: dict) -> str:
    """生成RSS 2.0 XML"""
    now = datetime.now(timezone.utc)
    
    xml_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<channel>',
        f'<title>{html.escape(title)}</title>',
        f'<link>{html.escape(link)}</link>',
        f'<description>{html.escape(description)}</description>',
        f'<language>zh-cn</language>',
        f'<lastBuildDate>{now.strftime("%a, %d %b %Y %H:%M:%S %z")}</lastBuildDate>',
        f'<atom:link href="{site_info["base_url"]}/feed.xml" rel="self" type="application/rss+xml" />',
        f'<managingEditor>{site_info["admin_email"]} ({title})</managingEditor>',
        f'<webMaster>{site_info["admin_email"]}</webMaster>',
+        f'<generator>{html.escape(DEFAULT_BASE_SETTINGS["site_title"])}</generator>',
    ]
    
    # 添加文章项
    for post in posts:
        post_url = f'{site_info["base_url"]}/{post.formats[0].slug if post.formats else "article"}/{post.slug}'
        pub_date = post.published_at or post.created_at
        
        xml_lines.extend([
            '<item>',
            f'<title>{html.escape(post.title)}</title>',
            f'<link>{html.escape(post_url)}</link>',
            f'<description>{html.escape(post.excerpt or post.content_html[:500])}</description>',
            f'<guid isPermaLink="true">{html.escape(post_url)}</guid>',
            f'<pubDate>{pub_date.strftime("%a, %d %b %Y %H:%M:%S %z")}</pubDate>',
        ])
        
        # 添加分类信息
        for category in post.categories:
            xml_lines.append(f'<category>{html.escape(category.name)}</category>')
        
        xml_lines.append('</item>')
    
    xml_lines.extend([
        '</channel>',
        '</rss>'
    ])
    
    return '\n'.join(xml_lines)

def generate_atom_xml(title: str, subtitle: str, link: str, posts: List[Post], site_info: dict) -> str:
    """生成Atom 1.0 XML"""
    now = datetime.now(timezone.utc)
    
    xml_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f'<title>{html.escape(title)}</title>',
        f'<subtitle>{html.escape(subtitle)}</subtitle>',
        f'<link href="{html.escape(link)}" />',
        f'<link href="{site_info["base_url"]}/atom.xml" rel="self" />',
        f'<updated>{now.isoformat()}</updated>',
        f'<id>{site_info["base_url"]}/</id>',
        '<author>',
        f'<name>{html.escape(title)}</name>',
        f'<email>{site_info["admin_email"]}</email>',
        '</author>',
+        f'<generator>{html.escape(DEFAULT_BASE_SETTINGS["site_title"])}</generator>',
    ]
    
    # 添加文章项
    for post in posts:
        post_url = f'{site_info["base_url"]}/{post.formats[0].slug if post.formats else "article"}/{post.slug}'
        pub_date = post.published_at or post.created_at
        
        xml_lines.extend([
            '<entry>',
            f'<title>{html.escape(post.title)}</title>',
            f'<link href="{html.escape(post_url)}" />',
            f'<id>{html.escape(post_url)}</id>',
            f'<updated>{pub_date.isoformat()}</updated>',
            f'<summary>{html.escape(post.excerpt or post.content_html[:500])}</summary>',
            f'<content type="html">{html.escape(post.content_html)}</content>',
        ])
        
        # 添加分类信息
        for category in post.categories:
            xml_lines.append(f'<category term="{html.escape(category.slug)}" label="{html.escape(category.name)}" />')
        
        xml_lines.append('</entry>')
    
    xml_lines.extend([
        '</feed>'
    ])
    
    return '\n'.join(xml_lines)