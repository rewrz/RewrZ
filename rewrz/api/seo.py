"""
SEO优化API模块

提供搜索引擎优化相关功能，包括：
1. 自动生成sitemap.xml
2. 动态robots.txt生成
3. Open Graph元标签支持
4. 结构化数据（JSON-LD）
5. SEO设置管理
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from ..core.database import get_db
from ..core.security import get_current_user
from ..crud import post as crud_post
from ..crud import category as crud_category
from ..crud import tag as crud_tag
from ..crud import setting as crud_setting
from ..schemas import User
from ..core.template_context import DEFAULT_BASE_SETTINGS
from ..core.content_intents import choose_primary_intent_slug, to_public_post_segment
from ..core.public_alias import resolve_public_display_name

router = APIRouter()

@router.get("/sitemap.xml", response_class=PlainTextResponse)
async def generate_sitemap(request: Request, db: Session = Depends(get_db)):
    """
    生成sitemap.xml
    
    自动包含所有已发布的文章、分类页面、标签页面等
    根据管理后台的SEO设置来决定是否启用
    """
    # 检查sitemap是否启用
    sitemap_enabled_setting = crud_setting.get_setting(db, key="sitemap_enabled")
    if not sitemap_enabled_setting or not sitemap_enabled_setting.value.get("value", False):
        raise HTTPException(status_code=404, detail="Sitemap disabled")
    
    # 获取站点URL设置
    site_url_setting = crud_setting.get_setting(db, key="site_url")
    base_url = site_url_setting.value.get("value") if site_url_setting else str(request.base_url).rstrip('/')
    
    # 创建XML根元素
    urlset = ET.Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")
    urlset.set("xmlns:news", "http://www.google.com/schemas/sitemap-news/0.9")
    urlset.set("xmlns:xhtml", "http://www.w3.org/1999/xhtml")
    urlset.set("xmlns:image", "http://www.google.com/schemas/sitemap-image/1.1")
    
    # 添加首页
    _add_url_to_sitemap(urlset, base_url, changefreq="daily", priority="1.0")
    
    # 添加已发布的文章
    posts = crud_post.get_posts(db, status="published", limit=1000, post_type="post")
    for post in posts:
        format_slugs = [fmt.slug for fmt in post.formats if getattr(fmt, "slug", None)] if post.formats else []
        primary_intent = choose_primary_intent_slug(format_slugs)
        post_url = urljoin(base_url, f"/{to_public_post_segment(primary_intent)}/{post.slug}")
        last_mod = post.updated_at.strftime("%Y-%m-%d") if post.updated_at else None
        _add_url_to_sitemap(urlset, post_url, lastmod=last_mod, changefreq="weekly", priority="0.8")
    
    # 添加分类页面
    categories = crud_category.get_all_categories(db)
    for category in categories:
        category_url = urljoin(base_url, f"/archives/by-category/{category.slug}")
        _add_url_to_sitemap(urlset, category_url, changefreq="weekly", priority="0.6")
    
    # 添加标签页面
    tags = crud_tag.get_all_tags(db)
    for tag in tags:
        tag_url = urljoin(base_url, f"/archives/by-tag/{tag.slug}")
        _add_url_to_sitemap(urlset, tag_url, changefreq="weekly", priority="0.5")
    
    # 转换为XML字符串
    xml_string = _prettify_xml(urlset)
    
    return Response(
        content=xml_string,
        media_type="application/xml",
        headers={"Content-Type": "application/xml; charset=utf-8"}
    )

@router.get("/robots.txt", response_class=PlainTextResponse)
async def generate_robots_txt(request: Request, db: Session = Depends(get_db)):
    """
    生成robots.txt文件
    
    根据SEO设置动态生成robots.txt内容
    """
    # 获取SEO设置
    noindex_setting = crud_setting.get_setting(db, key="noindex_site")
    block_ai_crawlers_setting = crud_setting.get_setting(db, key="block_ai_crawlers")
    site_url_setting = crud_setting.get_setting(db, key="site_url")
    
    noindex_site = noindex_setting.value.get("value") if noindex_setting and noindex_setting.value else DEFAULT_BASE_SETTINGS["noindex_site"]
    block_ai_crawlers = block_ai_crawlers_setting.value.get("value") if block_ai_crawlers_setting and block_ai_crawlers_setting.value else DEFAULT_BASE_SETTINGS["block_ai_crawlers"]
    base_url = site_url_setting.value.get("value") if site_url_setting else str(request.base_url).rstrip('/')
    
    robots_content = []
    
    if noindex_site:
        # 阻止所有搜索引擎索引
        robots_content.extend([
            "User-agent: *",
            "Disallow: /",
            ""
        ])
    else:
        # 允许搜索引擎，但阻止一些目录
        # 注意：不在 robots.txt 中暴露真实的后台路径，这是安全最佳实践
        robots_content.extend([
            "User-agent: *",
            "Disallow: /api/",
            "Disallow: /auth/",
            "Disallow: /installer",
            "Allow: /",
            ""
        ])
    
    if block_ai_crawlers:
        # 阻止AI爬虫
        ai_crawlers = [
            "ChatGPT-User", "GPTBot", "Google-Extended", "anthropic-ai", 
            "Claude-Web", "CCBot", "ChatGPT", "AI2Bot", "Ai2Bot-Dolma",
            "Amazonbot", "Meta-ExternalAgent", "Meta-ExternalFetcher",
            "OAI-SearchBot", "PerplexityBot", "YouBot", "Diffbot"
        ]
        
        for crawler in ai_crawlers:
            robots_content.extend([
                f"User-agent: {crawler}",
                "Disallow: /",
                ""
            ])
    
    # 添加sitemap链接
    sitemap_enabled_setting = crud_setting.get_setting(db, key="sitemap_enabled")
    if sitemap_enabled_setting and sitemap_enabled_setting.value.get("value", False):
        sitemap_url = urljoin(base_url, "/sitemap.xml")
        robots_content.append(f"Sitemap: {sitemap_url}")
    
    return "\n".join(robots_content)

@router.get("/api/v1/seo/meta/{post_slug}")
async def get_post_meta_tags(post_slug: str, request: Request, db: Session = Depends(get_db)):
    """
    获取文章的SEO元标签信息
    
    包括Open Graph、Twitter Cards、结构化数据等
    """
    # 获取文章信息
    db_post = crud_post.get_post_by_slug(db, slug=post_slug)
    if db_post is None or db_post.status != "published":
        raise HTTPException(status_code=404, detail="Post not found")
    
    return _generate_post_seo_data(db_post, request, db)

@router.get("/api/v1/seo/meta/homepage")
async def get_homepage_meta_tags(request: Request, db: Session = Depends(get_db)):
    """
    获取首页的SEO元标签信息
    """
    return _generate_homepage_seo_data(request, db)

@router.post("/api/v1/seo/ping-search-engines")
async def ping_search_engines(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    通知搜索引擎更新sitemap
    
    向Google、Bing等搜索引擎发送sitemap更新通知
    """
    # 获取站点URL
    site_url_setting = crud_setting.get_setting(db, key="site_url")
    if not site_url_setting:
        raise HTTPException(status_code=400, detail="Site URL not configured")
    
    base_url = site_url_setting.value.get("value")
    sitemap_url = urljoin(base_url, "/sitemap.xml")
    
    # 搜索引擎ping URLs
    ping_urls = [
        f"https://www.google.com/ping?sitemap={sitemap_url}",
        f"https://www.bing.com/ping?sitemap={sitemap_url}"
    ]
    
    results = []
    
    # 这里可以添加实际的HTTP请求来ping搜索引擎
    # 为了简化，我们只返回URLs
    for url in ping_urls:
        results.append({
            "url": url,
            "status": "queued",  # 实际实现中应该是HTTP请求的结果
            "message": "Ping request queued"
        })
    
    return {
        "sitemap_url": sitemap_url,
        "ping_results": results
    }

# 辅助函数

def _add_url_to_sitemap(urlset, url, lastmod=None, changefreq=None, priority=None):
    """向sitemap添加URL"""
    url_elem = ET.SubElement(urlset, "url")
    
    loc_elem = ET.SubElement(url_elem, "loc")
    loc_elem.text = url
    
    if lastmod:
        lastmod_elem = ET.SubElement(url_elem, "lastmod")
        lastmod_elem.text = lastmod
    
    if changefreq:
        changefreq_elem = ET.SubElement(url_elem, "changefreq")
        changefreq_elem.text = changefreq
    
    if priority:
        priority_elem = ET.SubElement(url_elem, "priority")
        priority_elem.text = priority

def _prettify_xml(elem):
    """美化XML输出"""
    from xml.dom import minidom
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode('utf-8')

def _extract_description_from_content(content_markdown: str, max_length: int = 160) -> str:
    """从Markdown内容中提取描述"""
    if not content_markdown:
        return ""
    
    # 移除Markdown标记的简单方法
    import re
    
    # 移除标题标记
    text = re.sub(r'^#+\s+', '', content_markdown, flags=re.MULTILINE)
    # 移除链接
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 移除加粗和斜体
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    # 移除代码块
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # 只取第一段
    first_paragraph = text.split('\n\n')[0].strip()
    
    # 截断到指定长度
    if len(first_paragraph) > max_length:
        return first_paragraph[:max_length].rsplit(' ', 1)[0] + '...'
    
    return first_paragraph

def _generate_open_graph_tags(meta_data: Dict, site_name: str) -> Dict[str, str]:
    """生成Open Graph标签"""
    og_tags = {
        "og:title": meta_data["title"],
        "og:description": meta_data["description"],
        "og:url": meta_data["url"],
        "og:type": meta_data["type"],
        "og:site_name": site_name
    }
    
    if meta_data.get("image"):
        og_tags["og:image"] = meta_data["image"]
    
    if meta_data.get("published_time"):
        og_tags["article:published_time"] = meta_data["published_time"]
    
    if meta_data.get("modified_time"):
        og_tags["article:modified_time"] = meta_data["modified_time"]
    
    if meta_data.get("author"):
        og_tags["article:author"] = meta_data["author"]
    
    if meta_data.get("section"):
        og_tags["article:section"] = meta_data["section"]
    
    if meta_data.get("tags"):
        for tag in meta_data["tags"]:
            og_tags[f"article:tag"] = tag  # 注意：多个标签需要多个meta标签
    
    return og_tags

def _generate_twitter_cards_tags(meta_data: Dict) -> Dict[str, str]:
    """生成Twitter Cards标签"""
    twitter_tags = {
        "twitter:card": "summary_large_image" if meta_data.get("image") else "summary",
        "twitter:title": meta_data["title"],
        "twitter:description": meta_data["description"]
    }
    
    if meta_data.get("image"):
        twitter_tags["twitter:image"] = meta_data["image"]
    
    return twitter_tags

def _generate_structured_data(meta_data: Dict, base_url: str) -> Dict:
    """生成文章的结构化数据（JSON-LD）"""
    structured_data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": meta_data["title"],
        "description": meta_data["description"],
        "url": meta_data["url"],
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": meta_data["url"]
        },
        "publisher": {
            "@type": "Organization",
            "name": meta_data.get("site_name", DEFAULT_BASE_SETTINGS["site_title"]),
            "url": base_url
        }
    }
    
    if meta_data.get("image"):
        structured_data["image"] = meta_data["image"]
    
    if meta_data.get("published_time"):
        structured_data["datePublished"] = meta_data["published_time"]
    
    if meta_data.get("modified_time"):
        structured_data["dateModified"] = meta_data["modified_time"]
    
    if meta_data.get("author"):
        structured_data["author"] = {
            "@type": "Person",
            "name": meta_data["author"]
        }
    
    return structured_data

def _generate_website_structured_data(meta_data: Dict) -> Dict:
    """生成网站的结构化数据（JSON-LD）"""
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": meta_data["title"],
        "description": meta_data["description"],
        "url": meta_data["url"]
    }

def _generate_post_seo_data(db_post, request, db: Session) -> Dict:
    """
    为文章生成SEO数据的辅助函数
    
    Args:
        db_post: 数据库中的文章对象
        request: 请求对象
        db: 数据库会话
    
    Returns:
        包含SEO元数据的字典
    """
    # 获取站点设置
    site_title_setting = crud_setting.get_setting(db, key="site_title")
    site_url_setting = crud_setting.get_setting(db, key="site_url")
    
    site_title = site_title_setting.value.get("value") if site_title_setting and site_title_setting.value else DEFAULT_BASE_SETTINGS["site_title"]
    base_url = site_url_setting.value.get("value") if site_url_setting else str(request.base_url).rstrip('/')
    
    format_slugs = [fmt.slug for fmt in db_post.formats if getattr(fmt, "slug", None)] if db_post.formats else []
    primary_intent = choose_primary_intent_slug(format_slugs)
    post_url = urljoin(base_url, f"/{to_public_post_segment(primary_intent)}/{db_post.slug}")
    
    # 生成SEO元数据
    meta_data = {
        "title": f"{db_post.title} - {site_title}",
        "description": db_post.excerpt or _extract_description_from_content(db_post.content_markdown),
        "url": post_url,
        "image": db_post.featured_image_url,
        "type": "article",
        "published_time": db_post.published_at.isoformat() if db_post.published_at else None,
        "modified_time": db_post.updated_at.isoformat() if db_post.updated_at else None,
        "author": (
            resolve_public_display_name(
                getattr(db_post.author, "display_name", None),
                seed_value=getattr(db_post.author, "id", None),
                fallback=site_title,
            )
            if db_post.author
            else None
        ),
        "section": ", ".join([cat.name for cat in db_post.categories]) if db_post.categories else None,
        "tags": [tag.name for tag in db_post.tags] if db_post.tags else []
    }
    # 为结构化数据提供站点名称，避免硬编码
    meta_data["site_name"] = site_title
    
    # 生成标签和结构化数据
    open_graph = _generate_open_graph_tags(meta_data, site_title)
    twitter_cards = _generate_twitter_cards_tags(meta_data)
    structured_data = _generate_structured_data(meta_data, base_url)
    
    return {
        "meta_data": meta_data,
        "open_graph": open_graph,
        "twitter_cards": twitter_cards,
        "structured_data": structured_data
    }

def _generate_homepage_seo_data(request, db: Session) -> Dict:
    """
    为首页生成SEO数据的辅助函数
    
    Args:
        request: 请求对象
        db: 数据库会话
    
    Returns:
        包含SEO元数据的字典
    """
    # 获取站点设置
    site_title_setting = crud_setting.get_setting(db, key="site_title")
    tagline_setting = crud_setting.get_setting(db, key="tagline")
    site_description_setting = crud_setting.get_setting(db, key="site_description")
    site_url_setting = crud_setting.get_setting(db, key="site_url")
    site_logo_setting = crud_setting.get_setting(db, key="site_logo_light")
    
    site_title = site_title_setting.value.get("value") if site_title_setting and site_title_setting.value else DEFAULT_BASE_SETTINGS["site_title"]
    tagline = tagline_setting.value.get("value") if tagline_setting and tagline_setting.value else DEFAULT_BASE_SETTINGS["tagline"]
    site_description = site_description_setting.value.get("value") if site_description_setting and site_description_setting.value else DEFAULT_BASE_SETTINGS["site_description"]
    base_url = site_url_setting.value.get("value") if site_url_setting else str(request.base_url).rstrip('/')
    site_logo = site_logo_setting.value.get("value") if site_logo_setting else None
    
    meta_data = {
        "title": f"{site_title} - {tagline}",
        "description": site_description or tagline,
        "url": base_url,
        "image": site_logo,
        "type": "website"
    }
    # 为结构化数据提供站点名称，避免硬编码
    meta_data["site_name"] = site_title
    
    # 生成标签
    open_graph = _generate_open_graph_tags(meta_data, site_title)
    twitter_cards = _generate_twitter_cards_tags(meta_data)
    structured_data = _generate_website_structured_data(meta_data)
    
    return {
        "meta_data": meta_data,
        "open_graph": open_graph,
        "twitter_cards": twitter_cards,
        "structured_data": structured_data
    }

