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
from ..core.content_access import strip_hide_blocks
from ..core.content_utils import get_effective_content_html, get_effective_plain_text
from ..core.time_utils import as_utc, utc_iso
from ..crud import setting as crud_setting
from ..models import Post
from ..core.template_context import DEFAULT_BASE_SETTINGS, normalize_rss_content_mode
from ..core.content_intents import choose_primary_intent_slug, to_public_post_segment

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
    rss_content_mode_setting = crud_setting.get_setting(db, key="rss_content_mode")
    
    return {
        "items_limit": rss_items_limit_setting.value.get("value", 20) if rss_items_limit_setting and rss_items_limit_setting.value else 20,
        "cache_duration": rss_cache_duration_setting.value.get("value", 60) if rss_cache_duration_setting and rss_cache_duration_setting.value else 60,
        "description": rss_description_setting.value.get("value", "") if rss_description_setting and rss_description_setting.value else "",
        "content_mode": normalize_rss_content_mode(
            rss_content_mode_setting.value.get("value")
            if rss_content_mode_setting and rss_content_mode_setting.value
            else DEFAULT_BASE_SETTINGS["rss_content_mode"]
        )
    }

@router.get("/feed.xml")
def rss_feed(request: Request, db: Session = Depends(get_db)):
    """
    全站RSS订阅源
    
    生成包含最新文章的RSS 2.0格式订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/rss.xml") 
def rss_feed_alt(request: Request, db: Session = Depends(get_db)):
    """RSS订阅源（备用路径）"""
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/atom.xml")
def atom_feed(request: Request, db: Session = Depends(get_db)):
    """
    Atom格式订阅源
    
    生成包含最新文章的Atom 1.0格式订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
    
    rss_config = get_rss_config(db)
    return generate_atom_feed(request, db, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/feed/category/{category_slug}")
def category_rss_feed(category_slug: str, request: Request, db: Session = Depends(get_db)):
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
    return generate_rss_feed(request, db, category=category, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/feed/tag/{tag_slug}")
def tag_rss_feed(tag_slug: str, request: Request, db: Session = Depends(get_db)):
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
    return generate_rss_feed(request, db, tag=tag, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/feed/format/{format_slug}")
def format_rss_feed(format_slug: str, request: Request, db: Session = Depends(get_db)):
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
    return generate_rss_feed(request, db, format_obj=format_obj, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

def generate_rss_feed(
    request: Request,
    db: Session,
    category=None,
    tag=None,
    format_obj=None,
    limit: int = 20,
    cache_duration: int = 60,
    content_mode: str = DEFAULT_BASE_SETTINGS["rss_content_mode"]
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
        site_info=site_info,
        content_mode=normalize_rss_content_mode(content_mode)
    )
    
    return Response(
        content=rss_xml,
        media_type="application/rss+xml; charset=utf-8",
        headers={"Cache-Control": f"max-age={cache_duration * 60}"}  # 使用配置的缓存时间
    )

def generate_atom_feed(
    request: Request,
    db: Session,
    limit: int = 20,
    cache_duration: int = 60,
    content_mode: str = DEFAULT_BASE_SETTINGS["rss_content_mode"]
):
    """生成Atom 1.0格式的订阅源"""
    site_info = get_site_info(db, request)
    posts = get_filtered_posts(db, limit=limit)
    
    atom_xml = generate_atom_xml(
        title=site_info['title'],
        subtitle=site_info['description'],
        link=site_info['base_url'],
        posts=posts,
        site_info=site_info,
        content_mode=normalize_rss_content_mode(content_mode)
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
    # 筛选条件必须下沉到查询，否则最新 N 篇之外的分类/标签/格式会得到空订阅源
    if category:
        return crud_post.get_posts_by_category(db, category_id=category.id, limit=limit)
    if tag:
        return crud_post.get_posts_by_tag(db, tag_id=tag.id, limit=limit)
    if format_obj:
        return crud_post.get_posts_by_format(db, format_id=format_obj.id, limit=limit)
    return crud_post.get_posts(
        db,
        skip=0,
        limit=limit,
        status="published",
        post_type="post",
    )

def _resolve_public_excerpt(post: Post, fallback_text: str) -> str:
    """RSS 摘要：剔除手写摘要中的评论后可见块，再回退到公开正文。"""
    excerpt = strip_hide_blocks(post.excerpt or "").strip()
    return excerpt or fallback_text


def _build_entry_title(post: Post, fallback_text: str) -> str:
    """RSS 条目标题：无标题内容用摘要兜底，避免订阅器出现空白标题。"""
    title = (post.title or "").strip()
    if title:
        return title
    candidate = _resolve_public_excerpt(post, fallback_text)
    candidate = " ".join(candidate.split())
    return candidate[:100] if candidate else "无标题"


def _resolve_public_content(post: Post) -> tuple[str, str]:
    """返回可公开分发的正文 HTML 与纯文本，剔除评论后可见块。"""
    raw_markdown = post.content_markdown or ""
    raw_html = post.content_html or ""
    public_markdown = strip_hide_blocks(raw_markdown)
    if public_markdown != raw_markdown:
        # 存在 [hide] 块时只使用清洗后的 Markdown，避免回退到含隐藏内容的 HTML
        return (
            get_effective_content_html(public_markdown, ""),
            get_effective_plain_text(public_markdown, ""),
        )
    return (
        get_effective_content_html(raw_markdown, raw_html),
        get_effective_plain_text(raw_markdown, raw_html),
    )


def generate_rss_xml(
    title: str,
    description: str,
    link: str,
    posts: List[Post],
    site_info: dict,
    content_mode: str = DEFAULT_BASE_SETTINGS["rss_content_mode"]
) -> str:
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
        f'<generator>{html.escape(DEFAULT_BASE_SETTINGS["site_title"])}</generator>',
    ]
    
    # 添加文章项
    for post in posts:
        format_slugs = [fmt.slug for fmt in post.formats if getattr(fmt, "slug", None)] if post.formats else []
        primary_intent = choose_primary_intent_slug(format_slugs)
        post_url = f'{site_info["base_url"]}/{to_public_post_segment(primary_intent)}/{post.slug}'
        pub_date = post.published_at or post.created_at
        public_html, public_text = _resolve_public_content(post)
        fallback_excerpt = public_text[:500]
        entry_title = _build_entry_title(post, fallback_excerpt)
        # 全文模式与 Atom 对齐，正文为空时回退到摘要
        item_description = public_html if content_mode == "full" and public_html else _resolve_public_excerpt(post, fallback_excerpt)
        
        xml_lines.extend([
            '<item>',
            f'<title>{html.escape(entry_title)}</title>',
            f'<link>{html.escape(post_url)}</link>',
            f'<description>{html.escape(item_description)}</description>',
            f'<guid isPermaLink="true">{html.escape(post_url)}</guid>',
            f'<pubDate>{as_utc(pub_date).strftime("%a, %d %b %Y %H:%M:%S %z")}</pubDate>',
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

def generate_atom_xml(
    title: str,
    subtitle: str,
    link: str,
    posts: List[Post],
    site_info: dict,
    content_mode: str = DEFAULT_BASE_SETTINGS["rss_content_mode"]
) -> str:
    """生成Atom 1.0 XML"""
    now = datetime.now(timezone.utc)
    
    xml_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f'<title>{html.escape(title)}</title>',
        f'<subtitle>{html.escape(subtitle)}</subtitle>',
        f'<link href="{html.escape(link)}" />',
        f'<link href="{site_info["base_url"]}/atom.xml" rel="self" />',
        f'<updated>{utc_iso(now)}</updated>',
        f'<id>{site_info["base_url"]}/</id>',
        '<author>',
        f'<name>{html.escape(title)}</name>',
        f'<email>{site_info["admin_email"]}</email>',
        '</author>',
        f'<generator>{html.escape(DEFAULT_BASE_SETTINGS["site_title"])}</generator>',
    ]
    
    # 添加文章项
    for post in posts:
        format_slugs = [fmt.slug for fmt in post.formats if getattr(fmt, "slug", None)] if post.formats else []
        primary_intent = choose_primary_intent_slug(format_slugs)
        post_url = f'{site_info["base_url"]}/{to_public_post_segment(primary_intent)}/{post.slug}'
        pub_date = post.published_at or post.created_at
        public_html, public_text = _resolve_public_content(post)
        fallback_excerpt = public_text[:500]
        entry_title = _build_entry_title(post, fallback_excerpt)
        
        entry_lines = [
            '<entry>',
            f'<title>{html.escape(entry_title)}</title>',
            f'<link href="{html.escape(post_url)}" />',
            f'<id>{html.escape(post_url)}</id>',
            f'<updated>{utc_iso(pub_date)}</updated>',
            f'<summary>{html.escape(_resolve_public_excerpt(post, fallback_excerpt))}</summary>',
        ]
        # 摘要模式不再输出全文 content；正文为空时同样退回摘要，与 RSS 保持一致
        if content_mode == "full" and public_html:
            entry_lines.append(f'<content type="html">{html.escape(public_html)}</content>')
        
        # 添加分类信息
        for category in post.categories:
            entry_lines.append(f'<category term="{html.escape(category.slug)}" label="{html.escape(category.name)}" />')
        
        entry_lines.append('</entry>')
        xml_lines.extend(entry_lines)
    
    xml_lines.extend([
        '</feed>'
    ])
    
    return '\n'.join(xml_lines)

